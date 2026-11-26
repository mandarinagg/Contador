import { rucCheckDigit } from '../../lib/ruc'
import type { ApiError } from '../../services/api'
import type { LegalForm } from '../../types/api'

export interface OrganizationDraft {
  legal_name: string
  trade_name: string
  legal_form: LegalForm
  first_names: string
  last_names: string
  ruc: string
  ruc_check_digit: string
}

export const EMPTY_ORGANIZATION: OrganizationDraft = { legal_name: '', trade_name: '', legal_form: 'EAS', first_names: '', last_names: '', ruc: '', ruc_check_digit: '' }

export const isPerson = (legalForm: LegalForm): boolean => legalForm === 'PERSONA_FISICA'

/** Lo que falta para poder enviar la identidad: razón social (empresa) o nombres y apellidos (persona). */
export function identityProblems(v: OrganizationDraft): Record<string, string> {
  const out: Record<string, string> = {}
  if (isPerson(v.legal_form)) {
    if (!v.first_names.trim()) out.first_names = 'Escribí los nombres.'
    if (!v.last_names.trim()) out.last_names = 'Escribí los apellidos.'
  } else if (v.legal_name.trim().length < 2) {
    out.legal_name = 'Escribí la razón social.'
  }
  return out
}

/** La identidad como la espera la API: la persona física no manda razón social (la arma el servidor). */
export function identityBody(v: OrganizationDraft) {
  return {
    ...(isPerson(v.legal_form) ? { first_names: v.first_names.trim(), last_names: v.last_names.trim() } : { legal_name: v.legal_name }),
    legal_form: v.legal_form,
    trade_name: v.trade_name.trim() || null,
  }
}

/** El dígito verificador que corresponde al RUC escrito, o null si el RUC todavía no es válido. */
export function expectedCheckDigit(ruc: string): string | null {
  return /^\d{1,8}$/.test(ruc) ? String(rucCheckDigit(ruc)) : null
}

export function hasCheckDigitMismatch(v: OrganizationDraft): boolean {
  const expected = expectedCheckDigit(v.ruc)
  return expected !== null && v.ruc_check_digit !== '' && v.ruc_check_digit !== expected
}

/** Textos propios de cada error de negocio del alta (el resto usa el mensaje del servidor). */
export function newOrganizationMessage(error: ApiError): string {
  if (error.code === 'RUC_TAKEN') return 'Ya hay una organización con ese RUC. Revisá el número y el dígito verificador.'
  if (error.code === 'OWNER_ONLY') return 'Solo el propietario de una organización puede dar de alta otra.'
  return error.message
}

