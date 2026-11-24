/** Ayudas sobre la referencia al asiento de un movimiento de finanzas (D-048). */
import { ApiError } from '../../services/api'
import { useSession } from '../../stores/session'
import { useAccountsById, useChart } from './data'
import type { Transaction } from '../finance/types'
import type { EntryRef, LedgerAccount } from './types'

export interface LedgerMapping {
  /** Se muestra la cuenta contable (contexto empresarial y permiso de consultar la contabilidad). */
  show: boolean
  /** Se puede cambiar (accounting.manage). */
  canEdit: boolean
  accounts: LedgerAccount[]
  byId: Map<string, LedgerAccount>
}

/** Cuentas contables para mapear cuentas y categorías de finanzas de la empresa (D-041). */
export function useLedgerMapping(business: boolean): LedgerMapping {
  const { can } = useSession()
  const show = business && can('accounting.read')
  const chart = useChart(show)
  const byId = useAccountsById(chart.data?.accounts)
  return { show, canEdit: show && can('accounting.manage'), accounts: chart.data?.accounts ?? [], byId }
}

/** Asiento contabilizado que bloquea anular o cambiar fecha, importe y cuenta (D-048). */
export function postedEntryOf(entry: EntryRef | null | undefined): EntryRef | null {
  return entry && entry.status === 'posted' ? entry : null
}

/** 409 TRANSACTION_HAS_POSTED_ENTRY: el mensaje de la API más el enlace al asiento. */
export function postedEntryFromError(error: unknown): EntryRef | null {
  if (!(error instanceof ApiError) || error.code !== 'TRANSACTION_HAS_POSTED_ENTRY') return null
  const d = error.details as { entry_id?: string; number?: number } | null
  return d?.entry_id ? { id: d.entry_id, number: d.number ?? null, status: 'posted' } : null
}

/** ¿Se puede proponer un asiento para este movimiento? (sin el permiso, que lo decide quien llama). */
export function canPropose(tx: Transaction): boolean {
  return !tx.voided_at && !tx.transfer_group_id && (!tx.journal_entry || tx.journal_entry.status === 'reversed')
}
