//! Copias de seguridad de la base `contador` y restauración en una base nueva.
//!
//! Reglas:
//! - Una copia automática por día: `<data_dir>/backups/auto/contador-AAAAMMDD-HHMMSS.dump`
//!   (formato custom de `pg_dump`, comprimido). La fecha es la hora local de la PC.
//! - Se escribe primero a `*.partial` y solo se renombra si `pg_dump` terminó bien **y**
//!   `pg_restore --list` puede leer el archivo. Una copia fallida deja el error en
//!   `logs/backup.log`, borra solo su `.partial` y no impide usar la app.
//! - Retención: se conservan las últimas [`KEEP_AUTO`] copias automáticas. Solo se borran
//!   archivos que coinciden **exactamente** con el patrón de copia automática dentro de
//!   `backups/auto/`; nunca otros archivos ni otras carpetas.
//! - La contraseña viaja solo por la variable de entorno `PGPASSWORD`, jamás como argumento.
//! - Nunca se escribe en `pgdata/`. La restauración ([`restore_dump`]) solo crea una base
//!   **nueva**: si ya existe, falla sin tocarla.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::Mutex;

use chrono::{Local, NaiveDateTime};

use crate::stack::{
    DB_NAME, DB_USER, Result, StackConfig, StackError, append, hidden, pg_tool, rotate, run_logged,
};

/// Cantidad de copias automáticas que se conservan.
pub const KEEP_AUTO: usize = 14;

const PREFIX: &str = "contador-";
const SUFFIX: &str = ".dump";
const PARTIAL_SUFFIX: &str = ".partial";
/// `AAAAMMDD-HHMMSS`
const STAMP_LEN: usize = 15;
const STAMP_FORMAT: &str = "%Y%m%d-%H%M%S";
/// Tope del registro antes de rotarlo a `backup.log.1`.
const LOG_MAX_BYTES: u64 = 512 * 1024;

/// Evita dos copias a la vez dentro del proceso (hilo diario y copia manual).
static RUNNING: Mutex<()> = Mutex::new(());

/// Nombre de una copia automática: `contador-AAAAMMDD-HHMMSS.dump`.
fn auto_name(now: NaiveDateTime) -> String {
    format!("{PREFIX}{}{SUFFIX}", now.format(STAMP_FORMAT))
}

/// ¿Es `AAAAMMDD-HHMMSS` con una fecha y una hora reales?
fn is_stamp(stamp: &str) -> bool {
    stamp.len() == STAMP_LEN
        && stamp
            .bytes()
            .enumerate()
            .all(|(i, b)| if i == 8 { b == b'-' } else { b.is_ascii_digit() })
        && NaiveDateTime::parse_from_str(stamp, STAMP_FORMAT).is_ok()
}

/// ¿El nombre coincide exactamente con una copia automática (`contador-AAAAMMDD-HHMMSS.dump`)?
pub fn is_auto_backup_name(name: &str) -> bool {
    name.strip_prefix(PREFIX)
        .and_then(|rest| rest.strip_suffix(SUFFIX))
        .is_some_and(is_stamp)
}

/// ¿El nombre es el `.partial` de una copia automática interrumpida?
fn is_auto_partial_name(name: &str) -> bool {
    name.strip_suffix(PARTIAL_SUFFIX).is_some_and(is_auto_backup_name)
}

/// Archivos regulares de `dir` (no carpetas ni enlaces) cuyo nombre cumple `matches`, ordenados
/// por nombre. Para copias automáticas el nombre ordena igual que la fecha.
fn matching_files(dir: &Path, matches: fn(&str) -> bool) -> Vec<PathBuf> {
    let Ok(entries) = fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut files: Vec<PathBuf> = entries
        .flatten()
        .filter(|e| e.file_type().is_ok_and(|t| t.is_file()))
        .filter(|e| e.file_name().to_str().is_some_and(matches))
        .map(|e| e.path())
        .collect();
    files.sort();
    files
}

/// ¿Ya hay una copia automática del día de `now`?
fn has_backup_for_day(auto_dir: &Path, now: NaiveDateTime) -> bool {
    let day = now.format("%Y%m%d").to_string();
    matching_files(auto_dir, is_auto_backup_name)
        .iter()
        .filter_map(|p| p.file_name()?.to_str())
        .any(|name| name[PREFIX.len()..].starts_with(&day))
}

/// Deja las últimas `keep` copias automáticas y borra las más viejas. Devuelve cuántas borró.
/// Con `keep` o menos copias no borra nada. Ignora todo lo que no coincide con el patrón.
pub fn apply_retention(auto_dir: &Path, keep: usize, log: &Path) -> usize {
    let backups = matching_files(auto_dir, is_auto_backup_name);
    let excess = backups.len().saturating_sub(keep);
    let mut deleted = 0;
    for old in backups.iter().take(excess) {
        match fs::remove_file(old) {
            Ok(()) => {
                deleted += 1;
                log_line(
                    log,
                    &format!("Retención: se borró la copia antigua {}", old.display()),
                );
            }
            Err(e) => log_line(
                log,
                &format!("Retención: no se pudo borrar {}: {e}", old.display()),
            ),
        }
    }
    deleted
}

/// Lo necesario para hacer copias sin retener el `Stack`: se puede mover a otro hilo.
#[derive(Clone)]
pub struct BackupJob {
    config: StackConfig,
    /// Solo en memoria; se pasa a `pg_dump` por `PGPASSWORD`.
    password: String,
}

impl BackupJob {
    pub(crate) fn new(config: StackConfig, password: String) -> Self {
        Self { config, password }
    }

    /// `<data_dir>/backups/auto`
    pub fn auto_dir(&self) -> PathBuf {
        self.config.data_dir.join("backups").join("auto")
    }

    /// `<data_dir>/logs/backup.log`
    pub fn log_path(&self) -> PathBuf {
        self.config.logs_dir().join("backup.log")
    }

    /// Hace una copia ahora (aunque ya haya una de hoy) y aplica la retención.
    pub fn run(&self) -> Result<PathBuf> {
        self.execute(Local::now().naive_local(), false)?
            .ok_or_else(|| StackError::new("La copia no devolvió ruta"))
    }

    /// Hace la copia automática solo si todavía no hay una de hoy. `Ok(None)` si ya existía.
    pub fn run_if_due(&self) -> Result<Option<PathBuf>> {
        self.execute(Local::now().naive_local(), true)
    }

    fn execute(&self, now: NaiveDateTime, only_if_due: bool) -> Result<Option<PathBuf>> {
        let _running = RUNNING.lock().unwrap_or_else(std::sync::PoisonError::into_inner);
        let dir = self.auto_dir();
        let log = self.log_path();
        if let Err(e) = prepare_dir(&dir) {
            return Err(self.failure(&log, format!("No se pudo preparar {}: {e}", dir.display())));
        }
        if only_if_due && has_backup_for_day(&dir, now) {
            return Ok(None);
        }
        // Restos de una copia que quedó a medias porque la app se cerró durante la copia.
        for stale in matching_files(&dir, is_auto_partial_name) {
            let _ = fs::remove_file(&stale);
            log_line(
                &log,
                &format!("Se borró una copia incompleta anterior: {}", stale.display()),
            );
        }

        let target = dir.join(auto_name(now));
        if target.exists() {
            return Err(self.failure(&log, format!("Ya existe {}", target.display())));
        }
        let partial = dir.join(format!("{}{PARTIAL_SUFFIX}", auto_name(now)));
        log_line(&log, &format!("Iniciando copia en {}", target.display()));

        let made = self
            .dump(&partial, &log)
            .and_then(|()| verify(&self.config, &partial, &log))
            .and_then(|()| {
                fs::rename(&partial, &target).map_err(|e| {
                    format!(
                        "No se pudo renombrar {} a {}: {e}",
                        partial.display(),
                        target.display()
                    )
                })
            });
        if let Err(message) = made {
            // Solo el `.partial` de esta copia; las copias anteriores no se tocan.
            let _ = fs::remove_file(&partial);
            return Err(self.failure(&log, message));
        }
        let size = fs::metadata(&target).map_or(0, |m| m.len());
        log_line(
            &log,
            &format!("Copia terminada: {} ({size} bytes)", target.display()),
        );
        apply_retention(&dir, KEEP_AUTO, &log);
        Ok(Some(target))
    }

    /// `pg_dump -Fc` de la base `contador` hacia `partial`.
    fn dump(&self, partial: &Path, log: &Path) -> std::result::Result<(), String> {
        let mut cmd = Command::new(self.config.pg_tool("pg_dump"));
        cmd.args(["-Fc", "-h", "127.0.0.1", "-p"])
            .arg(self.config.pg_port.to_string())
            .args(["-U", DB_USER, "--no-password", "-f"])
            .arg(partial)
            .arg(DB_NAME)
            // La contraseña va por entorno, nunca por argumento de línea de comandos.
            .env("PGPASSWORD", &self.password);
        let output = run_captured(&mut cmd).map_err(|e| format!("No se pudo ejecutar pg_dump: {e}"))?;
        if output.status.success() {
            return Ok(());
        }
        log_line(log, &format!("pg_dump falló ({}):", output.status));
        log_output(log, &output);
        Err(format!("pg_dump terminó con error ({})", output.status))
    }

    /// Registra el error, y lo devuelve apuntando al registro.
    fn failure(&self, log: &Path, message: String) -> StackError {
        log_line(log, &format!("ERROR: {message}"));
        StackError::with_log(
            format!("No se pudo hacer la copia de seguridad: {message}"),
            log.to_path_buf(),
        )
    }
}

/// `pg_restore --list` sobre el archivo: comprueba que se puede leer. No se conecta a la base.
fn verify(config: &StackConfig, dump: &Path, log: &Path) -> std::result::Result<(), String> {
    let mut cmd = Command::new(config.pg_tool("pg_restore"));
    cmd.arg("--list").arg(dump);
    let output = run_captured(&mut cmd).map_err(|e| format!("No se pudo ejecutar pg_restore: {e}"))?;
    if output.status.success() && !output.stdout.is_empty() {
        return Ok(());
    }
    log_line(
        log,
        &format!("La verificación con pg_restore --list falló ({}):", output.status),
    );
    log_output(log, &output);
    Err("La copia generada no se puede leer (pg_restore --list)".to_string())
}

/// Datos de la base **nueva** donde se restaura.
pub struct RestoreTarget<'a> {
    pub port: u16,
    pub user: &'a str,
    pub password: &'a str,
    /// Nombre de la base a crear. Si ya existe, la restauración se rechaza.
    pub database: &'a str,
}

/// Restaura un `.dump` en una base **nueva y vacía**: la crea con `createdb` (falla si ya
/// existe, sin tocarla) y carga el contenido con `pg_restore` en una sola transacción.
/// Si la carga falla, borra la base recién creada (nunca una preexistente) y devuelve el error.
/// Los detalles quedan en `log`.
pub fn restore_dump(pg_bin: &Path, dump: &Path, target: &RestoreTarget<'_>, log: &Path) -> Result<()> {
    if !dump.is_file() {
        return Err(StackError::new(format!("No existe la copia {}", dump.display())));
    }
    let port = target.port.to_string();
    let connection = |tool: &str| {
        let mut cmd = Command::new(pg_tool(pg_bin, tool));
        cmd.args(["-h", "127.0.0.1", "-p", &port, "-U", target.user, "--no-password"])
            .env("PGPASSWORD", target.password);
        cmd
    };

    let mut create = connection("createdb");
    create.arg(target.database);
    run_logged(&mut create, log).map_err(|()| {
        StackError::with_log(
            format!(
                "No se pudo crear la base '{}' (¿ya existe?). Solo se restaura en una base nueva; no se tocó nada.",
                target.database
            ),
            log.to_path_buf(),
        )
    })?;

    let mut restore = connection("pg_restore");
    restore
        .args([
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "-d",
            target.database,
        ])
        .arg(dump);
    if run_logged(&mut restore, log).is_err() {
        // La base se creó recién arriba, así que es seguro quitarla para poder reintentar.
        let mut drop_db = connection("dropdb");
        drop_db.args(["--if-exists", target.database]);
        let _ = run_logged(&mut drop_db, log);
        return Err(StackError::with_log(
            "No se pudo restaurar la copia. La base nueva se descartó.",
            log.to_path_buf(),
        ));
    }
    Ok(())
}

/// Crea `backups/` y `backups/auto/`. En sistemas Unix (solo desarrollo) quedan privadas.
fn prepare_dir(auto_dir: &Path) -> std::io::Result<()> {
    fs::create_dir_all(auto_dir)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let private = fs::Permissions::from_mode(0o700);
        if let Some(backups) = auto_dir.parent() {
            fs::set_permissions(backups, private.clone())?;
        }
        fs::set_permissions(auto_dir, private)?;
    }
    // En Windows hereda los permisos de %LOCALAPPDATA%, que es solo del usuario.
    Ok(())
}

/// Ejecuta una herramienta sin ventana y captura su salida.
fn run_captured(cmd: &mut Command) -> std::io::Result<Output> {
    hidden(cmd).stdin(Stdio::null()).output()
}

/// Agrega la salida de error de una herramienta al registro (acotada).
fn log_output(log: &Path, output: &Output) {
    const MAX: usize = 4000;
    let text = String::from_utf8_lossy(&output.stderr);
    let text = text.trim();
    let start = text.len().saturating_sub(MAX);
    let start = (start..=text.len())
        .find(|&i| text.is_char_boundary(i))
        .unwrap_or(0);
    log_line(log, &text[start..]);
}

/// Línea con fecha y hora local en `logs/backup.log` (se rota a `.1` al pasar el tope).
fn log_line(log: &Path, text: &str) {
    if fs::metadata(log).is_ok_and(|m| m.len() > LOG_MAX_BYTES) {
        rotate(log);
    }
    append(
        log,
        &format!("[{}] {text}\n", Local::now().format("%Y-%m-%d %H:%M:%S")),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stamp(s: &str) -> NaiveDateTime {
        NaiveDateTime::parse_from_str(s, STAMP_FORMAT).unwrap()
    }

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("contador-backup-unit-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn name_pattern_is_exact() {
        assert!(is_auto_backup_name("contador-20261124-093015.dump"));
        assert_eq!(
            auto_name(stamp("20261124-093015")),
            "contador-20261124-093015.dump"
        );
        for bad in [
            "contador-20261124-093015.dump.partial",
            "contador-20261124-093015.dump.bak",
            "contador-20261124-093015.DUMP",
            "contador-20261124-09301.dump",
            "contador-20261124-0930150.dump",
            "contador-2026112-4093015.dump",
            "contador-20261324-093015.dump",
            "contador-20261124-253015.dump",
            "contador-20261124_093015.dump",
            "contador-manual.dump",
            "Contador-20261124-093015.dump",
            "xcontador-20261124-093015.dump",
            "contador-+0261124-093015.dump",
            ".dump",
            "",
        ] {
            assert!(!is_auto_backup_name(bad), "{bad} no debe coincidir");
        }
        assert!(is_auto_partial_name("contador-20261124-093015.dump.partial"));
        assert!(!is_auto_partial_name("contador-manual.dump.partial"));
        assert!(!is_auto_partial_name("contador-20261124-093015.dump"));
    }

    #[test]
    fn due_check_looks_only_at_today() {
        let dir = temp_dir("due");
        let now = stamp("20261124-180000");
        assert!(!has_backup_for_day(&dir, now));
        fs::write(dir.join("contador-20261123-235959.dump"), "x").unwrap();
        fs::write(dir.join("contador-20261124-080000.dump.partial"), "x").unwrap();
        fs::write(dir.join("contador-20261124-manual.dump"), "x").unwrap();
        assert!(
            !has_backup_for_day(&dir, now),
            "ayer, un .partial y un nombre ajeno no cuentan"
        );
        fs::write(dir.join("contador-20261124-080000.dump"), "x").unwrap();
        assert!(has_backup_for_day(&dir, now));
        fs::remove_dir_all(&dir).unwrap();
    }

    #[test]
    fn retention_keeps_newest_and_touches_nothing_else() {
        let dir = temp_dir("retention");
        let log = dir.join("backup.log");
        // Menos copias que el tope: no se borra nada.
        for day in 1..=5 {
            fs::write(dir.join(format!("contador-202601{day:02}-000000.dump")), "x").unwrap();
        }
        assert_eq!(apply_retention(&dir, KEEP_AUTO, &log), 0);
        assert_eq!(matching_files(&dir, is_auto_backup_name).len(), 5);

        // 20 copias + archivos ajenos + una carpeta con nombre de copia.
        for day in 6..=20 {
            fs::write(dir.join(format!("contador-202601{day:02}-000000.dump")), "x").unwrap();
        }
        let foreign = [
            "contador-manual.dump",
            "contador-20260101-000000.dump.bak",
            "contador-20260101-000000.dump.partial",
            "notas.txt",
        ];
        for name in foreign {
            fs::write(dir.join(name), "ajeno").unwrap();
        }
        fs::create_dir(dir.join("contador-20250101-000000.dump")).unwrap();
        fs::write(
            dir.join("contador-20250101-000000.dump").join("dentro.txt"),
            "ajeno",
        )
        .unwrap();

        assert_eq!(apply_retention(&dir, KEEP_AUTO, &log), 6);
        let left = matching_files(&dir, is_auto_backup_name);
        assert_eq!(left.len(), KEEP_AUTO);
        assert!(left[0].ends_with("contador-20260107-000000.dump"));
        assert!(left[KEEP_AUTO - 1].ends_with("contador-20260120-000000.dump"));
        for name in foreign {
            assert!(dir.join(name).is_file(), "{name} debía sobrevivir");
        }
        assert!(
            dir.join("contador-20250101-000000.dump")
                .join("dentro.txt")
                .is_file()
        );
        // Con exactamente el tope tampoco se borra nada.
        assert_eq!(apply_retention(&dir, KEEP_AUTO, &log), 0);
        fs::remove_dir_all(&dir).unwrap();
    }
}
