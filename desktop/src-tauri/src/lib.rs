//! Aplicación de escritorio: ventana + servicios locales (PostgreSQL y backend).
//!
//! - **Instalada (release):** levanta PostgreSQL portable y el backend que vienen como
//!   recursos del instalador, y los detiene al cerrar.
//! - **Desarrollo (`tauri dev`):** no levanta nada; se usa `scripts/dev.sh`. Para probar
//!   el modo instalado en desarrollo, definir `CONTADOR_PGSQL_BIN` y `CONTADOR_BACKEND_EXE`.
//!
//! Con los servicios en marcha, un hilo aparte hace la copia de seguridad diaria (`backup.rs`)
//! sin demorar la apertura; una copia fallida solo se registra en `logs/backup.log`.
//!
//! La interfaz espera sola a que la API responda (muestra "Iniciando…").

pub mod backup;
pub mod secret;
pub mod stack;

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

use backup::BackupJob;
use secret::SecretStore;
use stack::{Stack, StackConfig};

/// Nombre de la carpeta de datos. Distinto del identificador de la app a propósito:
/// el desinstalador de Tauri ofrece borrar la carpeta del identificador, y la
/// contabilidad no debe poder borrarse con un clic al desinstalar.
const DATA_DIR_NAME: &str = "ContadorAI";
const PG_PORT: u16 = 55440;
const API_PORT: u16 = 8765;
const SECRET_SERVICE: &str = "ContadorAI";
const SECRET_ACCOUNT: &str = "postgresql";
/// Cada cuánto se revisa si falta la copia del día (por si la app queda abierta varios días).
const BACKUP_RECHECK: Duration = Duration::from_secs(30 * 60);

enum StackSlot {
    Starting,
    // En una caja: en Windows `Stack` incluye el job object y agranda mucho el enum.
    Running(Box<Stack>),
    Closing,
}

/// Estado de los servicios y el hilo que los arranca. El hilo se guarda para poder esperarlo
/// al salir: si la ventana se cierra durante el arranque, es ese hilo el que detiene todo.
struct StackState(Mutex<StackSlot>, Mutex<Option<std::thread::JoinHandle<()>>>);

pub fn run() {
    let app = tauri::Builder::default()
        // Una sola instancia: una segunda apertura enfoca la ventana existente
        // (dos instancias pelearían por la base y el puerto de la API).
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .manage(StackState(Mutex::new(StackSlot::Starting), Mutex::new(None)))
        .setup(|app| {
            match stack_config(app.handle()) {
                Ok(Some(config)) => {
                    let starter = start_in_background(app.handle().clone(), config);
                    *app.state::<StackState>()
                        .1
                        .lock()
                        .unwrap_or_else(std::sync::PoisonError::into_inner) = Some(starter);
                }
                Ok(None) => log::info!("Modo desarrollo: los servicios los levanta scripts/dev.sh"),
                Err(message) => fail(app.handle(), &message),
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("no se pudo construir la aplicación");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let state = handle.state::<StackState>();
            let previous = std::mem::replace(&mut *lock(&state), StackSlot::Closing);
            match previous {
                StackSlot::Running(stack) => {
                    log::info!("Deteniendo servicios locales");
                    stack.stop();
                }
                StackSlot::Starting => {
                    // Todavía arrancando: al terminar, el hilo de arranque ve `Closing` y detiene
                    // los servicios. Hay que esperarlo, porque al volver de este evento el proceso
                    // termina y mataría el hilo antes de detener PostgreSQL. No se traba: el
                    // arranque tiene su propio límite de tiempo y `fail` muestra el error en otro
                    // hilo.
                    let starter = state
                        .1
                        .lock()
                        .unwrap_or_else(std::sync::PoisonError::into_inner)
                        .take();
                    if let Some(starter) = starter {
                        log::info!(
                            "La ventana se cerró durante el arranque: esperando para detener los servicios"
                        );
                        let _ = starter.join();
                    }
                }
                StackSlot::Closing => {}
            }
        }
    });
}

fn start_in_background(handle: tauri::AppHandle, config: StackConfig) -> std::thread::JoinHandle<()> {
    std::thread::spawn(move || {
        log::info!("Iniciando servicios locales en {}", config.data_dir.display());
        let store = match secret_store(&config) {
            Ok(store) => store,
            Err(message) => return fail(&handle, &message),
        };
        match Stack::start(&config, store.as_ref()) {
            Ok(stack) => {
                log::info!("Servicios listos en 127.0.0.1:{}", stack.api_port());
                let backup = stack.backup_job();
                let state = handle.state::<StackState>();
                let mut slot = lock(&state);
                if matches!(*slot, StackSlot::Closing) {
                    // La ventana se cerró mientras arrancaba.
                    drop(slot);
                    stack.stop();
                } else {
                    *slot = StackSlot::Running(Box::new(stack));
                    drop(slot);
                    start_backups(handle.clone(), backup);
                }
            }
            Err(e) => {
                log::error!("No se pudieron iniciar los servicios: {e}");
                fail(&handle, &e.to_string());
            }
        }
    })
}

/// Copia de seguridad diaria en un hilo propio: la app ya está abierta y no espera a la copia.
/// Si falla (queda en `logs/backup.log`), la app sigue funcionando y se reintenta luego.
fn start_backups(handle: tauri::AppHandle, job: BackupJob) {
    let spawned = std::thread::Builder::new().name("copias".into()).spawn(move || {
        loop {
            match job.run_if_due() {
                Ok(Some(path)) => log::info!("Copia de seguridad hecha: {}", path.display()),
                Ok(None) => log::info!("Ya hay una copia de seguridad de hoy"),
                Err(e) => log::error!("Copia de seguridad fallida: {e}"),
            }
            std::thread::sleep(BACKUP_RECHECK);
            if matches!(*lock(&handle.state::<StackState>()), StackSlot::Closing) {
                return;
            }
        }
    });
    if let Err(e) = spawned {
        log::error!("No se pudo iniciar el hilo de copias de seguridad: {e}");
    }
}

/// `None` en desarrollo sin variables: los servicios los levanta otro proceso.
fn stack_config(handle: &tauri::AppHandle) -> Result<Option<StackConfig>, String> {
    let env_path = |name: &str| std::env::var_os(name).map(PathBuf::from);
    let (pg_bin, backend_exe) = match (env_path("CONTADOR_PGSQL_BIN"), env_path("CONTADOR_BACKEND_EXE")) {
        (Some(pg), Some(be)) => (pg, be),
        _ if cfg!(debug_assertions) => return Ok(None),
        _ => {
            let resources = handle.path().resource_dir().map_err(|e| e.to_string())?;
            (
                resources.join("pgsql").join("bin"),
                resources
                    .join("backend")
                    .join(format!("contador-backend{}", std::env::consts::EXE_SUFFIX)),
            )
        }
    };
    let data_dir = match env_path("CONTADOR_DATA_DIR") {
        Some(dir) => dir,
        None => handle
            .path()
            .local_data_dir()
            .map_err(|e| e.to_string())?
            .join(DATA_DIR_NAME),
    };
    Ok(Some(StackConfig {
        pg_bin,
        backend_exe,
        data_dir,
        pg_port: PG_PORT,
        api_port: API_PORT,
        startup_timeout: Duration::from_secs(180),
    }))
}

fn secret_store(config: &StackConfig) -> Result<Box<dyn SecretStore>, String> {
    #[cfg(windows)]
    {
        let _ = config;
        Ok(Box::new(secret::CredentialManagerStore::new(
            SECRET_SERVICE,
            SECRET_ACCOUNT,
        )?))
    }
    #[cfg(not(windows))]
    {
        let _ = (SECRET_SERVICE, SECRET_ACCOUNT);
        Ok(Box::new(secret::FileStore::new(
            config.data_dir.join("secrets").join("postgresql"),
        )))
    }
}

/// Muestra el error y cierra la app: sin base de datos no hay nada útil que hacer.
fn fail(handle: &tauri::AppHandle, message: &str) {
    let handle = handle.clone();
    let text = format!("Contador AI no pudo iniciar.\n\n{message}");
    std::thread::spawn(move || {
        handle
            .dialog()
            .message(text)
            .title("Contador AI")
            .kind(MessageDialogKind::Error)
            .blocking_show();
        handle.exit(1);
    });
}

fn lock(state: &StackState) -> std::sync::MutexGuard<'_, StackSlot> {
    state.0.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
}
