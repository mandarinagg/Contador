# Registro de decisiones (ADR)

Formato: contexto → decisión → alternativas → consecuencias. Estado: **Aceptada**, **Propuesta** (requiere confirmación del propietario) o **Reemplazada**.

## D-001 — Repositorio de trabajo
**Aceptada · 2026-11-23.** Se trabaja en `proyectos/Contador/Contador` (clon de `mandarinagg/Contador`). El `.git` de la carpeta superior es un `git init` sin remoto; no se toca.

## D-002 — Estructura por módulos verticales
**Aceptada.** Cada dominio del backend es un paquete con `models`, `schemas`, `service` y `router`. Sin carpeta `database/` (Alembic en `backend/migrations` es la única fuente del esquema). Alternativa descartada: capas horizontales globales (más saltos entre carpetas por cambio). Detalle en `ARCHITECTURE.md`.

## D-003 — PostgreSQL 18
**Aceptada.** Se usa PostgreSQL 18 (`uuidv7()` y `sha256()` nativos). UUIDv7 da PK ordenadas por tiempo (índices más compactos que UUIDv4) sin extensiones. Consecuencia: la distribución debe empaquetar PostgreSQL ≥ 18.

## D-004 — SQLAlchemy y FastAPI en modo síncrono
**Aceptada.** Uso local con pocos usuarios: el modo síncrono simplifica transacciones, triggers, candados y pruebas (rollback por prueba). Lo asíncrono se reserva para trabajos largos en un worker. Alternativa: async con asyncpg (más complejidad sin beneficio medible aquí).

## D-005 — Dinero
**Aceptada (se implementa en fase 2).** `NUMERIC(20,4)` + código de moneda ISO 4217 en cada importe; `Decimal` en Python; en el frontend los importes viajan como **string** decimal, nunca `number`. El redondeo a la unidad mínima (PYG = 0 decimales) se hace al contabilizar, con reglas explícitas. Las tasas de IVA del SIFEN usan 8 decimales en el XML (lo resuelve el servicio SIFEN).

## D-006 — Autenticación con sesiones opacas
**Aceptada.** Token aleatorio de 256 bits; la base guarda solo su SHA-256. Vencimiento absoluto (12 h) e inactividad (60 min), revocables al instante (cerrar sesión, desactivar usuario, cambiar contraseña). Contraseñas con Argon2id. Bloqueo de 15 min tras 5 intentos fallidos. Mismo mensaje para email inexistente y contraseña errónea. Alternativa descartada: JWT (no se revocan sin una lista negra, que es una tabla de sesiones igual).

## D-007 — Facturación: reutilizar el núcleo SIFEN como servicio Node
**Propuesta · requiere confirmación.** El núcleo `sifen/*` del proyecto existente se copia sin cambios a `services/sifen/` y se expone por HTTP local; el backend Python lo usa mediante un adaptador. Alternativas: (a) portar a Python con `lxml`/`signxml`/`cryptography` — descartada por reintroducir riesgos ya resueltos y probados; (b) integrar NestJS completo — descartada, arrastra el CRM. Consecuencia: un segundo runtime en el instalador (ver R-02). Detalle en `INTEGRATIONS.md`.

## D-008 — Auditoría inmutable con cadena de hashes
**Aceptada.** `audit.audit_logs` y `audit.security_events` son de solo inserción (triggers rechazan UPDATE, DELETE y TRUNCATE). Cada fila de `audit_logs` incluye el SHA-256 de la anterior, calculado por la base bajo un candado transaccional; `GET /audit/verify` recalcula la cadena. Protege contra modificaciones ordinarias y hace **evidente** una alteración hecha por alguien con control total de la base (que puede desactivar triggers). Sin FK hacia usuarios/organizaciones: la auditoría sobrevive al borrado.

## D-009 — Configuración inicial en lugar de usuario por defecto
**Aceptada.** Con la base vacía, `POST /system/setup` crea la organización y su propietario; después responde 409. No existe contraseña por defecto. Riesgo aceptado: hasta completar la configuración, cualquier proceso local podría hacerla (la API escucha solo en 127.0.0.1); en fase 8 Tauri hará la configuración inicial en el primer arranque.

## D-010 — Roles iniciales
**Aceptada (el propietario puede ajustarla).** Propietario y Administrador: todo; solo un Propietario crea, modifica o asigna Propietarios. Contador: lectura de organización, usuarios y auditoría (ganará permisos contables en fase 3). Consulta: solo lectura de la organización. Siempre queda al menos un propietario activo; nadie cambia su propio rol ni se desactiva.

## D-011 — Gestores de paquetes
**Aceptada.** `npm` (viene con Node, plantilla oficial) y `venv` + `pip` con versiones fijas. pnpm/uv/poetry no aportan lo suficiente para sumar herramientas.

## D-012 — Cliente de pruebas `httpx2`
**Aceptada.** Starlette depreca `httpx` en su `TestClient` en favor de `httpx2`; se usa `httpx2` para no arrastrar advertencias.

## D-013 — Pruebas contra PostgreSQL real
**Aceptada.** Sin SQLite ni mocks de base: triggers, `uuidv7()`, índices parciales y candados solo existen en PostgreSQL. Cada prueba corre en una transacción revertida.

## D-014 — Token en `sessionStorage`
**Aceptada.** Sobrevive a recargas de la ventana pero no a cerrar la app; no se comparte entre ventanas. Ningún dato de negocio se guarda en el navegador. En fase 8 se evaluará pasar el token por el proceso Rust.

## D-015 — Identidad visual
**Aceptada.** Verde de libro mayor como primario, lapacho (árbol nacional) como color de marca usado en un solo lugar, IBM Plex Sans con cifras tabulares, doble raya contable como firma visual. Detalle en `ARCHITECTURE.md § Sistema de diseño`.

## D-016 — Plataforma objetivo: Windows 11, una sola PC
**Aceptada · 2026-11-23 (propietario).** La app se desarrolla en Linux y se usa en **una** PC con Windows 11. Consecuencias: no hace falta servidor ni base compartida en red; la base PostgreSQL vive en esa PC. Linux pasa a ser solo plataforma de desarrollo (los instaladores Linux quedan como opcionales). Los datos cargados en la PC de desarrollo son **solo de prueba**: los datos reales se cargan directamente en la PC de Windows.

## D-017 — Distribución adelantada (antes de la fase 2)
**Aceptada.** El empaquetado estaba en la fase 8. Como el uso real es en otra PC, se adelanta a una **fase 1B**: instalador mínimo para Windows que levanta PostgreSQL portable, el backend y la interfaz. Así se resuelve temprano el riesgo principal (R-01) y cada fase nueva llega a Windows como actualización.

## D-018 — Compilar Windows en GitHub Actions
**Aceptada (requiere autorización para subir el código).** Tauri no genera instaladores de Windows de forma soportada desde Linux. Los instaladores se arman en un runner `windows-latest` de GitHub Actions y se descargan como artefacto. Alternativa descartada: compilar en una PC con Windows (obliga a instalar Rust, Build Tools, Node y Python ahí). **Atención:** el repositorio `mandarinagg/Contador` es **público**; se recomienda hacerlo privado antes del primer push (Actions sigue siendo gratis dentro del cupo mensual).

## D-019 — Backend empaquetado con PyInstaller en modo carpeta
**Aceptada.** `backend/packaging/contador-backend.spec` genera `dist/contador-backend/` (≈ 83 MB en Linux). Modo carpeta en lugar de archivo único: arranca más rápido (no se descomprime en cada inicio) y genera menos falsos positivos de antivirus en Windows. Tauri lo incluye como recurso y lo lanza. El ejecutable aplica las migraciones al arrancar (`python -m app`). Verificado en Linux: migración de base vacía, configuración inicial e ingreso.

## D-020 — PostgreSQL portable de EDB
**Aceptada.** Se empaquetan los binarios oficiales para Windows de EDB (`postgresql-18.7-1-windows-x64-binaries.zip`, la misma versión que en desarrollo), recortados a `bin`, `lib` y `share` (sin pgAdmin, documentación ni StackBuilder). Datos en `%LOCALAPPDATA%\ContadorAI\pgdata`, solo `127.0.0.1`, autenticación `scram-sha-256` con contraseña aleatoria guardada en el Administrador de credenciales de Windows.

## D-021 — Datos fuera de la carpeta del identificador
**Aceptada.** La base vive en `%LOCALAPPDATA%\ContadorAI` y no en `%LOCALAPPDATA%\py.contadorai.desktop`: el desinstalador de Tauri ofrece "borrar datos de la aplicación" sobre la carpeta del identificador, y la contabilidad no debe poder borrarse con un clic al desinstalar. El CI verifica que desinstalar deja los datos.

## D-022 — Lanzador en Rust (`desktop/src-tauri/src/stack.rs`)
**Aceptada.** Sin dependencias de red extra (HTTP mínimo sobre `TcpStream` para el chequeo de salud). Reglas: nunca borra una carpeta de datos existente (la creación inicial ocurre en `pgdata.init` y se renombra al terminar); contraseña aleatoria de 256 bits en el Administrador de credenciales (`ContadorAI` / `postgresql`); PostgreSQL solo TCP en `127.0.0.1:55440`, sin sockets Unix, `scram-sha-256`, ICU `es-PY` para ordenar en español; backend atado a la app con un *job object* de Windows (muere con ella aunque la app falle); si PostgreSQL quedó en marcha tras un cierre brusco, se reutiliza; una sola instancia de la app. Fuera de Windows (solo desarrollo) la contraseña va a un archivo `0600`.

## D-023 a D-027 — Modelo de finanzas (fase 2)
**Aceptadas · 2026-11-24.** Detalle y motivos en [`specs/FASE2_FINANZAS.md`](specs/FASE2_FINANZAS.md) §1: contextos `business` (uno por organización) y `personal` (uno por usuario) (D-023); finanzas personales privadas de su dueño sin importar el rol (D-024); separación impuesta en la base con claves foráneas compuestas, incluida la moneda (D-025); importes `NUMERIC(18,2)`/`Decimal`/string, sin mezclar monedas (D-026); nada se borra, se anula o archiva con auditoría (D-027).

## D-028 — Equipo de agentes
**Aceptada · 2026-11-24 (autorizada por el propietario).** El trabajo se reparte entre agentes especializados, cada uno en su propio *worktree* de git y con su propia base de pruebas (`contador_test_<agente>`), bajo una especificación escrita por el jefe de proyecto. El jefe revisa, corre todas las pruebas e integra en `main`; ningún agente decide el modelo de datos ni sube código por su cuenta.
