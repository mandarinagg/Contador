//! Aplicación de escritorio: ventana + servicios locales (PostgreSQL y backend).
//!
//! - **Instalada (release):** levanta PostgreSQL portable y el backend que vienen como
//!   recursos del instalador, y los detiene al cerrar.
//! - **Desarrollo (`tauri dev`):** no levanta nada; se usa `scripts/dev.sh`. Para probar
//!   el modo instalado en desarrollo, definir `CONTADOR_PGSQL_BIN` y `CONTADOR_BACKEND_EXE`.
//!
//! La interfaz espera sola a que la API responda (muestra "Iniciando…").

pub mod secret;
pub mod stack;

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogKind};

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

enum StackSlot {
    Starting,
    Running(Stack),
    Closing,
}

struct StackState(Mutex<StackSlot>);

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
        .manage(StackState(Mutex::new(StackSlot::Starting)))
        .setup(|app| {
            match stack_config(app.handle()) {
                Ok(Some(config)) => start_in_background(app.handle().clone(), config),
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
            if let StackSlot::Running(stack) = previous {
                log::info!("Deteniendo servicios locales");
                stack.stop();
            }
        }
    });
}

fn start_in_background(handle: tauri::AppHandle, config: StackConfig) {
    std::thread::spawn(move || {
        log::info!("Iniciando servicios locales en {}", config.data_dir.display());
        let store = match secret_store(&config) {
            Ok(store) => store,
            Err(message) => return fail(&handle, &message),
        };
        match Stack::start(&config, store.as_ref()) {
            Ok(stack) => {
                log::info!("Servicios listos en 127.0.0.1:{}", stack.api_port());
                let state = handle.state::<StackState>();
                let mut slot = lock(&state);
                if matches!(*slot, StackSlot::Closing) {
                    // La ventana se cerró mientras arrancaba.
                    drop(slot);
                    stack.stop();
                } else {
                    *slot = StackSlot::Running(stack);
                }
            }
            Err(e) => {
                log::error!("No se pudieron iniciar los servicios: {e}");
                fail(&handle, &e.to_string());
            }
        }
    });
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
