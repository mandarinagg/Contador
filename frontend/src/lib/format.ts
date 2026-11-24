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
}

export function formatFieldValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (field === 'role') return ROLE_LABELS[String(value)] ?? String(value)
  return String(value)
}

export const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
