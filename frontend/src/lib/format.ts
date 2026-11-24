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

/** Etiqueta de una acción de auditoría, incluidas las de finanzas (`finance[.personal].<entidad>.<verbo>`). */
export function auditActionLabel(action: string): string {
  if (AUDIT_ACTION_LABELS[action]) return AUDIT_ACTION_LABELS[action]
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
}

export function formatFieldValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (field === 'role') return ROLE_LABELS[String(value)] ?? String(value)
  return String(value)
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
