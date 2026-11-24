//! Prueba de copias de seguridad y restauración con binarios reales
//! (PostgreSQL con `pg_dump`, `pg_restore`, `psql` + backend empaquetado).
//!
//! ```text
//! CONTADOR_TEST_PGSQL_BIN=<pgsql/bin> CONTADOR_TEST_BACKEND_EXE=<contador-backend> \
//!   cargo test --test backup -- --ignored --test-threads=1
//! ```
//!
//! Usa puertos propios (PostgreSQL 55451 y 55452, API 8793) para no chocar con una app abierta.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use contador_desktop_lib::backup::{KEEP_AUTO, RestoreTarget, is_auto_backup_name, restore_dump};
use contador_desktop_lib::secret::{FileStore, SecretStore};
use contador_desktop_lib::stack::{Stack, StackConfig, http_get, http_request};

const PG_PORT: u16 = 55451;
const RESTORED_PG_PORT: u16 = 55452;
const API_PORT: u16 = 8793;
const PASSWORD: &str = "Clave-Segura-2026";

fn env_path(name: &str) -> PathBuf {
    PathBuf::from(std::env::var(name).unwrap_or_else(|_| panic!("definir {name} (ver encabezado)")))
}

fn pg_tool(name: &str) -> PathBuf {
    env_path("CONTADOR_TEST_PGSQL_BIN").join(format!("{name}{}", std::env::consts::EXE_SUFFIX))
}

fn temp_dir(prefix: &str) -> PathBuf {
    let mut suffix = [0u8; 6];
    getrandom::fill(&mut suffix).unwrap();
    let name: String = suffix.iter().map(|b| format!("{b:02x}")).collect();
    std::env::temp_dir().join(format!("{prefix}-{name}"))
}

fn auto_dumps(auto_dir: &Path) -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(auto_dir)
        .unwrap()
        .flatten()
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|n| is_auto_backup_name(n))
        .collect();
    names.sort();
    names
}

/// Clúster PostgreSQL desechable (otro `initdb`, otro puerto). Se detiene al soltarlo.
struct ScratchCluster {
    dir: PathBuf,
}

impl ScratchCluster {
    fn start(port: u16, password: &str) -> Self {
        let dir = temp_dir("contador-backup-test-restaurado");
        fs::create_dir_all(&dir).unwrap();
        let pwfile = dir.join("pw.txt");
        fs::write(&pwfile, password).unwrap();
        let initdb = Command::new(pg_tool("initdb"))
            .arg("-D")
            .arg(dir.join("data"))
            .args(["-U", "contador", "-E", "UTF8", "--auth=scram-sha-256"])
            .arg(format!("--pwfile={}", pwfile.display()))
            .args(["--locale=C", "--locale-provider=icu", "--icu-locale=es-PY"])
            .output()
            .unwrap();
        assert!(
            initdb.status.success(),
            "{}",
            String::from_utf8_lossy(&initdb.stderr)
        );
        let cluster = Self { dir };
        // Salida a un archivo, no a un pipe: en Windows `postgres` hereda los handles de
        // `pg_ctl` y `Command::output` esperaría para siempre (mismo motivo que en stack.rs).
        let out_path = cluster.dir.join("pg_ctl.out");
        let out = fs::File::create(&out_path).unwrap();
        let status = Command::new(pg_tool("pg_ctl"))
            .arg("start")
            .arg("-D")
            .arg(cluster.dir.join("data"))
            .args(["-w", "-t", "60", "-l"])
            .arg(cluster.dir.join("pg.log"))
            .arg("-o")
            .arg(format!(
                "-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories="
            ))
            .stdin(Stdio::null())
            .stdout(out.try_clone().unwrap())
            .stderr(out)
            .status()
            .unwrap();
        assert!(
            status.success(),
            "{}",
            fs::read_to_string(&out_path).unwrap_or_default()
        );
        cluster
    }
}

impl Drop for ScratchCluster {
    fn drop(&mut self) {
        let _ = Command::new(pg_tool("pg_ctl"))
            .arg("stop")
            .arg("-D")
            .arg(self.dir.join("data"))
            .args(["-m", "immediate", "-w"])
            .output();
        let _ = fs::remove_dir_all(&self.dir);
    }
}

/// Backend atado a la prueba: se mata al soltarlo.
struct Backend(Child);

impl Drop for Backend {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

/// Borra la carpeta de datos al terminar, aunque la prueba falle.
struct Cleanup(PathBuf);

impl Drop for Cleanup {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn psql_scalar(port: u16, database: &str, password: &str, sql: &str) -> String {
    let out = Command::new(pg_tool("psql"))
        .args([
            "-h",
            "127.0.0.1",
            "-p",
            &port.to_string(),
            "-U",
            "contador",
            "-d",
            database,
        ])
        .args(["--no-password", "-tA", "-c", sql])
        .env("PGPASSWORD", password)
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    String::from_utf8_lossy(&out.stdout).trim().to_string()
}

#[test]
#[ignore = "requiere binarios de PostgreSQL y del backend"]
fn daily_backup_retention_and_restore() {
    let dir = temp_dir("contador-backup-test");
    let _cleanup = Cleanup(dir.clone());
    let cfg = StackConfig {
        pg_bin: env_path("CONTADOR_TEST_PGSQL_BIN"),
        backend_exe: env_path("CONTADOR_TEST_BACKEND_EXE"),
        data_dir: dir.clone(),
        pg_port: PG_PORT,
        api_port: API_PORT,
        startup_timeout: Duration::from_secs(180),
    };
    let secrets = FileStore::new(dir.join("secrets").join("postgresql"));
    let auto_dir = dir.join("backups").join("auto");

    // Datos: la organización de prueba, creada por la API como en la app.
    let stack = Stack::start(&cfg, &secrets).expect("arranque");
    let setup = format!(
        r#"{{"organization":{{"legal_name":"Empresa de copia de seguridad","legal_form":"EAS"}},
        "owner":{{"full_name":"Prueba","email":"copia@example.com","password":"{PASSWORD}"}}}}"#
    );
    let (code, body) = http_request(API_PORT, "POST", "/api/v1/system/setup", Some(&setup)).unwrap();
    assert_eq!(code, 201, "{body}");
    let job = stack.backup_job();
    let db_password = secrets.get().unwrap().unwrap();

    // 1. Primera copia del día: archivo, sin restos, y legible con pg_restore --list.
    let first = job
        .run_if_due()
        .expect("copia")
        .expect("debía crear la copia de hoy");
    assert!(first.starts_with(&auto_dir), "{}", first.display());
    assert!(is_auto_backup_name(first.file_name().unwrap().to_str().unwrap()));
    assert!(fs::metadata(&first).unwrap().len() > 0);
    assert!(
        fs::read_dir(&auto_dir)
            .unwrap()
            .flatten()
            .all(|e| !e.file_name().to_string_lossy().ends_with(".partial")),
        "no debe quedar ningún .partial"
    );
    let list = Command::new(pg_tool("pg_restore"))
        .arg("--list")
        .arg(&first)
        .output()
        .unwrap();
    assert!(list.status.success(), "{}", String::from_utf8_lossy(&list.stderr));
    assert!(
        String::from_utf8_lossy(&list.stdout).contains("organizations"),
        "el índice de la copia debe incluir la tabla de organizaciones"
    );
    let log = fs::read_to_string(dir.join("logs").join("backup.log")).unwrap();
    assert!(log.contains("Copia terminada"), "{log}");
    assert!(
        !log.contains(&db_password),
        "la contraseña no debe quedar en el registro"
    );

    // 2. Segunda llamada el mismo día: no crea otra copia.
    assert!(job.run_if_due().expect("segunda llamada").is_none());
    assert_eq!(auto_dumps(&auto_dir).len(), 1);

    // 3. Retención: 15 copias falsas viejas + 1 real = 16; la copia forzada hace 17 y se
    //    conservan 14, así que se borran las 3 más antiguas. Lo ajeno no se toca.
    let fakes: Vec<String> = (1..=15)
        .map(|d| format!("contador-202001{d:02}-000000.dump"))
        .collect();
    for name in &fakes {
        fs::write(auto_dir.join(name), "falsa").unwrap();
    }
    let foreign_file = auto_dir.join("contador-manual.dump");
    let foreign_bak = auto_dir.join("contador-20200101-000000.dump.bak");
    fs::write(&foreign_file, "ajena").unwrap();
    fs::write(&foreign_bak, "ajena").unwrap();
    let manual_dir = dir.join("backups").join("manual");
    fs::create_dir_all(&manual_dir).unwrap();
    fs::write(manual_dir.join("contador-20200101-000000.dump"), "ajena").unwrap();
    // Un .partial de una copia interrumpida (se limpia) y otro ajeno (se respeta).
    let stale = auto_dir.join("contador-20200102-000000.dump.partial");
    let foreign_partial = auto_dir.join("otro.partial");
    fs::write(&stale, "a medias").unwrap();
    fs::write(&foreign_partial, "ajeno").unwrap();

    std::thread::sleep(Duration::from_millis(1100)); // el nombre lleva segundos
    let second = stack.backup().expect("copia forzada");
    assert_ne!(second, first);
    let left = auto_dumps(&auto_dir);
    assert_eq!(left.len(), KEEP_AUTO, "{left:?}");
    for gone in &fakes[..3] {
        assert!(!left.contains(gone), "{gone} debía borrarse");
    }
    for kept in &fakes[3..] {
        assert!(left.contains(kept), "{kept} debía conservarse");
    }
    assert!(
        first.is_file() && second.is_file(),
        "las copias reales sobreviven"
    );
    assert!(foreign_file.is_file() && foreign_bak.is_file() && foreign_partial.is_file());
    assert!(manual_dir.join("contador-20200101-000000.dump").is_file());
    assert!(!stale.exists(), "el .partial de una copia interrumpida se limpia");

    // 4. Restaurar nunca pisa una base existente: 'contador' ya existe y sigue intacta.
    let restore_log = dir.join("logs").join("restauracion.log");
    let live = RestoreTarget {
        port: PG_PORT,
        user: "contador",
        password: &db_password,
        database: "contador",
    };
    let err = restore_dump(&cfg.pg_bin, &first, &live, &restore_log).expect_err("debe rechazarla");
    assert!(err.message.contains("ya existe"), "{err}");
    assert_eq!(
        psql_scalar(
            PG_PORT,
            "contador",
            &db_password,
            "select count(*) from core.organizations"
        ),
        "1"
    );

    // 5. Restaurar en un clúster nuevo (otro initdb, otro puerto) y comprobar los datos.
    let _restored = ScratchCluster::start(RESTORED_PG_PORT, "clave-del-cluster-nuevo");
    let target = RestoreTarget {
        port: RESTORED_PG_PORT,
        user: "contador",
        password: "clave-del-cluster-nuevo",
        database: "contador",
    };
    restore_dump(&cfg.pg_bin, &first, &target, &restore_log).expect("restauración");
    assert_eq!(
        psql_scalar(
            RESTORED_PG_PORT,
            "contador",
            "clave-del-cluster-nuevo",
            "select legal_name from core.organizations"
        ),
        "Empresa de copia de seguridad"
    );
    // Segunda restauración sobre la misma base: rechazada, los datos siguen.
    assert!(restore_dump(&cfg.pg_bin, &first, &target, &restore_log).is_err());
    assert_eq!(
        psql_scalar(
            RESTORED_PG_PORT,
            "contador",
            "clave-del-cluster-nuevo",
            "select count(*) from core.users"
        ),
        "1"
    );
    // Una copia ilegible se rechaza y no deja una base a medias.
    let broken = dir.join("rota.dump");
    fs::write(&broken, "esto no es una copia").unwrap();
    let scratch = RestoreTarget {
        database: "prueba_rota",
        ..target
    };
    assert!(restore_dump(&cfg.pg_bin, &broken, &scratch, &restore_log).is_err());
    assert_eq!(
        psql_scalar(
            RESTORED_PG_PORT,
            "contador",
            "clave-del-cluster-nuevo",
            "select count(*) from pg_database where datname = 'prueba_rota'"
        ),
        "0"
    );

    // 6. El backend arranca sobre la base restaurada y el propietario puede ingresar.
    stack.stop();
    let backend_log = fs::File::create(dir.join("backend-restaurado.log")).unwrap();
    let child = Command::new(&cfg.backend_exe)
        .env("CONTADOR_ENV", "production")
        .env(
            "CONTADOR_DATABASE_URL",
            format!(
                "postgresql+psycopg://contador:clave-del-cluster-nuevo@127.0.0.1:{RESTORED_PG_PORT}/contador"
            ),
        )
        .env("CONTADOR_API_HOST", "127.0.0.1")
        .env("CONTADOR_API_PORT", API_PORT.to_string())
        .stdin(Stdio::null())
        .stdout(backend_log.try_clone().unwrap())
        .stderr(backend_log)
        .spawn()
        .unwrap();
    let _backend = Backend(child);
    let deadline = Instant::now() + Duration::from_secs(120);
    while !http_get(API_PORT, "/api/v1/system/health").is_ok_and(|(code, _)| code == 200) {
        assert!(
            Instant::now() < deadline,
            "el backend no respondió sobre la base restaurada"
        );
        std::thread::sleep(Duration::from_millis(300));
    }
    let (_, body) = http_get(API_PORT, "/api/v1/system/setup").unwrap();
    assert!(body.contains("\"needs_setup\":false"), "{body}");
    let login = format!(r#"{{"email":"copia@example.com","password":"{PASSWORD}"}}"#);
    let (code, body) = http_request(API_PORT, "POST", "/api/v1/auth/login", Some(&login)).unwrap();
    assert_eq!(code, 200, "{body}");

    // 7. Una copia fallida (la base ya está detenida) borra solo su .partial, deja el error en
    //    el registro y no toca las copias existentes.
    let before = auto_dumps(&auto_dir);
    std::thread::sleep(Duration::from_millis(1100));
    let err = job.run().expect_err("sin base no hay copia");
    assert!(err.message.contains("No se pudo hacer la copia"), "{err}");
    assert_eq!(auto_dumps(&auto_dir), before, "las copias existentes no cambian");
    assert!(
        fs::read_dir(&auto_dir)
            .unwrap()
            .flatten()
            .all(|e| e.file_name().to_string_lossy() == "otro.partial"
                || !e.file_name().to_string_lossy().ends_with(".partial")),
        "solo debe sobrevivir el .partial ajeno"
    );
    assert!(foreign_partial.is_file());
    let log = fs::read_to_string(dir.join("logs").join("backup.log")).unwrap();
    assert!(log.contains("ERROR"), "{log}");
}
