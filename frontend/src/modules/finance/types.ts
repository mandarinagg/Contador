/**
 * Tipos de la API de finanzas (espejo de backend/app/modules/finance/schemas.py).
 * Todo importe es `string` decimal (D-026): nunca `number`.
 */

export type ContextKind = 'business' | 'personal'
export type AccountKind = 'cash' | 'checking' | 'savings' | 'credit_card' | 'digital_wallet' | 'other'
export type CategoryKind = 'income' | 'expense'
export type CounterpartyKind = 'customer' | 'supplier' | 'employee' | 'bank' | 'government' | 'person' | 'other'
export type Decision = 'import' | 'skip'

export interface FinanceContext {
  id: string
  kind: ContextKind
  name: string
  owner_user_id: string | null
  is_active: boolean
  created_at: string
}

export interface Account {
  id: string
  context_id: string
  name: string
  kind: AccountKind
  institution: string | null
  currency: string
  number_last4: string | null
  opening_balance: string
  opening_date: string
  balance: string
  archived_at: string | null
  created_at: string
}

export interface Category {
  id: string
  context_id: string
  name: string
  kind: CategoryKind
  parent_id: string | null
  archived_at: string | null
  created_at: string
}

export interface Counterparty {
  id: string
  context_id: string
  name: string
  ruc: string | null
  ruc_check_digit: string | null
  kind: CounterpartyKind
  notes: string | null
  archived_at: string | null
  created_at: string
}

export interface Transaction {
  id: string
  context_id: string
  account_id: string
  currency: string
  booked_on: string
  amount: string
  description: string
  reference: string | null
  category_id: string | null
  counterparty_id: string | null
  source: 'manual' | 'import'
  import_batch_id: string | null
  transfer_group_id: string | null
  reviewed_at: string | null
  voided_at: string | null
  voided_by: string | null
  void_reason: string | null
  created_by: string
  created_at: string
}

export interface TransferResult {
  transfer_group_id: string
  outgoing: Transaction
  incoming: Transaction
}

export type AmountMapping =
  | { mode: 'single'; column: string }
  | { mode: 'split'; debit_column: string; credit_column: string }

export interface ImportMapping {
  has_header: boolean
  delimiter: ';' | ',' | '\t' | '|'
  encoding: 'auto' | 'utf-8' | 'cp1252'
  date_column: string
  date_format: string
  description_column: string
  reference_column: string | null
  amount: AmountMapping
  decimal_separator: ',' | '.'
  thousands_separator: '.' | ',' | ' ' | ''
  skip_rows: number
}

export interface ImportRow {
  row_number: number
  raw: Record<string, string>
  booked_on: string | null
  amount: string | null
  description: string | null
  reference: string | null
  error: string | null
  duplicate_of: string | null
  duplicate_in_file: number | null
  decision: Decision
}

export interface ImportBatch {
  id: string
  context_id: string
  account_id: string
  currency: string
  filename: string
  file_sha256: string
  file_format: 'csv' | 'xlsx'
  mapping: ImportMapping
  status: 'previewed' | 'committed' | 'cancelled'
  rows_total: number
  rows_imported: number
  rows_duplicate: number
  rows_error: number
  created_by: string
  created_at: string
  committed_at: string | null
  rows: ImportRow[] | null
}

export interface CurrencyTotals {
  currency: string
  income: string
  expense: string
  net: string
}

export interface Summary {
  context_id: string
  date_from: string
  date_to: string
  balances: { account_id: string; name: string; currency: string; balance: string; archived: boolean }[]
  totals: CurrencyTotals[]
  by_month: (CurrencyTotals & { month: string })[]
  expenses_by_category: { currency: string; category_id: string | null; category_name: string; amount: string }[]
}

export interface Consolidated {
  date_from: string
  date_to: string
  contexts: { context: FinanceContext; totals: (CurrencyTotals & { balance: string })[] }[]
}
