# Especificación de la API local

Base: `http://127.0.0.1:8765/api/v1`. JSON. Autenticación: `Authorization: Bearer <token>`.
La especificación OpenAPI completa y navegable está en `http://127.0.0.1:8765/docs` (solo fuera de producción).

## Convenciones

- **Errores:** `{"error": {"code": "CODIGO", "message": "texto para la persona", "details": ...}}`.
- **Validación (422):** `code = VALIDATION_ERROR`, `details = [{"field": "owner.password", "message": "..."}]`.
- **Trazabilidad:** toda respuesta trae `X-Request-Id`; se puede enviar uno propio (8-64 caracteres ASCII).
- **Fechas:** ISO 8601 con zona horaria. **Importes (desde fase 2):** string decimal + `currency`.

| HTTP | Códigos |
|---|---|
| 400 | `INVALID_CURRENT_PASSWORD`, `PASSWORD_REUSED`, `SELF_CHANGE_FORBIDDEN` |
| 401 | `NOT_AUTHENTICATED`, `SESSION_EXPIRED`, `INVALID_CREDENTIALS` |
| 403 | `FORBIDDEN` (`details.missing` = permisos faltantes), `OWNER_ONLY` |
| 404 | `USER_NOT_FOUND`, `NOT_FOUND` |
| 409 | `ALREADY_SET_UP`, `EMAIL_TAKEN`, `LAST_OWNER` |
| 422 | `VALIDATION_ERROR` |
| 423 | `ACCOUNT_LOCKED` (`details.locked_until`) |
| 500 | `INTERNAL_ERROR` |

## Sistema

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/system/health` | — | `{status, database, version}` |
| GET | `/system/setup` | — | `{needs_setup: bool}` |
| POST | `/system/setup` | — (solo con la base vacía) | Crea organización + propietario. Cuerpo: `{organization: {legal_name, trade_name?, legal_form}, owner: {full_name, email, password}}`. Responde como `/auth/login` (201) |

## Autenticación

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| POST | `/auth/login` | — | `{email, password}` → `{token, expires_at, user, organization, role, permissions[]}` |
| POST | `/auth/logout` | sesión | Revoca la sesión actual (204) |
| GET | `/auth/me` | sesión | `{user, organization, role, permissions[]}` |
| POST | `/auth/change-password` | sesión | `{current_password, new_password}` (204). Cierra las demás sesiones |

## Usuarios

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/users` | `users.read` | Miembros de la organización: `[{user, role, member_since}]` |
| POST | `/users` | `users.manage` | `{email, full_name, password, role}` → 201. Crear `owner` exige ser `owner` |
| PATCH | `/users/{id}` | `users.manage` | `{role?, is_active?}`. Reglas BR-ID-08/09 |
| GET | `/users/roles` | `users.read` | Roles con sus permisos |
| GET | `/users/permissions` | `users.read` | Catálogo `{codigo: descripcion}` |

## Organización

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/organization` | `organization.read` | Datos de la organización activa |
| PATCH | `/organization` | `organization.manage` | `{legal_name?, trade_name?, legal_form?, ruc?, ruc_check_digit?}`; RUC y DV van juntos y se valida el DV |

## Auditoría

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| GET | `/audit/logs` | `audit.read` | `?limit=1..200&before_seq=&entity_type=&action=`; orden descendente por `seq` (paginación por cursor) |
| GET | `/audit/security-events` | `audit.read` | `?limit=1..200` |
| GET | `/audit/verify` | `audit.read` | `{valid, checked, first_broken_seq}` |

## Acciones auditadas
`system.setup`, `organization.updated`, `user.created`, `user.updated`.
