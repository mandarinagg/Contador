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

## Contabilidad (fase 3 — núcleo en `docs/specs/FASE3_CONTABILIDAD.md`, 3B en `docs/specs/FASE3B_CONTABILIDAD.md`)

| ID | Regla | Estado | Dónde |
|---|---|---|---|
| BR-ACC-01 | Un asiento solo se contabiliza si Σ debe = Σ haber en guaraníes (moneda funcional, D-036) y tiene al menos dos líneas | Implementada | Trigger `journal_entries_guard` (`trg_journal_entries_unbalanced`, `_min_lines`), `entries._check_postable`, `test_posting_unbalanced_single_line_or_in_closed_period_fails`, `test_draft_can_be_unbalanced_and_is_edited_only_while_draft`, `test_posting_errors_are_readable` |
| BR-ACC-02 | Un asiento contabilizado no se modifica ni se borra; se corrige con un asiento de reversión | Implementada | Triggers `journal_entries_guard` (`_posted_immutable`, `_final`, `_no_delete`, `_reversal_missing`, `_reversal_mismatch`) y `journal_lines_guard` (`_entry_not_draft`), `TRUNCATE` prohibido, `test_update_and_delete_of_posted_entry_fail`, `test_lines_of_posted_entry_cannot_change`, `test_reversal_lines_must_mirror_the_original`, `test_reversal_inverts_lines_and_nets_ledger_to_zero` |
| BR-ACC-03 | No se contabiliza en un período cerrado | Implementada | `trg_journal_entries_period_closed`, `_year_closed`, `trg_periods_year_closed`, `test_posting_unbalanced_single_line_or_in_closed_period_fails`, `test_reversal_in_closed_period_asks_for_another_date`, `test_closing_the_fiscal_year` |
| BR-ACC-04 | Todo asiento registra usuario responsable y documento respaldatorio cuando exista | Implementada | `created_by`, `posted_by`/`posted_at` (`ck_journal_entries_posted_complete`), `document_reference`, auditoría `accounting.journal_entry.*`, `test_draft_can_be_unbalanced_and_is_edited_only_while_draft`, `test_proposed_draft_has_bank_against_category_with_the_right_sign` |
| BR-ACC-05 | Ningún cálculo monetario usa punto flotante | Implementada | `Decimal` en todo el módulo, `NUMERIC(18,2)` y `ck_journal_lines_pyg_integer`, importes y cotizaciones como string en JSON, `test_line_validation`, `test_foreign_currency_needs_a_rate_and_never_rounds_silently` |
| BR-ACC-06 | Un movimiento importado nunca genera un asiento definitivo sin confirmación humana | Implementada | `finance_link.propose_from_transaction` crea solo borradores; `trg_journal_entries_insert_draft`, `test_proposed_draft_has_bank_against_category_with_the_right_sign` |
| BR-ACC-07 | La contabilidad es de la empresa: un movimiento personal nunca origina un asiento (D-035) | Implementada | `ck_journal_entries_source_business_only`, FK `(source_context_id, source_context_kind) → finance.contexts (id, kind)`, FK `(source_transaction_id, source_context_id) → finance.transactions (id, context_id)` (D-044), `test_entry_from_personal_context_is_rejected_by_database`, `test_personal_transaction_is_not_found_for_accounting`, `test_ledger_accounts_are_assigned_only_in_business_and_with_the_right_kind`, `test_transactions_show_their_journal_entry_only_in_business` |
| BR-ACC-08 | Los asientos contabilizados llevan número correlativo por ejercicio, sin huecos (D-040) | Implementada | Trigger: número desde `fiscal_years.last_entry_number` (D-049), `trg_journal_entries_number_assigned`, `trg_fiscal_years_numbering`, `test_numbering_is_correlative_without_gaps_despite_discards`, `test_concurrent_posts_do_not_repeat_or_skip_numbers`, `test_same_draft_posted_twice_at_once_gets_one_number`, `test_free_race_stress` |
| BR-ACC-09 | Solo las cuentas imputables reciben líneas; una cuenta usada no cambia de código ni de naturaleza (D-037) | Implementada | `trg_journal_lines_account_not_postable`, `trg_journal_entries_account_not_postable`, `trg_ledger_accounts_in_use`, `chart.update_account`, `test_line_with_grouping_or_archived_account_fails`, `test_used_ledger_account_keeps_code_and_nature`, `test_used_account_does_not_change_code_or_nature`, `test_archive_rules` |
| BR-ACC-10 | El plan de cuentas propuesto no se presenta como validado hasta que un contador lo marca, con nombre y matrícula (D-038) | Implementada | `accounting.settings` (`ck_settings_chart_validation_complete`), `chart_status` en todos los reportes, D-046, `test_validation_requires_accountant_and_any_structural_change_resets_it`, `test_load_proposed_creates_173_accounts_with_hierarchy_and_kinds` |
| BR-ACC-11 | Un movimiento de finanzas con asiento contabilizado no se anula sin revertir antes el asiento (D-041) | Implementada | `links.ensure_no_posted_entry` (también para importe, fecha y cuenta, D-048), `trg_journal_entries_source_voided`, `test_transaction_with_posted_entry_cannot_be_voided_or_changed`, `test_draft_of_a_voided_transaction_cannot_be_posted` |
| BR-ACC-12 | El cierre del ejercicio exige todos sus períodos cerrados y deja en cero las cuentas de resultado con un asiento de refundición (D-039) | Implementada | `closing.close_fiscal_year`, `trg_journal_entries_closing_invalid`, `trg_fiscal_years_closed_final` (D-050), `test_closing_the_fiscal_year`, `test_closing_with_loss_and_drafts`, `test_closing_entry_only_with_all_periods_closed`, `test_closing_entry_matches_reference` |
| BR-ACC-13 | La depreciación es lineal mensual en guaraníes enteros y la suma de las cuotas es exactamente el importe depreciable (D-057) | Implementada (3B; parámetros `pending` de validación, D-064 a D-067) | `depreciation.quota` (la última cuota absorbe la diferencia), `trg_journal_entries_depreciation_mismatch` (el asiento coincide con su detalle por bien), `trg_fixed_assets_depreciated` (D-081), `test_quota_sum_is_exact_and_last_absorbs`, `test_ten_million_with_one_million_residual_over_36_months`, `test_inexact_division_one_month_and_zero_residual`, `test_service_matches_reference_on_varied_assets`, `test_depreciation_entry_must_match_its_items`, `test_depreciated_asset_keeps_its_parameters`, `test_fiscal_and_accounting_differ_with_non_deductible_quota` |
| BR-ACC-14 | Una categoría de activo sin vida útil o sin cuentas no se usa; las vidas útiles propuestas no se presentan como validadas (D-056) | Implementada (3B) | `depreciation.require_complete` (422 `ASSET_CATEGORY_INCOMPLETE`, D-068), `assets.validate_category` (`accounting.post`), `ck_asset_categories_validation_complete`, `test_packaged_categories_are_identical_to_research_yaml`, `test_incomplete_category_cannot_be_used`, `test_category_accounts_of_wrong_kind_are_rejected`, `test_validation_requires_post_and_resets_on_structural_change`, `test_load_proposed_maps_accounts_and_stays_pending` |
| BR-ACC-15 | Hay a lo sumo una depreciación viva por período y no se saltean meses; la corrida es un borrador que contabiliza una persona (D-058) | Implementada (3B) | `uq_depreciation_runs_live_period` sobre `entry_status` (que copia el trigger, D-069), `trg_depreciation_runs_entry_invalid`, `_period_mismatch`, `_immutable`, `depreciation.run_depreciation` (409 `DEPRECIATION_RUN_EXISTS`, `DEPRECIATION_MONTH_MISSING`), `check_year_depreciated` en el cierre, `test_one_live_run_per_period_and_discard_frees_it`, `test_months_are_not_skipped`, `test_reversal_frees_the_run_and_only_the_last_one_reverses`, `test_concurrent_runs_create_one_live_run`, `test_one_live_run_per_period_and_generation_per_template`, `test_run_status_follows_its_entry_and_cannot_be_faked`, `test_year_close_requires_depreciation_and_stores_year_values` |
| BR-ACC-16 | Un centro de costos solo va en líneas de cuentas de ingreso o gasto (D-060) | Implementada (3B) | `trg_journal_lines_cost_center_account`, `_cost_center_archived` (salvo en reversiones, D-078), `trg_journal_entries_cost_center_required` con `settings.cost_centers_required`, `entries._check_cost_centers`, `test_center_on_asset_or_liability_line_is_rejected`, `test_archived_center_is_rejected_except_in_a_reversal`, `test_required_center_is_checked_on_post`, `test_center_only_on_income_or_expense_lines`, `test_required_centers_block_posting`, `test_income_statement_by_center_adds_up` |
| BR-ACC-17 | Un asiento recurrente se genera como borrador una sola vez por período (D-061) | Implementada (3B) | `uq_recurring_generations_live`, `trg_recurring_generations_entry_invalid`, `_period_mismatch`, `recurring.generate` (todo o nada, D-079), `test_generate_twice_does_not_duplicate`, `test_discard_then_regenerate`, `test_validity_and_pause_are_respected`, `test_day_31_falls_on_last_day_of_short_months`, `test_concurrent_generation_does_not_duplicate` |
| BR-ACC-18 | La baja de un bien exige la depreciación al día y deja en cero su costo y su acumulada (D-059) | Implementada (3B) | `depreciation.dispose` (409 `DEPRECIATION_NOT_UP_TO_DATE`, `document_reference` obligatorio), `trg_journal_entries_disposal_orphan`, reglas de reversión D-074, `test_disposal_zeroes_the_asset_and_books_the_result`, `test_disposal_of_a_fully_depreciated_asset`, `test_disposal_reversal_and_discard_return_the_asset`, `test_disposal_requires_document_and_reason`, `test_disposal_reversal_blocked_by_later_runs`, `test_disposal_entry_needs_its_asset`, `test_disposed_in_year_shows_zero_net` |

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

## Tributación (fase 4 — especificadas en `docs/specs/FASE4_TRIBUTACION.md`)

| ID | Regla |
|---|---|
| BR-TAX-01 | Toda obligación, vencimiento o estimación indica la regla aplicada; si no está `verified` se muestra «sin verificar» y nunca como oficial (D-082, reformulada el 2026-11-24) |
| BR-TAX-02 | Todo cálculo indica la versión de la regla aplicada y su vigencia |
| BR-TAX-03 | Un cálculo es una estimación interna, nunca una declaración oficial; la presentación es manual en Marangatu |
| BR-TAX-04 | Sin perfil fiscal no se generan obligaciones (D-083) |
| BR-TAX-05 | Un vencimiento en día inhábil pasa al siguiente hábil; las excepciones fechadas reemplazan la fecha (D-086) |
| BR-TAX-06 | Las obligaciones presentadas no cambian de vencimiento ni de regla; ninguna se borra (D-087) |
| BR-TAX-07 | Sin comprobantes duplicados: misma dirección, RUC, timbrado y número (D-088) |
| BR-TAX-08 | Los comprobantes de un mes con el registro confirmado no se tocan sin reabrirlo (D-089) |
| BR-TAX-09 | El IVA se calcula con la regla de tasas vigente a la fecha del comprobante; se acepta el impreso con ±1 ₲ (D-088) |
| BR-TAX-10 | Nunca dos asientos vivos para el mismo hecho, desde el comprobante o desde el movimiento (D-091) |
| BR-TAX-11 | El prorrateo del crédito fiscal no se calcula: se avisa (D-090) |
| BR-TAX-12 | Solo `tax.verify` verifica reglas y perfiles, con nombre y matrícula (D-094) |

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
