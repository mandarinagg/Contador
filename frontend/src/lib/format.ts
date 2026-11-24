const dateTime = new Intl.DateTimeFormat('es-PY', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'America/Asuncion',
})
const date = new Intl.DateTimeFormat('es-PY', { dateStyle: 'long', timeZone: 'America/Asuncion' })

export const formatDateTime = (iso: string) => dateTime.format(new Date(iso))
export const formatDate = (iso: string) => date.format(new Date(iso))

export const ROLE_LABELS: Record<string, string> = {
  owner: 'Propietario',
  admin: 'Administrador',
  accountant: 'Contador',
  viewer: 'Consulta',
}

export const LEGAL_FORM_LABELS: Record<string, string> = {
  EAS: 'Empresa por Acciones Simplificadas (EAS)',
  SA: 'Sociedad Anónima (S.A.)',
  SRL: 'Sociedad de Responsabilidad Limitada (S.R.L.)',
  UNIPERSONAL: 'Empresa unipersonal',
  OTRA: 'Otra forma jurídica',
}

export const AUDIT_ACTION_LABELS: Record<string, string> = {
  'system.setup': 'Configuración inicial',
  'organization.updated': 'Datos de la empresa modificados',
  'user.created': 'Usuario creado',
  'user.updated': 'Usuario modificado',
}

export const SECURITY_EVENT_LABELS: Record<string, string> = {
  setup_completed: 'Configuración inicial',
  login_success: 'Inicio de sesión',
  login_failed: 'Intento fallido',
  login_blocked: 'Intento con cuenta bloqueada',
  account_locked: 'Cuenta bloqueada',
  logout: 'Cierre de sesión',
  password_changed: 'Contraseña cambiada',
}

const FINANCE_ENTITIES: Record<string, [string, 'm' | 'f']> = {
  context: ['Contexto financiero', 'm'],
  account: ['Cuenta', 'f'],
  category: ['Categoría', 'f'],
  counterparty: ['Contraparte', 'f'],
  transaction: ['Movimiento', 'm'],
  import: ['Importación', 'f'],
}
const FINANCE_VERBS: Record<string, [string, string]> = {
  created: ['creado', 'creada'],
  updated: ['modificado', 'modificada'],
  archived: ['archivado', 'archivada'],
  unarchived: ['desarchivado', 'desarchivada'],
  voided: ['anulado', 'anulada'],
  previewed: ['analizado', 'analizada'],
  committed: ['confirmado', 'confirmada'],
  cancelled: ['cancelado', 'cancelada'],
}

/** Acciones de contabilidad (`accounting.<entidad>.<verbo>`, backend/app/modules/accounting/common.py). */
export const ACCOUNTING_ACTION_LABELS: Record<string, string> = {
  'accounting.chart.loaded': 'Plan de cuentas propuesto cargado',
  'accounting.chart.pending': 'Plan de cuentas vuelto a «sin validar»',
  'accounting.chart.validated': 'Plan de cuentas validado',
  'accounting.chart.invalidated': 'Validación del plan de cuentas retirada',
  'accounting.ledger_account.created': 'Cuenta contable creada',
  'accounting.ledger_account.updated': 'Cuenta contable modificada',
  'accounting.ledger_account.archived': 'Cuenta contable archivada',
  'accounting.ledger_account.unarchived': 'Cuenta contable desarchivada',
  'accounting.settings.updated': 'Configuración contable modificada',
  'accounting.fiscal_year.created': 'Ejercicio creado',
  'accounting.fiscal_year.closed': 'Ejercicio cerrado (con refundición)',
  'accounting.period.closed': 'Período cerrado',
  'accounting.period.reopened': 'Período reabierto',
  'accounting.journal_entry.created': 'Asiento creado (borrador)',
  'accounting.journal_entry.updated': 'Borrador de asiento modificado',
  'accounting.journal_entry.posted': 'Asiento contabilizado',
  'accounting.journal_entry.discarded': 'Borrador de asiento descartado',
  'accounting.journal_entry.reversed': 'Asiento revertido',
  'accounting.asset_categories.loaded': 'Categorías de activo fijo propuestas cargadas',
  'accounting.asset_category.created': 'Categoría de activo fijo creada',
  'accounting.asset_category.updated': 'Categoría de activo fijo modificada',
  'accounting.asset_category.validated': 'Categoría de activo fijo validada',
  'accounting.fixed_asset.created': 'Bien de uso dado de alta',
  'accounting.fixed_asset.updated': 'Bien de uso modificado',
  'accounting.fixed_asset.disposal_drafted': 'Baja de bien preparada (borrador)',
  'accounting.fixed_asset.disposed': 'Bien de uso dado de baja',
  'accounting.fixed_asset.disposal_discarded': 'Borrador de baja descartado',
  'accounting.fixed_asset.disposal_reversed': 'Baja de bien revertida',
  'accounting.depreciation_run.created': 'Depreciación del mes calculada (borrador)',
  'accounting.cost_center.created': 'Centro de costos creado',
  'accounting.cost_center.updated': 'Centro de costos modificado',
  'accounting.recurring_template.created': 'Plantilla recurrente creada',
  'accounting.recurring_template.updated': 'Plantilla recurrente modificada',
  'accounting.recurring_generation.created': 'Asiento recurrente generado',
}

/** Etiqueta de una acción de auditoría, incluidas las de finanzas (`finance[.personal].<entidad>.<verbo>`) y contabilidad. */
export function auditActionLabel(action: string): string {
  if (AUDIT_ACTION_LABELS[action]) return AUDIT_ACTION_LABELS[action]
  if (ACCOUNTING_ACTION_LABELS[action]) return ACCOUNTING_ACTION_LABELS[action]
  const m = /^finance\.(personal\.)?([a-z]+)\.([a-z]+)$/.exec(action)
  const entity = m && FINANCE_ENTITIES[m[2]]
  const verb = m && FINANCE_VERBS[m[3]]
  if (!m || !entity || !verb) return action
  return `${entity[0]} ${verb[entity[1] === 'm' ? 0 : 1]}${m[1] ? ' (finanzas personales)' : ''}`
}

/** Nombres legibles de los campos que aparecen en la auditoría. */
export const FIELD_LABELS: Record<string, string> = {
  legal_name: 'Razón social',
  trade_name: 'Nombre de fantasía',
  legal_form: 'Forma jurídica',
  ruc: 'RUC',
  ruc_check_digit: 'Dígito verificador',
  email: 'Email',
  owner_email: 'Email del propietario',
  full_name: 'Nombre',
  is_active: 'Activo',
  role: 'Rol',
  name: 'Nombre',
  kind: 'Tipo',
  institution: 'Entidad',
  currency: 'Moneda',
  number_last4: 'Últimos 4 dígitos',
  opening_balance: 'Saldo inicial',
  opening_date: 'Fecha del saldo inicial',
  archived_at: 'Archivado',
  parent_id: 'Categoría padre',
  notes: 'Notas',
  account_id: 'Cuenta',
  booked_on: 'Fecha',
  amount: 'Importe',
  description: 'Descripción',
  reference: 'Referencia',
  category_id: 'Categoría',
  counterparty_id: 'Contraparte',
  reviewed_at: 'Revisado',
  voided_at: 'Anulado',
  void_reason: 'Motivo de anulación',
  filename: 'Archivo',
  rows_total: 'Filas',
  rows_imported: 'Importadas',
  rows_error: 'Con error',
  rows_duplicate: 'Duplicadas',
  // Contabilidad
  code: 'Código',
  normal_side: 'Saldo normal',
  is_postable: 'Imputable',
  chart_status: 'Estado del plan',
  chart_validated_by_name: 'Validado por',
  chart_validated_reference: 'Matrícula',
  chart_validated_at: 'Validado el',
  retained_earnings_account_id: 'Cuenta de resultados acumulados',
  asset_disposal_account_id: 'Cuenta de resultado por bajas',
  cost_centers_required: 'Centro de costos obligatorio',
  default_asset_start_rule: 'Inicio de depreciación por defecto',
  entry_date: 'Fecha del asiento',
  document_reference: 'Comprobante',
  number: 'Número',
  status: 'Estado',
  useful_life_months: 'Vida útil (meses)',
  residual_rate: 'Residual (%)',
  residual_value: 'Valor residual contable',
  fiscal_useful_life_months: 'Vida útil fiscal (meses)',
  fiscal_residual_rate: 'Residual fiscal (%)',
  fiscal_residual_value: 'Valor residual fiscal',
  asset_account_id: 'Cuenta del bien',
  accumulated_account_id: 'Cuenta de depreciación acumulada',
  expense_account_id: 'Cuenta de gasto',
  validation_status: 'Validación',
  validated_by_name: 'Validado por',
  validated_reference: 'Matrícula',
  acquired_on: 'Fecha de adquisición',
  cost: 'Costo',
  start_rule: 'Inicio de la depreciación',
  depreciation_start: 'Primer mes de depreciación',
  serial_or_reference: 'N° de serie o referencia',
  acquisition_entry_id: 'Asiento de compra',
  disposed_on: 'Fecha de baja',
  disposal_kind: 'Tipo de baja',
  disposal_reason: 'Motivo de la baja',
  disposal_document_reference: 'Acta de baja',
  day_of_month: 'Día del mes',
  start_date: 'Desde',
  end_date: 'Hasta',
  note: 'Nota',
}

export function formatFieldValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (field === 'role') return ROLE_LABELS[String(value)] ?? String(value)
  return String(value)
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
