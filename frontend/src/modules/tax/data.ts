/**
 * Acceso a la API de tributación: claves de caché, consultas comunes y permisos (D-094).
 * La tributación es de la organización (como la contabilidad); las reglas y los feriados son
 * globales (normas del país).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { ROLE_LABELS } from '../../lib/format'
import { get, qs } from '../../services/api'
import { useSession } from '../../stores/session'
import { monthEnd, shiftMonth } from './logic'
import type { DueDateException, Holiday, Obligation, Profile, Rule, TaxAlerts, TaxSettings } from './types'

export const taxKeys = {
  all: ['tax'] as const,
  alerts: () => ['tax', 'alerts'] as const,
  profile: () => ['tax', 'profile'] as const,
  rules: () => ['tax', 'rules'] as const,
  holidays: () => ['tax', 'holidays'] as const,
  exceptions: () => ['tax', 'exceptions'] as const,
  obligations: () => ['tax', 'obligations'] as const,
  vouchers: () => ['tax', 'vouchers'] as const,
  vat: () => ['tax', 'vat'] as const,
  irp: () => ['tax', 'irp'] as const,
  settings: () => ['tax', 'settings'] as const,
}

/** Un cambio tributario mueve avisos, calendario, comprobantes e IVA: se invalida todo lo de impuestos. */
export function useInvalidateTax() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: taxKeys.all })
}

export function useTaxAlerts(enabled = true) {
  return useQuery({ enabled, queryKey: taxKeys.alerts(), queryFn: () => get<TaxAlerts>('/tax/alerts'), staleTime: 30_000 })
}

export function useTaxProfile(enabled = true) {
  return useQuery({ enabled, queryKey: taxKeys.profile(), queryFn: () => get<Profile>('/tax/profile') })
}

/** Todas las reglas (incluidas las deprecadas): las obligaciones viejas las siguen nombrando. */
export function useRules() {
  return useQuery({ queryKey: taxKeys.rules(), queryFn: () => get<Rule[]>('/tax/rules'), staleTime: 60_000 })
}

export function useRulesById() {
  const rules = useRules()
  return useMemo(() => new Map((rules.data ?? []).map((r) => [r.id, r])), [rules.data])
}

export function useHolidays() {
  return useQuery({ queryKey: taxKeys.holidays(), queryFn: () => get<Holiday[]>('/tax/holidays') })
}

export function useExceptions() {
  return useQuery({ queryKey: taxKeys.exceptions(), queryFn: () => get<DueDateException[]>('/tax/due-date-exceptions') })
}

export function useObligations(range: { from?: string; to?: string; status?: string; code?: string }, enabled = true) {
  return useQuery({
    enabled,
    queryKey: [...taxKeys.obligations(), range],
    queryFn: () => get<Obligation[]>(`/tax/obligations${qs(range)}`),
  })
}

export function useTaxSettings() {
  return useQuery({ queryKey: taxKeys.settings(), queryFn: () => get<TaxSettings>('/tax/settings'), staleTime: 30_000 })
}

export interface TaxPerms {
  canRead: boolean
  /** Perfil declarado, comprobantes, obligaciones, feriados, excepciones y configuración. */
  canManage: boolean
  /** Aprobar la verificación de CONTADOR AI (reglas, perfil, feriados) y deprecar reglas (D-120). */
  canVerify: boolean
  /** Proponer el asiento de un comprobante: además `accounting.manage`. */
  canProposeEntry: boolean
  manageReason: string
  verifyReason: string
}

export function useTaxPerms(): TaxPerms {
  const { can, me } = useSession()
  const role = me ? (ROLE_LABELS[me.role] ?? me.role) : ''
  const canManage = can('tax.manage')
  const canVerify = can('tax.verify')
  return {
    canRead: can('tax.read'),
    canManage,
    canVerify,
    canProposeEntry: canManage && can('accounting.manage'),
    manageReason: canManage ? '' : `Tu rol (${role}) puede consultar los impuestos, pero no cargar ni cambiar nada.`,
    verifyReason: canVerify
      ? ''
      : canManage
        ? `Tu rol (${role}) carga y opera; aprobar la verificación de reglas y del perfil le toca al propietario.`
        : `Tu rol (${role}) puede consultar los impuestos, pero no verificarlos.`,
  }
}

/** Obligación del registro del mes del comprobante, si está confirmada (D-089). */
export function useConfirmedRegister(issuedOn: string): { obligationId: string; dueMonth: string } | null {
  const month = /^\d{4}-\d{2}-\d{2}$/.test(issuedOn) ? issuedOn.slice(0, 7) : ''
  const list = useObligations(
    { code: 'REG-COMPROB-MENSUAL', from: month ? `${month}-01` : undefined, to: month ? monthEnd(shiftMonth(month, 3)) : undefined },
    Boolean(month),
  )
  const row = (list.data ?? []).find((o: Obligation) => o.period_start === `${month}-01`)
  return row && (row.status === 'filed' || row.status === 'paid') ? { obligationId: row.id, dueMonth: row.due_date.slice(0, 7) } : null
}
