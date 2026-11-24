//! Prueba del lanzador con binarios reales (PostgreSQL + backend empaquetado).
//!
//! Se ejecuta a pedido porque necesita los binarios:
//!
//! ```text
//! CONTADOR_TEST_PGSQL_BIN=<pgsql/bin> CONTADOR_TEST_BACKEND_EXE=<contador-backend> \
//!   cargo test --test stack -- --ignored --test-threads=1
//! ```
//!
//! Usa puertos propios (55441 / 8791) para no chocar con una app abierta.

use std::path::PathBuf;
use std::time::Duration;

use contador_desktop_lib::secret::{FileStore, SecretStore};
use contador_desktop_lib::stack::{Stack, StackConfig, http_get, http_request};

const PG_PORT: u16 = 55441;
const API_PORT: u16 = 8791;

fn config(data_dir: PathBuf) -> StackConfig {
    let var = |name: &str| {
        PathBuf::from(std::env::var(name).unwrap_or_else(|_| panic!("definir {name} (ver encabezado)")))
    };
    StackConfig {
        pg_bin: var("CONTADOR_TEST_PGSQL_BIN"),
        backend_exe: var("CONTADOR_TEST_BACKEND_EXE"),
        data_dir,
        pg_port: PG_PORT,
        api_port: API_PORT,
        startup_timeout: Duration::from_secs(180),
    }
}

fn temp_data_dir() -> PathBuf {
    let mut suffix = [0u8; 6];
    getrandom::fill(&mut suffix).unwrap();
    let name: String = suffix.iter().map(|b| format!("{b:02x}")).collect();
    std::env::temp_dir().join(format!("contador-stack-test-{name}"))
}

fn needs_setup() -> bool {
    let (code, body) = http_get(API_PORT, "/api/v1/system/setup").unwrap();
    assert_eq!(code, 200, "{body}");
    body.contains("\"needs_setup\":true")
}

#[test]
#[ignore = "requiere binarios de PostgreSQL y del backend"]
fn first_run_restart_and_recovery() {
    let dir = temp_data_dir();
    let cfg = config(dir.clone());
    let secrets = FileStore::new(dir.join("secrets").join("postgresql"));

    // 1. Primera ejecución: crea la base, guarda la contraseña, migra y responde.
    let stack = Stack::start(&cfg, &secrets).expect("primer arranque");
    assert!(cfg.pgdata().join("PG_VERSION").is_file());
    assert!(
        !dir.join("pgdata.init").exists(),
        "la carpeta temporal debe desaparecer"
    );
    assert!(
        !dir.join(".pgpass.init").exists(),
        "el archivo de contraseña de initdb debe borrarse"
    );
    let password = secrets.get().unwrap().expect("contraseña guardada");
    assert_eq!(password.len(), 64);
    assert!(needs_setup());

    let setup = r#"{"organization":{"legal_name":"Prueba lanzador EAS","legal_form":"EAS"},
        "owner":{"full_name":"Prueba","email":"lanzador@example.com","password":"Clave-Segura-2026"}}"#;
    let (code, body) = http_request(API_PORT, "POST", "/api/v1/system/setup", Some(setup)).unwrap();
    assert_eq!(code, 201, "{body}");
    stack.stop();
    assert!(
        http_get(API_PORT, "/api/v1/system/health").is_err(),
        "el backend debe quedar detenido"
    );

    // 2. Segundo arranque: reutiliza la base y la contraseña; los datos persisten.
    let stack = Stack::start(&cfg, &secrets).expect("segundo arranque");
    assert!(
        !needs_setup(),
        "los datos de la primera ejecución deben seguir ahí"
    );
    let login = r#"{"email":"lanzador@example.com","password":"Clave-Segura-2026"}"#;
    let (code, body) = http_request(API_PORT, "POST", "/api/v1/auth/login", Some(login)).unwrap();
    assert_eq!(code, 200, "{body}");
    assert_eq!(secrets.get().unwrap().as_deref(), Some(password.as_str()));
    stack.stop();

    // 3. Sin la contraseña, no arranca y no toca los datos.
    secrets.delete().unwrap();
    let err = Stack::start(&cfg, &secrets)
        .err()
        .expect("debe fallar sin contraseña");
    assert!(err.message.contains("no se encontró su contraseña"), "{err}");
    assert!(cfg.pgdata().join("PG_VERSION").is_file(), "los datos no se tocan");
    secrets.set(&password).unwrap();

    // 4. Carpeta de datos incompleta (no creada por el lanzador): se rechaza sin borrarla.
    let foreign = temp_data_dir();
    std::fs::create_dir_all(foreign.join("pgdata")).unwrap();
    std::fs::write(
        foreign.join("pgdata").join("archivo-del-usuario.txt"),
        "no borrar",
    )
    .unwrap();
    let foreign_secrets = FileStore::new(foreign.join("secrets").join("postgresql"));
    let err = Stack::start(&config(foreign.clone()), &foreign_secrets)
        .err()
        .expect("debe rechazarla");
    assert!(err.message.contains("no es una base de datos completa"), "{err}");
    assert!(foreign.join("pgdata").join("archivo-del-usuario.txt").is_file());

    // 5. Base movida a un costado: la nueva reutiliza la contraseña guardada, así la
    //    anterior se sigue pudiendo abrir.
    std::fs::rename(cfg.pgdata(), dir.join("pgdata.anterior")).unwrap();
    let stack = Stack::start(&cfg, &secrets).expect("arranque con base nueva");
    assert!(needs_setup(), "la base nueva empieza vacía");
    assert_eq!(
        secrets.get().unwrap().as_deref(),
        Some(password.as_str()),
        "no se pisa la contraseña"
    );
    stack.stop();

    std::fs::remove_dir_all(&foreign).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
}

#[cfg(windows)]
#[test]
#[ignore = "escribe en el Administrador de credenciales de Windows"]
fn windows_credential_manager_roundtrip() {
    use contador_desktop_lib::secret::CredentialManagerStore;
    let store = CredentialManagerStore::new("ContadorAI-prueba", "ci").unwrap();
    store.delete().unwrap();
    assert_eq!(store.get().unwrap(), None);
    store.set("valor-de-prueba").unwrap();
    assert_eq!(store.get().unwrap().as_deref(), Some("valor-de-prueba"));
    store.delete().unwrap();
    assert_eq!(store.get().unwrap(), None);
}
