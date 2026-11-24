/**
 * Acceso a la API de contabilidad: claves de caché, consultas comunes y permisos (D-043).
 * La contabilidad es de la organización (D-035): no hay contextos como en finanzas.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { ROLE_LABELS } from '../../lib/format'
import { get } from '../../services/api'
import { useSession } from '../../stores/session'
import type { Member } from '../../types/api'
import { compareCodes } from './chartTree'
import type { Chart, Entry, FiscalYear, LedgerAccount } from './types'

export const accountingKeys = {
  all: ['accounting'] as const,
  chart: () => ['accounting', 'chart'] as const,
  fiscalYears: () => ['accounting', 'fiscal-years'] as const,
  entries: () => ['accounting', 'entries'] as const,
  entry: (id: string) => ['accounting', 'entries', id] as const,
  reports: () => ['accounting', 'reports'] as const,
}

/** Lo contable cambia en cadena (un asiento mueve reportes, saldos y el movimiento de origen). */
export function useInvalidateAccounting() {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: accountingKeys.all })
    qc.invalidateQueries({ queryKey: ['finance'] })
  }
}

/** Plan completo como lista plana, en orden de código (incluye archivadas). */
export function useChart(enabled = true) {
  return useQuery({
    enabled,
    queryKey: accountingKeys.chart(),
    queryFn: async () => {
      const chart = await get<Chart>('/accounting/chart?flat=true')
      return { ...chart, accounts: [...chart.accounts].sort((a, b) => compareCodes(a.code, b.code)) }
    },
    staleTime: 30_000,
  })
}

/** Cuentas por id (para nombrar las cuentas de asientos, filtros y finanzas). */
export function useAccountsById(accounts: LedgerAccount[] | undefined) {
  return useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts])
}

export function useFiscalYears() {
  return useQuery({ queryKey: accountingKeys.fiscalYears(), queryFn: () => get<FiscalYear[]>('/accounting/fiscal-years') })
}

export function useEntry(id: string | undefined) {
  return useQuery({
    queryKey: accountingKeys.entry(id ?? ''),
    queryFn: () => get<Entry>(`/accounting/entries/${id}`),
    enabled: Boolean(id),
  })
}

export interface AccountingPerms {
  canRead: boolean
  /** Plan de cuentas y borradores. */
  canManage: boolean
  /** Contabilizar, revertir, cerrar, reabrir, validar el plan, crear ejercicios. */
  canPost: boolean
  /** Por qué no puede contabilizar (vacío si puede). */
  postReason: string
  manageReason: string
}

export function useAccountingPerms(): AccountingPerms {
  const { can, me } = useSession()
  const role = me ? (ROLE_LABELS[me.role] ?? me.role) : ''
  const canManage = can('accounting.manage')
  const canPost = can('accounting.post')
  return {
    canRead: can('accounting.read'),
    canManage,
    canPost,
    postReason: canPost
      ? ''
      : canManage
        ? `Tu rol (${role}) prepara el plan y los borradores; contabilizar, revertir, cerrar períodos y validar el plan lo hace un propietario o el contador.`
        : `Tu rol (${role}) puede consultar la contabilidad, pero no modificarla.`,
    manageReason: canManage ? '' : `Tu rol (${role}) puede consultar la contabilidad, pero no modificarla.`,
  }
}

/** Nombre de un usuario por id ("vos" para quien está en sesión). Sin `users.read`, solo "vos" u "otro usuario". */
export function useUserName() {
  const { me, can } = useSession()
  const members = useQuery({
    queryKey: ['users'],
    queryFn: () => get<Member[]>('/users'),
    enabled: can('users.read'),
    staleTime: 60_000,
  })
  return (id: string | null | undefined): string => {
    if (!id) return '—'
    if (me && id === me.user.id) return `${me.user.full_name} (vos)`
    return members.data?.find((m) => m.user.id === id)?.user.full_name ?? 'otro usuario'
  }
}
