//! Arranque y parada de los servicios locales: PostgreSQL portable y backend empaquetado.
//!
//! No depende de Tauri para poder probarse solo (`tests/stack.rs`) con binarios reales.
//!
//! Garantías:
//! - Nunca borra una carpeta de datos existente. La creación inicial ocurre en
//!   `pgdata.init` y solo se renombra a `pgdata` cuando terminó bien.
//! - PostgreSQL escucha solo en 127.0.0.1 con `scram-sha-256` y una contraseña aleatoria
//!   guardada en un [`SecretStore`] (Administrador de credenciales en Windows).
//! - Las copias de seguridad (`backup.rs`) solo escriben en `backups/` y nunca tocan `pgdata`.
//! - Si la app se cerró mal y PostgreSQL quedó en marcha, se reutiliza.
//! - En Windows el backend queda atado a la app: si la app muere, el backend también.

use std::fmt;
use std::fs;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use crate::backup::BackupJob;
use crate::secret::SecretStore;

pub const DB_NAME: &str = "contador";
pub const DB_USER: &str = "contador";
const HEALTH_PATH: &str = "/api/v1/system/health";

#[derive(Debug, Clone)]
pub struct StackConfig {
    /// Carpeta `bin` de PostgreSQL (initdb, pg_ctl, createdb, postgres).
    pub pg_bin: PathBuf,
    /// Ejecutable del backend (`contador-backend[.exe]`).
    pub backend_exe: PathBuf,
    /// Carpeta de datos de la app: `pgdata/`, `logs/` y, fuera de Windows, `secrets/`.
    pub data_dir: PathBuf,
    pub pg_port: u16,
    pub api_port: u16,
    /// Tiempo máximo para que el backend responda (incluye migraciones).
    pub startup_timeout: Duration,
}

impl StackConfig {
    pub fn pgdata(&self) -> PathBuf {
        self.data_dir.join("pgdata")
    }
    pub fn logs_dir(&self) -> PathBuf {
        self.data_dir.join("logs")
    }
    pub(crate) fn pg_tool(&self, name: &str) -> PathBuf {
        pg_tool(&self.pg_bin, name)
    }
}

/// Ruta de una herramienta de PostgreSQL dentro de su carpeta `bin` (agrega `.exe` en Windows).
pub(crate) fn pg_tool(pg_bin: &Path, name: &str) -> PathBuf {
    pg_bin.join(format!("{name}{}", std::env::consts::EXE_SUFFIX))
}

#[derive(Debug)]
pub struct StackError {
    pub message: String,
    /// Archivo de registro donde mirar, si corresponde.
    pub log: Option<PathBuf>,
}

impl StackError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            log: None,
        }
    }
    pub(crate) fn with_log(message: impl Into<String>, log: PathBuf) -> Self {
        Self {
            message: message.into(),
            log: Some(log),
        }
    }
}

impl fmt::Display for StackError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)?;
        if let Some(log) = &self.log {
            write!(f, "\n\nRegistro: {}", log.display())?;
        }
        Ok(())
    }
}

impl std::error::Error for StackError {}

pub(crate) type Result<T> = std::result::Result<T, StackError>;

/// Servicios en marcha. Llamar a [`Stack::stop`] al cerrar la app.
pub struct Stack {
    config: StackConfig,
    /// Contraseña de la base: solo en memoria, para las copias de seguridad.
    password: String,
    backend: Child,
    #[cfg(windows)]
    _job: windows_job::Job,
}

impl Stack {
    pub fn start(config: &StackConfig, secrets: &dyn SecretStore) -> Result<Self> {
        fs::create_dir_all(config.logs_dir())
            .map_err(|e| StackError::new(format!("No se pudo crear {}: {e}", config.logs_dir().display())))?;
        for tool in ["initdb", "pg_ctl", "createdb"] {
            if !config.pg_tool(tool).is_file() {
                return Err(StackError::new(format!(
                    "Falta {}",
                    config.pg_tool(tool).display()
                )));
            }
        }
        if !config.backend_exe.is_file() {
            return Err(StackError::new(format!("Falta {}", config.backend_exe.display())));
        }

        if !config.pgdata().join("PG_VERSION").is_file() {
            initialize_cluster(config, secrets)?;
        }
        let password = secrets
            .get()
            .map_err(|e| StackError::new(format!("No se pudo leer la contraseña de la base: {e}")))?
            .ok_or_else(|| {
                StackError::new(format!(
                    "La base de datos existe en {} pero no se encontró su contraseña en el almacén de \
                     credenciales. No se tocó ningún dato. Restaurá la credencial o pedí ayuda técnica.",
                    config.pgdata().display()
                ))
            })?;

        start_postgres(config, &config.pgdata())?;

        if port_in_use(config.api_port) {
            return Err(StackError::new(format!(
                "El puerto {} ya está en uso por otro programa. Cerralo y volvé a abrir Contador AI.",
                config.api_port
            )));
        }
        let backend_log = config.logs_dir().join("backend.log");
        rotate(&backend_log);
        let mut backend = spawn_backend(config, &password, &backend_log)?;
        #[cfg(windows)]
        let job = windows_job::Job::kill_on_close(&backend)
            .map_err(|e| StackError::new(format!("No se pudo vincular el backend a la app: {e}")))?;

        if let Err(e) = wait_healthy(config, &mut backend, &backend_log) {
            let _ = backend.kill();
            let _ = backend.wait();
            return Err(e);
        }
        Ok(Self {
            config: config.clone(),
            password,
            backend,
            #[cfg(windows)]
            _job: job,
        })
    }

    pub fn api_port(&self) -> u16 {
        self.config.api_port
    }

    /// Datos para hacer copias desde otro hilo sin retener el `Stack` (se puede clonar y mover).
    pub fn backup_job(&self) -> BackupJob {
        BackupJob::new(self.config.clone(), self.password.clone())
    }

    /// Hace una copia de seguridad ahora (siempre crea una nueva) y aplica la retención.
    pub fn backup(&self) -> Result<PathBuf> {
        self.backup_job().run()
    }

    /// Detiene el backend y luego PostgreSQL (parada rápida: confirma lo confirmado).
    pub fn stop(mut self) {
        let _ = self.backend.kill();
        let _ = self.backend.wait();
        let _ = stop_postgres(&self.config, &self.config.pgdata());
    }
}

/// Primera ejecución: crea el clúster en `pgdata.init`, crea la base y recién entonces
/// lo renombra a `pgdata`. Si algo falla, `pgdata` no existe y el próximo arranque reintenta.
fn initialize_cluster(config: &StackConfig, secrets: &dyn SecretStore) -> Result<()> {
    let pgdata = config.pgdata();
    if pgdata.exists() {
        return Err(StackError::new(format!(
            "La carpeta {} existe pero no es una base de datos completa. No se modificó; \
             revisala antes de continuar.",
            pgdata.display()
        )));
    }
    let staging = config.data_dir.join("pgdata.init");
    if staging.exists() {
        // Solo puede venir de una creación inicial interrumpida: nunca contiene datos del usuario.
        fs::remove_dir_all(&staging)
            .map_err(|e| StackError::new(format!("No se pudo limpiar {}: {e}", staging.display())))?;
    }

    let password = random_password()?;
    secrets
        .set(&password)
        .map_err(|e| StackError::new(format!("No se pudo guardar la contraseña de la base: {e}")))?;

    let init_log = config.logs_dir().join("initdb.log");
    let pwfile = config.data_dir.join(".pgpass.init");
    write_private(&pwfile, &password)?;
    let initdb = run_logged(
        Command::new(config.pg_tool("initdb"))
            .arg("-D")
            .arg(&staging)
            .args(["-U", DB_USER, "-E", "UTF8", "--auth=scram-sha-256"])
            .arg(format!("--pwfile={}", pwfile.display()))
            // Orden alfabético en español (ñ, tildes) sin depender del idioma de Windows.
            .args(["--locale=C", "--locale-provider=icu", "--icu-locale=es-PY"]),
        &init_log,
    );
    let _ = fs::remove_file(&pwfile);
    initdb
        .map_err(|_| StackError::with_log("No se pudo crear la base de datos (initdb).", init_log.clone()))?;

    start_postgres(config, &staging)?;
    let created = run_logged(
        Command::new(config.pg_tool("createdb"))
            .args([
                "-h",
                "127.0.0.1",
                "-p",
                &config.pg_port.to_string(),
                "-U",
                DB_USER,
                DB_NAME,
            ])
            .env("PGPASSWORD", &password),
        &init_log,
    );
    let stopped = stop_postgres(config, &staging);
    created.map_err(|_| StackError::with_log("No se pudo crear la base 'contador'.", init_log.clone()))?;
    stopped?;

    fs::rename(&staging, &pgdata).map_err(|e| {
        StackError::new(format!(
            "No se pudo mover {} a {}: {e}",
            staging.display(),
            pgdata.display()
        ))
    })
}

fn start_postgres(config: &StackConfig, pgdata: &Path) -> Result<()> {
    if postgres_running(config, pgdata) {
        log::info!(
            "PostgreSQL ya estaba en marcha en {}; se reutiliza",
            pgdata.display()
        );
        return Ok(());
    }
    let log = config.logs_dir().join("postgresql.log");
    rotate(&log);
    run_logged(
        Command::new(config.pg_tool("pg_ctl"))
            .arg("start")
            .arg("-D")
            .arg(pgdata)
            .args(["-w", "-t", "60", "-l"])
            .arg(&log)
            .arg("-o")
            // Solo TCP en 127.0.0.1: sin sockets Unix (el binario de Ubuntu los pondría en
            // /var/run/postgresql; en Windows ya vienen apagados).
            .arg(format!(
                "-p {} -c listen_addresses=127.0.0.1 -c unix_socket_directories=",
                config.pg_port
            )),
        &config.logs_dir().join("pg_ctl.log"),
    )
    .map_err(|_| StackError::with_log("PostgreSQL no pudo iniciar.", log))
}

fn stop_postgres(config: &StackConfig, pgdata: &Path) -> Result<()> {
    run_logged(
        Command::new(config.pg_tool("pg_ctl"))
            .arg("stop")
            .arg("-D")
            .arg(pgdata)
            .args(["-m", "fast", "-w", "-t", "60"]),
        &config.logs_dir().join("pg_ctl.log"),
    )
    .map_err(|_| StackError::with_log("PostgreSQL no se detuvo.", config.logs_dir().join("pg_ctl.log")))
}

fn postgres_running(config: &StackConfig, pgdata: &Path) -> bool {
    // `pg_ctl status` devuelve 0 si el servidor de esa carpeta está en marcha.
    hidden(&mut Command::new(config.pg_tool("pg_ctl")))
        .arg("status")
        .arg("-D")
        .arg(pgdata)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|s| s.success())
}

fn spawn_backend(config: &StackConfig, password: &str, log: &Path) -> Result<Child> {
    let out = fs::File::create(log)
        .map_err(|e| StackError::new(format!("No se pudo crear {}: {e}", log.display())))?;
    let err = out
        .try_clone()
        .map_err(|e| StackError::new(format!("No se pudo abrir {}: {e}", log.display())))?;
    hidden(&mut Command::new(&config.backend_exe))
        .env("CONTADOR_ENV", "production")
        .env(
            "CONTADOR_DATABASE_URL",
            format!(
                "postgresql+psycopg://{DB_USER}:{password}@127.0.0.1:{}/{DB_NAME}",
                config.pg_port
            ),
        )
        .env("CONTADOR_API_HOST", "127.0.0.1")
        .env("CONTADOR_API_PORT", config.api_port.to_string())
        .stdin(Stdio::null())
        .stdout(out)
        .stderr(err)
        .spawn()
        .map_err(|e| StackError::new(format!("No se pudo iniciar el backend: {e}")))
}

fn wait_healthy(config: &StackConfig, backend: &mut Child, log: &Path) -> Result<()> {
    let deadline = Instant::now() + config.startup_timeout;
    while Instant::now() < deadline {
        if let Ok(Some(status)) = backend.try_wait() {
            return Err(StackError::with_log(
                format!("El backend se cerró al iniciar ({status})."),
                log.to_path_buf(),
            ));
        }
        if http_get(config.api_port, HEALTH_PATH).is_ok_and(|(code, _)| code == 200) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(300));
    }
    Err(StackError::with_log(
        format!(
            "El backend no respondió en {} s.",
            config.startup_timeout.as_secs()
        ),
        log.to_path_buf(),
    ))
}

/// GET mínimo por HTTP/1.1 a 127.0.0.1 (evita sumar un cliente HTTP solo para esto).
pub fn http_get(port: u16, path: &str) -> std::io::Result<(u16, String)> {
    http_request(port, "GET", path, None)
}

pub fn http_request(
    port: u16,
    method: &str,
    path: &str,
    json: Option<&str>,
) -> std::io::Result<(u16, String)> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(2))?;
    stream.set_read_timeout(Some(Duration::from_secs(30)))?;
    let body = json.unwrap_or("");
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\
         Content-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    )?;
    let mut raw = String::new();
    stream.read_to_string(&mut raw)?;
    let code = raw
        .split_whitespace()
        .nth(1)
        .and_then(|c| c.parse().ok())
        .ok_or_else(|| std::io::Error::other("respuesta HTTP inválida"))?;
    let body = raw
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    Ok((code, body))
}

fn port_in_use(port: u16) -> bool {
    TcpStream::connect_timeout(
        &SocketAddr::from(([127, 0, 0, 1], port)),
        Duration::from_millis(500),
    )
    .is_ok()
}

/// Ejecuta una herramienta y agrega su salida al registro; error si no termina bien.
pub(crate) fn run_logged(cmd: &mut Command, log: &Path) -> std::result::Result<(), ()> {
    let output = hidden(cmd).stdin(Stdio::null()).output().map_err(|e| {
        append(
            log,
            &format!("No se pudo ejecutar {:?}: {e}\n", cmd.get_program()),
        );
    })?;
    append(
        log,
        &format!(
            "$ {:?} {:?}\n{}{}\n",
            cmd.get_program(),
            cmd.get_args().collect::<Vec<_>>(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        ),
    );
    if output.status.success() { Ok(()) } else { Err(()) }
}

pub(crate) fn append(log: &Path, text: &str) {
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(log) {
        let _ = f.write_all(text.as_bytes());
    }
}

/// Conserva el registro anterior como `<nombre>.1` (un solo nivel alcanza para diagnosticar).
pub(crate) fn rotate(log: &Path) {
    if log.exists() {
        let _ = fs::rename(log, log.with_extension("log.1"));
    }
}

fn random_password() -> Result<String> {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| StackError::new(format!("Sin fuente de aleatoriedad: {e}")))?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

fn write_private(path: &Path, content: &str) -> Result<()> {
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    // En Windows hereda los permisos de %LOCALAPPDATA%, que es solo del usuario.
    options
        .open(path)
        .and_then(|mut f| f.write_all(content.as_bytes()))
        .map_err(|e| StackError::new(format!("No se pudo escribir {}: {e}", path.display())))
}

/// En Windows, evita que cada herramienta abra una ventana de consola.
pub(crate) fn hidden(cmd: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

#[cfg(windows)]
mod windows_job {
    //! Job object con `KILL_ON_JOB_CLOSE`: cuando el proceso de la app termina (aun por
    //! un fallo), Windows cierra el handle y mata al backend y a sus hijos.
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation, SetInformationJobObject,
    };

    pub struct Job(HANDLE);

    // El handle solo se usa para cerrarlo al soltar el Job.
    unsafe impl Send for Job {}
    unsafe impl Sync for Job {}

    impl Job {
        pub fn kill_on_close(child: &Child) -> std::io::Result<Self> {
            // SAFETY: llamadas Win32 con punteros válidos; el handle se cierra en Drop.
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return Err(std::io::Error::last_os_error());
                }
                let job = Self(handle);
                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                if SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    (&raw const info).cast(),
                    u32::try_from(std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>()).unwrap_or(0),
                ) == 0
                {
                    return Err(std::io::Error::last_os_error());
                }
                if AssignProcessToJobObject(handle, child.as_raw_handle() as HANDLE) == 0 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(job)
            }
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            // SAFETY: handle propio, cerrado una sola vez.
            unsafe { CloseHandle(self.0) };
        }
    }
}
