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
import type { AccountingSettings, Chart, Entry, FiscalYear, LedgerAccount, Period } from './types'
import type { AssetCategory, CostCenter, RecurringDue, RecurringTemplate } from './types3b'

export const accountingKeys = {
  all: ['accounting'] as const,
  chart: () => ['accounting', 'chart'] as const,
  fiscalYears: () => ['accounting', 'fiscal-years'] as const,
  entries: () => ['accounting', 'entries'] as const,
  entry: (id: string) => ['accounting', 'entries', id] as const,
  reports: () => ['accounting', 'reports'] as const,
  settings: () => ['accounting', 'settings'] as const,
  assetCategories: () => ['accounting', 'asset-categories'] as const,
  assets: () => ['accounting', 'fixed-assets'] as const,
  asset: (id: string) => ['accounting', 'fixed-assets', id] as const,
  runs: (yearId: string) => ['accounting', 'depreciation-runs', yearId] as const,
  costCenters: () => ['accounting', 'cost-centers'] as const,
  recurring: () => ['accounting', 'recurring'] as const,
  recurringDue: (periodId: string) => ['accounting', 'recurring', 'due', periodId] as const,
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

export function useFiscalYears(enabled = true) {
  return useQuery({ enabled, queryKey: accountingKeys.fiscalYears(), queryFn: () => get<FiscalYear[]>('/accounting/fiscal-years') })
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
        ? `Tu rol (${role}) prepara el plan y los borradores; contabilizar, revertir, cerrar períodos y validar el plan lo hace el propietario.`
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

/** Configuración contable (GET /accounting/settings): cuentas de resultados y de bajas, centros, inicio por defecto. */
export function useAccountingSettings() {
  return useQuery({ queryKey: accountingKeys.settings(), queryFn: () => get<AccountingSettings>('/accounting/settings'), staleTime: 30_000 })
}

/** Todas las categorías de activo fijo, incluidas las archivadas (los bienes viejos las siguen nombrando). */
export function useAssetCategories(enabled = true) {
  return useQuery({ enabled, queryKey: accountingKeys.assetCategories(), queryFn: () => get<AssetCategory[]>('/accounting/asset-categories?include_archived=true') })
}

/** Centros de costos, incluidos los archivados (para nombrar líneas viejas). */
export function useCostCenters(enabled = true) {
  return useQuery({ enabled, queryKey: accountingKeys.costCenters(), queryFn: () => get<CostCenter[]>('/accounting/cost-centers?include_archived=true'), staleTime: 30_000 })
}

export function useRecurringTemplates() {
  return useQuery({ queryKey: accountingKeys.recurring(), queryFn: () => get<RecurringTemplate[]>('/accounting/recurring') })
}

/** El período (mes) de una fecha, si hay un ejercicio que la contiene. */
export function periodOf(years: FiscalYear[] | undefined, date: string): Period | undefined {
  for (const y of years ?? []) {
    if (y.start_date <= date && date <= y.end_date) return y.periods.find((p) => p.start_date <= date && date <= p.end_date)
  }
  return undefined
}

/** Qué asientos recurrentes faltan generar en un período (para el aviso de D-061). */
export function useRecurringDue(periodId: string | undefined) {
  return useQuery({
    enabled: Boolean(periodId),
    queryKey: accountingKeys.recurringDue(periodId ?? ''),
    queryFn: () => get<RecurringDue[]>(`/accounting/recurring/due?period_id=${periodId}`),
    staleTime: 30_000,
  })
}
