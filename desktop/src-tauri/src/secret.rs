//! Dónde vive la contraseña de PostgreSQL.
//!
//! - Windows (uso real): Administrador de credenciales de Windows, ligado al usuario.
//! - Otros sistemas (solo desarrollo): archivo con permisos 0600 en la carpeta de datos.

use std::path::PathBuf;

pub type SecretResult<T> = Result<T, String>;

pub trait SecretStore: Send + Sync {
    fn get(&self) -> SecretResult<Option<String>>;
    fn set(&self, value: &str) -> SecretResult<()>;
    fn delete(&self) -> SecretResult<()>;
}

/// Credencial genérica de Windows. Se ve en "Administrador de credenciales" como
/// `<servicio>` / `<cuenta>`.
#[cfg(windows)]
pub struct CredentialManagerStore {
    entry: keyring::Entry,
}

#[cfg(windows)]
impl CredentialManagerStore {
    pub fn new(service: &str, account: &str) -> SecretResult<Self> {
        keyring::Entry::new(service, account)
            .map(|entry| Self { entry })
            .map_err(|e| e.to_string())
    }
}

#[cfg(windows)]
impl SecretStore for CredentialManagerStore {
    fn get(&self) -> SecretResult<Option<String>> {
        match self.entry.get_password() {
            Ok(v) => Ok(Some(v)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => Err(e.to_string()),
        }
    }
    fn set(&self, value: &str) -> SecretResult<()> {
        self.entry.set_password(value).map_err(|e| e.to_string())
    }
    fn delete(&self) -> SecretResult<()> {
        match self.entry.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(e.to_string()),
        }
    }
}

/// Archivo privado. **Solo para desarrollo y pruebas**: en Windows se usa el
/// Administrador de credenciales.
pub struct FileStore {
    path: PathBuf,
}

impl FileStore {
    pub fn new(path: PathBuf) -> Self {
        Self { path }
    }
}

impl SecretStore for FileStore {
    fn get(&self) -> SecretResult<Option<String>> {
        match std::fs::read_to_string(&self.path) {
            Ok(v) => Ok(Some(v.trim().to_string())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(format!("{}: {e}", self.path.display())),
        }
    }
    fn set(&self, value: &str) -> SecretResult<()> {
        use std::io::Write;
        if let Some(dir) = self.path.parent() {
            std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
        let mut options = std::fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(unix)]
        std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
        options
            .open(&self.path)
            .and_then(|mut f| f.write_all(value.as_bytes()))
            .map_err(|e| format!("{}: {e}", self.path.display()))
    }
    fn delete(&self) -> SecretResult<()> {
        match std::fs::remove_file(&self.path) {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(e) => Err(e.to_string()),
        }
    }
}
