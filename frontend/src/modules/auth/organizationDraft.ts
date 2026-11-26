import { rucCheckDigit } from '../../lib/ruc'
import type { ApiError } from '../../services/api'
import type { LegalForm } from '../../types/api'

export interface OrganizationDraft {
  legal_name: string
  trade_name: string
  legal_form: LegalForm
  ruc: string
  ruc_check_digit: string
}

export const EMPTY_ORGANIZATION: OrganizationDraft = { legal_name: '', trade_name: '', legal_form: 'EAS', ruc: '', ruc_check_digit: '' }

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

