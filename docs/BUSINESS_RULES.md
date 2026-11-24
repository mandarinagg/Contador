# Reglas de negocio

Cada regla tiene un identificador estable, su estado y dónde se hace cumplir. **Implementada** = tiene código y prueba automatizada.

## Identidad y acceso

| ID | Regla | Estado | Dónde |
|---|---|---|---|
| BR-ID-01 | La configuración inicial solo se puede hacer con la base sin usuarios; crea la organización y su propietario | Implementada | `system/router.py` (candado `contador.setup`), `test_setup_creates_owner_once` |
| BR-ID-02 | Contraseña de 12 a 256 caracteres, con al menos 3 de: minúsculas, mayúsculas, números, símbolos; sin espacios al inicio o final | Implementada | `identity/schemas.py`, `test_setup_rejects_weak_password` |
| BR-ID-03 | 5 intentos fallidos bloquean la cuenta 15 minutos | Implementada | `identity/service.login`, `test_lockout_after_repeated_failures` |
| BR-ID-04 | El error de ingreso no revela si el email existe | Implementada | `test_bad_credentials_do_not_reveal_email` |
| BR-ID-05 | La sesión vence a las 12 h o tras 60 min sin uso | Implementada | `api/deps.get_auth`, `test_expired_and_idle_sessions_are_rejected` |
| BR-ID-06 | Cambiar la contraseña exige la actual y cierra las demás sesiones | Implementada | `test_change_password_*` |
| BR-ID-07 | Desactivar un usuario cierra sus sesiones y le impide ingresar | Implementada | `test_deactivated_user_loses_sessions` |
| BR-ID-08 | Solo un propietario crea, modifica o asigna el rol de propietario | Implementada | `test_admin_cannot_create_or_modify_owners` |
| BR-ID-09 | Siempre queda al menos un propietario activo; nadie se desactiva ni cambia su propio rol | Implementada | `test_last_owner_and_self_protection` |
| BR-ID-10 | Un cambio de rol tiene efecto inmediato en las sesiones abiertas | Implementada | `test_role_change_takes_effect_immediately` |

## Organización

| ID | Regla | Estado | Dónde |
|---|---|---|---|
| BR-ORG-01 | RUC opcional hasta verificarlo; si se carga, va con su DV y el DV debe ser el del módulo 11 de la SET | Implementada | `organizations/router.py`, `ruc.py`, restricciones de la tabla, `test_organization_rejects_wrong_check_digit` |
| BR-ORG-02 | Moneda base PYG | Implementada | Default de la tabla |
| BR-ORG-03 | La aplicación no reemplaza los libros societarios rubricados ni los registros oficiales | Política | PRD, textos de la UI (fase 2) |

## Auditoría

| ID | Regla | Estado | Dónde |
|---|---|---|---|
| BR-AUD-01 | Todo cambio de negocio se audita en la misma transacción, con usuario, fecha, valores anteriores y nuevos (solo campos que cambian) | Implementada | `audit/service.record`, `test_organization_update_*` |
| BR-AUD-02 | La auditoría no se puede modificar ni borrar | Implementada | Triggers, `test_audit_log_is_append_only` |
| BR-AUD-03 | Una alteración de la auditoría es detectable | Implementada | Cadena de hashes, `test_hash_chain_detects_tampering` |
| BR-AUD-04 | Ingresos, fallos, bloqueos, cierres de sesión y cambios de contraseña se registran como eventos de seguridad | Implementada | `audit.security_events` |

## Contabilidad (fase 3 — diseñadas)

| ID | Regla |
|---|---|
| BR-ACC-01 | Un asiento solo se contabiliza si Σ debe = Σ haber (por moneda) y tiene al menos dos líneas |
| BR-ACC-02 | Un asiento contabilizado no se modifica ni se borra; se corrige con un asiento de reversión |
| BR-ACC-03 | No se contabiliza en un período cerrado |
| BR-ACC-04 | Todo asiento registra usuario responsable y documento respaldatorio cuando exista |
| BR-ACC-05 | Ningún cálculo monetario usa punto flotante |
| BR-ACC-06 | Un movimiento importado nunca genera un asiento definitivo sin confirmación humana |

## Finanzas (fase 2)

| ID | Regla | Estado | Dónde |
|---|---|---|---|
| BR-FIN-01 | Personal y empresarial son contextos separados; una operación pertenece a uno solo | Implementada | `finance.contexts` (un `business` por organización, un `personal` por usuario), `test_setup_creates_exactly_one_business_context`, `test_one_business_context_per_organization`, `test_ids_from_another_context_are_not_found` |
| BR-FIN-02 | Lo consolidado identifica el contexto de origen de cada importe | Implementada | `GET /finance/summary/consolidated`, `test_consolidated_identifies_each_context` |
| BR-FIN-03 | La importación detecta duplicados (cuenta, fecha, importe, referencia/descripción normalizada) y pide confirmación | Implementada | `finance/normalize.py` (`dedupe_key`), `finance/imports.py`, `test_dedupe_key_ignores_case_accents_spaces_and_scale`, `test_csv_utf8_semicolon_errors_and_duplicates`, `test_duplicates_appearing_after_preview_block_commit` |
| BR-FIN-04 | Las finanzas personales solo las ve y opera su dueño, sin importar el rol (D-024) | Implementada | `finance/service.resolve_context` (404), filtro `finance.personal.*` en `audit/service.list_logs`, `test_personal_context_is_invisible_to_everyone_else`, `test_viewer_reads_business_but_writes_only_personal`, `test_personal_audit_is_private_to_its_owner` |
| BR-FIN-05 | Un movimiento no puede usar cuenta, categoría o contraparte de otro contexto ni otra moneda que la de su cuenta: lo impide la base (D-025) | Implementada | Claves foráneas compuestas de `finance.transactions`, `test_personal_transaction_cannot_use_business_account`, `test_transaction_cannot_use_category_or_counterparty_of_other_context`, `test_transaction_currency_must_match_account` |
| BR-FIN-06 | Importes en decimal exacto; no se suman ni convierten monedas distintas (D-026) | Implementada | `finance/money.py`, `NUMERIC(18,2)`, `ck_*_pyg_integer`, `test_decimal_arithmetic_is_exact`, `test_amounts_are_strings_and_exact`, `test_float_and_bad_decimals_are_rejected`, `test_summary_never_mixes_currencies` |
| BR-FIN-07 | Nada se borra: los movimientos se anulan con motivo y el resto se archiva; todo queda auditado (D-027) | Implementada | `ck_transactions_void_*`, `test_void_excludes_from_balance_and_summary_and_is_audited`, `test_account_archive_and_names`, `test_each_entity_audits_creation_and_only_changed_fields` |
| BR-FIN-08 | Una importación no crea movimientos hasta que el usuario confirma el lote; confirmar dos veces no duplica | Implementada | `finance/imports.py`, `test_commit_is_idempotent_and_audited_once`, `test_cancel` |
| BR-FIN-09 | Las transferencias entre cuentas propias no son ingreso ni gasto; un aporte entre contextos no es una transferencia | Implementada | `transfer_group_id`, `ck_transactions_transfer_without_category`, `test_transfer_creates_two_linked_movements_outside_income_and_expense`, `test_consolidated_identifies_each_context` |

## Tributación (fase 4 — diseñadas)

| ID | Regla |
|---|---|
| BR-TAX-01 | Ninguna obligación, tasa ni vencimiento se activa sin una regla con fuente oficial y estado `verified` |
| BR-TAX-02 | Todo cálculo indica la versión de la regla aplicada y su vigencia |
| BR-TAX-03 | Un cálculo es una estimación interna, nunca una declaración oficial; la presentación es manual en Marangatu |

## Facturación (fase 5 — diseñadas)

| ID | Regla |
|---|---|
| BR-BIL-01 | Una factura no está aprobada hasta que el SIFEN responde `Aprobado` u `Aprobado con observación` |
| BR-BIL-02 | Solo un documento aprobado genera asiento definitivo y base imponible |
| BR-BIL-03 | El ambiente de producción se activa solo por el propietario, con auditoría |

## IA (fase 6 — diseñadas)

| ID | Regla |
|---|---|
| BR-AI-01 | La IA solo accede a datos mediante herramientas del backend con los permisos del usuario que conversa |
| BR-AI-02 | La IA solo crea borradores; un humano aprueba |
| BR-AI-03 | La IA no presenta declaraciones ni ejecuta operaciones irreversibles |
| BR-AI-04 | Cada respuesta distingue datos reales, estimados, incompletos y recomendaciones |
