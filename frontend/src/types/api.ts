/** Tipos de la API local (espejo de los esquemas Pydantic del backend). */

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown }
}

export type RoleCode = 'owner' | 'admin' | 'accountant' | 'viewer'
export type LegalForm = 'EAS' | 'SA' | 'SRL' | 'UNIPERSONAL' | 'PERSONA_FISICA' | 'OTRA'

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  last_login_at: string | null
}

export interface OrganizationSummary {
  id: string
  legal_name: string
  trade_name: string | null
  legal_form: LegalForm
}

export interface Me {
  user: User
  organization: OrganizationSummary
  role: RoleCode
  permissions: string[]
}

/** Una organización a la que el usuario tiene acceso, con su rol ahí (`GET /auth/organizations`). */
export interface Membership {
  id: string
  legal_name: string
  trade_name: string | null
  legal_form: LegalForm
  ruc: string | null
  ruc_check_digit: string | null
  role: RoleCode
  is_current: boolean
}

export interface LoginResponse extends Me {
  token: string
  expires_at: string
  organizations: Membership[]
}

export interface Organization extends OrganizationSummary {
  first_names: string | null
  last_names: string | null
  ruc: string | null
  ruc_check_digit: string | null
  base_currency: string
  created_at: string
  updated_at: string
}

export interface Member {
  user: User
  role: RoleCode
  member_since: string
}

export interface Role {
  code: RoleCode
  name: string
  description: string
  permissions: string[]
}

export interface AuditLog {
  id: string
  seq: number
  occurred_at: string
  actor_user_id: string | null
  actor_kind: string
  action: string
  entity_type: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  request_id: string | null
}

export interface SecurityEvent {
  id: string
  occurred_at: string
  event_type: string
  user_id: string | null
  email_attempted: string | null
  ip_address: string | null
  details: Record<string, unknown> | null
}

export interface ChainVerification {
  valid: boolean
  checked: number
  first_broken_seq: number | null
}
