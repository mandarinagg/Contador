# Seguridad

## Modelo de amenazas (resumen)

| Activo | Amenaza | Control |
|---|---|---|
| Datos contables y personales | Acceso de otro usuario de la PC, robo del equipo | Autenticación; API solo en 127.0.0.1; (fase 8) datos de PostgreSQL en la carpeta del usuario, cifrado de disco recomendado, copias cifradas |
| Cuentas de usuario | Adivinación de contraseñas | Argon2id, política de contraseñas, bloqueo tras 5 fallos, mensajes que no revelan emails |
| Sesiones | Robo o reutilización del token | Token opaco de 256 bits, solo el hash en la base, vencimiento absoluto e inactividad, revocación inmediata |
| Auditoría | Ocultar cambios | Solo inserción + cadena de hashes verificable |
| Certificado de firma y CSC (fase 5) | Robo | AES-256-GCM con clave fuera de la base (almacén seguro del SO), atado a la organización |
| API key de Claude (fase 6) | Filtración | Solo en el backend, en el almacén seguro del SO; nunca en el frontend ni en prompts |
| Datos enviados a Claude (fase 6) | Exposición excesiva | Herramientas con permisos, minimización, registro de cada llamada |
| WebView | Inyección de scripts | CSP estricta en Tauri, React escapa por defecto, sin HTML dinámico |

## Controles implementados (fase 1)

- **Autenticación:** `POST /auth/login` con Argon2id (parámetros por defecto de argon2-cffi, RFC 9106) y rehash automático si cambian los parámetros. Comparación con hash ficticio cuando el email no existe (tiempo de respuesta parejo).
- **Sesiones:** `core.user_sessions` guarda `sha256(token)`. TTL 12 h, inactividad 60 min (configurables). El cierre de sesión, la desactivación del usuario y el cambio de contraseña revocan sesiones.
- **Autorización:** permisos por rol cargados desde la base en cada pedido (`require(Perm.X)`); un cambio de rol aplica de inmediato. La organización activa sale de la sesión, nunca del cliente.
- **Validación:** Pydantic en cada entrada (longitudes, patrones, enums); restricciones CHECK y UNIQUE en la base como segunda barrera.
- **Errores:** sin trazas ni SQL en las respuestas; los errores inesperados se registran con `request_id`.
- **Logging:** JSON con redacción de claves sensibles (`password`, `token`, `authorization`, `secret`, `api_key`, `csc`). No se registran cuerpos de pedidos.
- **Cabeceras:** `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `X-Request-Id`.
- **CORS:** solo el frontend de desarrollo y los orígenes de Tauri.
- **Documentación de la API** (`/docs`, `/openapi.json`) deshabilitada con `CONTADOR_ENV=production`.
- **Eventos de seguridad:** configuración inicial, ingreso, fallo (con motivo interno), bloqueo, intento bloqueado, cierre de sesión, cambio de contraseña.
- **Tauri:** CSP `default-src 'self'; connect-src 'self' http://127.0.0.1:8765; ...` y capacidades mínimas (`core:default`).

## Secretos

| Secreto | Dónde vive | Estado |
|---|---|---|
| Contraseña de PostgreSQL (desarrollo) | `docker-compose.yml` (`contador_dev`, solo localhost) | Solo desarrollo |
| `CONTADOR_DATABASE_URL` | `backend/.env` (ignorado por git) | — |
| `CONTADOR_SECRETS_KEY` | Almacén seguro del SO (Windows Credential Manager / Secret Service) | Fase 5 |
| `ANTHROPIC_API_KEY` | Almacén seguro del SO, leída solo por el backend | Fase 6 |
| Certificado `.p12` de la empresa | Nunca se guarda el archivo ni su contraseña; solo la clave privada cifrada | Fase 5 (diseño heredado del proyecto SIFEN) |

`.gitignore` excluye `.env*`, `*.p12`, `*.pfx`, `*.pem`, `*.key`, `data/` y `backups/`.

## Repositorio público

`github.com/mandarinagg/Contador` es **público** (decisión del propietario, 2026-11-23: Actions sin costo). Todo lo que se sube queda visible y puede quedar en cachés aunque después se borre. Reglas:

1. **Nunca** al repositorio: `.env`, API keys, certificados (`.p12`, `.pfx`, `.pem`, `.key`), CSC, contraseñas reales, copias de la base, extractos bancarios, facturas, constancias, datos de clientes o empleados. `.gitignore` excluye los tipos conocidos.
2. Los secretos de la app viven en el **Administrador de credenciales de Windows** de la PC donde se usa, nunca en archivos del proyecto.
3. **Hook pre-commit** (`scripts/check-secrets.sh --install`, una vez por clon): revisa cada commit con gitleaks y lo cancela si encuentra un secreto. El CI repite la revisión sobre todo el historial (job `secrets`).
4. Falsos positivos de pruebas: se agregan **uno por uno** en `.gitleaks.toml`, con el valor exacto.
5. Los ejemplos y pruebas usan datos ficticios (`example.com`, RUC del manual técnico `44444401-7`).
6. Commits con el email privado de GitHub (`<id>+<usuario>@users.noreply.github.com`), no con un email personal o laboral.
7. **Si se sube un secreto por error:** borrarlo del repo no alcanza. Hay que **revocarlo y generar uno nuevo** de inmediato (API key, certificado, contraseña).
8. Antes de copiar el núcleo SIFEN del proyecto de facturación (fase 5), confirmar que se puede publicar ese código.

## Pendientes

- Rol de base de datos de mínimo privilegio para la app (sin `ALTER`/`DISABLE TRIGGER`), distinto del dueño de las tablas (fase 8, junto con el PostgreSQL empaquetado).
- Secreto por proceso entre Tauri y el backend para que otros procesos locales no hablen con la API (fase 8).
- Copias de seguridad cifradas y prueba de restauración (fase 8).
- Revisión de dependencias automatizada (`pip-audit`, `npm audit`) en CI.
