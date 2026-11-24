/**
 * Tipos de la API de contabilidad (espejo de backend/app/modules/accounting/schemas.py).
 * Importes siempre `string` (D-036, BR-ACC-05): el debe y el haber son guaraníes enteros.
 */

export type LedgerKind = 'asset' | 'liability' | 'equity' | 'income' | 'expense'
export type NormalSide = 'debit' | 'credit'
export type LedgerOrigin = 'rg49_2014' | 'proposed' | 'user'
export type ChartStatus = 'none' | 'pending' | 'validated'
export type EntryStatus = 'draft' | 'posted' | 'reversed' | 'discarded'
export type EntryKind = 'manual' | 'finance' | 'reversal' | 'closing' | 'depreciation' | 'disposal' | 'recurring'
export type StartRule = 'next_month' | 'next_fiscal_year'
export type FxCurrency = 'USD' | 'BRL' | 'ARS' | 'EUR'

export interface LedgerAccount {
  id: string
  code: string
  name: string
  kind: LedgerKind
  normal_side: NormalSide
  is_postable: boolean
  parent_id: string | null
  origin: LedgerOrigin
  note: string | null
  archived_at: string | null
  in_use: boolean
  balance?: string | null
  children?: LedgerAccount[] | null
}

export interface AccountingSettings {
  chart_status: ChartStatus
  chart_validated_by_name: string | null
  chart_validated_reference: string | null
  chart_validated_at: string | null
  retained_earnings_account_id: string | null
  /** 3B: cuenta de resultado por bajas (null = la 17.01 del plan propuesto). */
  asset_disposal_account_id: string | null
  cost_centers_required: boolean
  default_asset_start_rule: StartRule
}

export interface Chart extends AccountingSettings {
  balance_at: string | null
  accounts: LedgerAccount[]
}

export interface Period {
  id: string
  fiscal_year_id: string
  start_date: string
  end_date: string
  status: 'open' | 'closed'
  closed_at: string | null
  closed_by: string | null
  reopen_reason: string | null
}

export interface FiscalYear {
  id: string
  start_date: string
  end_date: string
  status: 'open' | 'closed'
  closed_at: string | null
  closed_by: string | null
  closing_entry_id: string | null
  last_entry_number: number
  periods: Period[]
}

export interface EntryLine {
  id: string
  line_no: number
  account_id: string
  account_code: string
  account_name: string
  debit: string
  credit: string
  description: string | null
  fx_currency: string | null
  fx_amount: string | null
  fx_rate: string | null
  cost_center_id: string | null
  cost_center_code: string | null
}

export interface Entry {
  id: string
  fiscal_year_id: string
  entry_date: string
  number: number | null
  status: EntryStatus
  kind: EntryKind
  description: string
  document_reference: string | null
  reverses_entry_id: string | null
  reversed_by_entry_id: string | null
  source_transaction_id: string | null
  source_context_id: string | null
  total_debit: string
  total_credit: string
  balanced: boolean
  created_by: string
  /** Nombre visible de quien lo creó y de quien lo contabilizó (P-10). */
  created_by_name: string | null
  created_at: string
  posted_by: string | null
  posted_by_name: string | null
  posted_at: string | null
  discarded_by: string | null
  discarded_at: string | null
  discard_reason: string | null
  lines: EntryLine[] | null
}

/** Asiento de un movimiento de finanzas empresarial (`Transaction.journal_entry`). */
export interface EntryRef {
  id: string
  number: number | null
  status: EntryStatus
}

export interface EntryLineIn {
  account_id: string
  debit?: string
  credit?: string
  description?: string | null
  fx_currency?: string | null
  fx_amount?: string | null
  fx_rate?: string | null
  cost_center_id?: string | null
}

export interface EntryIn {
  entry_date: string
  description: string
  document_reference: string | null
  lines: EntryLineIn[]
}

// --- Reportes -------------------------------------------------------------------------

interface Report {
  chart_status: ChartStatus
}

export interface JournalReport extends Report {
  date_from: string
  date_to: string
  total_debit: string
  total_credit: string
  entries: Entry[]
  next_cursor: string | null
}

export interface LedgerMovement {
  line_id: string
  entry_id: string
  number: number
  entry_date: string
  entry_description: string
  line_description: string | null
  document_reference: string | null
  debit: string
  credit: string
  balance: string
}

export interface LedgerReport extends Report {
  account: LedgerAccount
  date_from: string
  date_to: string
  opening_balance: string
  total_debit: string
  total_credit: string
  closing_balance: string
  movements: LedgerMovement[]
  next_cursor: string | null
}

export interface TrialRow {
  account_id: string
  code: string
  name: string
  kind: LedgerKind
  /** Saldo antes de `from` (D-062, D-075), en el sentido deudor o acreedor. */
  opening_debit: string
  opening_credit: string
  debit: string
  credit: string
  /** Saldo del rango (compatibilidad con el núcleo). */
  debit_balance: string
  credit_balance: string
  /** Saldo inicial más el rango. */
  closing_debit: string
  closing_credit: string
}

export interface TrialBalance extends Report {
  date_from: string
  date_to: string
  rows: TrialRow[]
  total_opening_debit: string
  total_opening_credit: string
  total_debit: string
  total_credit: string
  total_debit_balance: string
  total_credit_balance: string
  total_closing_debit: string
  total_closing_credit: string
  balanced: boolean
}

export interface StatementNode {
  account_id: string
  code: string
  name: string
  kind: LedgerKind
  is_postable: boolean
  amount: string
  children: StatementNode[]
  /** Solo con `by_cost_center`: el importe en cada columna de `cost_center_columns`. */
  column_amounts?: string[] | null
}

export interface BalanceSheet extends Report {
  at: string
  assets: StatementNode[]
  liabilities: StatementNode[]
  equity: StatementNode[]
  total_assets: string
  total_liabilities: string
  total_equity: string
  result: string
  total_liabilities_and_equity: string
  balanced: boolean
}

export interface IncomeStatement extends Report {
  date_from: string
  date_to: string
  accounts: StatementNode[]
  total_income: string
  total_expense: string
  result: string
  cost_center_columns: CostCenterColumn[] | null
}

/** Columna del estado de resultados por centro; `cost_center_id` null = «Sin centro». */
export interface CostCenterColumn {
  cost_center_id: string | null
  code: string | null
  name: string
  total_income: string
  total_expense: string
  result: string
}
