/**
 * Tipos de la API de tributación (espejo de backend/app/modules/tax/schemas.py y de las
 * respuestas de `vat.py`, `alerts.py` y `exports.py`). Todo importe es `string` (D-095).
 */

export type RuleStatus = 'pending' | 'verified' | 'deprecated'
export type Direction = 'purchase' | 'sale'
export type VoucherType = 'invoice' | 'credit_note' | 'debit_note'
export type DocType = 'ruc' | 'identity_card' | 'passport' | 'foreign_id' | 'unnamed' | 'diplomatic' | 'tax_id'
export type Condition = 'cash' | 'credit'
export type IreRegime = 'ire_general' | 'ire_simple' | 'unknown'
export type ObligationStatus = 'pending' | 'filed' | 'paid' | 'not_applicable'

export interface RuleApplied {
  id: string
  code: string
  version: number
  validation_status: RuleStatus | string
  legal_reference: string | null
}

export interface Rule {
  id: string
  code: string
  version: number
  description: string
  parameters: Record<string, unknown>
  valid_from: string | null
  valid_to: string | null
  published_at: string | null
  source_url: string | null
  legal_reference: string | null
  consulted_at: string | null
  confidence: string | null
  notes: string | null
  validation_status: RuleStatus
  reviewed_by_name: string | null
  reviewed_reference: string | null
  reviewed_at: string | null
  review_note: string | null
  deprecation_reason: string | null
  deprecated_at: string | null
  used_by_calculations: boolean
  /** D-120: si CONTADOR AI puede verificarla (fuente oficial leída) y, si no, por qué. */
  verifiable: boolean
  unverifiable_reason: string | null
}

export interface RuleBulkVerifyResult {
  verified: string[]
  left_pending: { id: string; code: string; version: number; reason: string }[]
}

export interface RuleLoadResult {
  created: number
  unchanged: number
  differing: string[]
  rejected: Record<string, unknown>[]
  exceptions_created: number
  total: number
}

export interface Holiday {
  id: string
  day: string
  name: string
  source_url: string | null
  legal_reference: string | null
  validation_status: 'pending' | 'verified'
  origin: string
  notes: string | null
}

export interface DueDateException {
  id: string
  obligation_code: string | null
  obligation_group: string | null
  due_month: string
  ruc_digits: number[]
  new_due_date: string
  legal_reference: string
  source_url: string | null
  rule_version_id: string | null
  origin: string
  is_active: boolean
  notes: string | null
}

export interface ProfileObligation {
  code: string
  registered_on: string
  supported: boolean
}

export interface ProfileVersion {
  id: string
  valid_from: string
  ire_regime: IreRegime
  fiscal_close_month: number
  vat_taxpayer: boolean
  origin: 'declared' | 'verified'
  verified_by_name: string | null
  verified_license: string | null
  verified_document_reference: string | null
  verified_at: string | null
  notes: string | null
  obligations: ProfileObligation[]
}

export interface Profile {
  ruc: string | null
  ruc_check_digit: string | null
  current: ProfileVersion | null
  history: ProfileVersion[]
}

export interface SyncResult {
  created: number
  recalculated: number
  not_applicable: number
  reactivated: number
  profile_missing: boolean
  unsupported_codes: string[]
  without_rule: Record<string, unknown>[]
}

export interface Obligation {
  id: string
  code: string
  dnit_code: string
  period_start: string
  period_end: string
  nominal_due_date: string
  due_date: string
  remind_by: string
  shift_explanation: string | null
  status: ObligationStatus
  is_overdue: boolean
  calculated_amount: string | null
  calculated_credit_balance: string | null
  filed_on: string | null
  filing_reference: string | null
  declared_amount: string | null
  declared_credit_balance: string | null
  paid_on: string | null
  paid_amount: string | null
  payment_transaction_id: string | null
  not_applicable_reason: string | null
  not_applicable_auto: boolean
  reopen_reason: string | null
  exception: { id: string; new_due_date: string; legal_reference: string; source_url: string | null } | null
  rules_applied: RuleApplied[]
  rule_status: string | null
}

export interface Voucher {
  id: string
  direction: Direction
  voucher_type: VoucherType
  is_electronic: boolean
  cdc: string | null
  timbrado: string
  number: string
  issued_on: string
  counterparty_doc_type: DocType
  counterparty_ruc: string | null
  counterparty_ruc_dv: string | null
  counterparty_document: string | null
  counterparty_name: string
  counterparty_review_required: boolean
  condition: Condition
  currency: string
  fx_rate: string | null
  foreign_total: string | null
  taxed_10: string
  taxed_5: string
  exempt: string
  total: string
  vat_10: string
  vat_5: string
  imputes_vat: boolean
  imputes_ire: boolean
  imputes_irp: boolean
  related_voucher_id: string | null
  finance_counterparty_id: string | null
  transaction_id: string | null
  journal_entry_id: string | null
  journal_entry_status: 'draft' | 'posted' | 'reversed' | 'discarded' | null
  period_confirmed: boolean
  notes: string | null
  voided_at: string | null
  void_reason: string | null
  created_at: string
  rules_applied: RuleApplied[]
  rule_status: string | null
}

export interface VoucherIn {
  direction: Direction
  voucher_type: VoucherType
  is_electronic: boolean
  cdc?: string | null
  timbrado: string
  number: string
  issued_on: string
  counterparty_doc_type: DocType
  counterparty_ruc?: string | null
  counterparty_ruc_dv?: string | null
  counterparty_document?: string | null
  counterparty_name?: string | null
  condition: Condition
  currency: string
  fx_rate?: string | null
  foreign_total?: string | null
  taxed_10?: string
  taxed_5?: string
  exempt?: string
  vat_10?: string
  vat_5?: string
  imputes_vat: boolean
  imputes_ire: boolean
  imputes_irp: boolean
  related_voucher_id?: string | null
  finance_counterparty_id?: string | null
  transaction_id?: string | null
  notes?: string | null
}

export interface ExcludedVoucher {
  id: string
  direction: Direction
  voucher_type: VoucherType
  issued_on: string
  number: string
  cdc: string | null
  counterparty_name: string
}

export interface MarangatuPreview {
  is_draft: boolean
  notice: string
  format: string
  encoding: string
  header: boolean
  separator: 'semicolon' | 'comma'
  rows: number
  batches: { name: string; rows: number }[]
  excluded_electronic: { count: number; vouchers: ExcludedVoucher[] }
  excluded_not_imputed: { count: number; vouchers: ExcludedVoucher[] }
  warnings: string[]
  doubts: { code: string; text: string }[]
  rules_applied: RuleApplied[]
  rule_status: string
}

export interface RateBlock {
  rate_10: { taxed: string; base: string; vat: string }
  rate_5: { taxed: string; base: string; vat: string }
  exempt: string
  vat: string
  count: number
}

export interface Form120Box {
  box: string
  rubro: number
  label: string
  value: string | null
  status: 'calculated' | 'from_previous' | 'not_calculated'
  doubts: string[]
  note: string | null
}

export interface LedgerControlRow {
  field: string
  account_id: string
  account_code: string
  account_name: string
  ledger: string
  estimate: string
  difference: string
  matches: boolean
}

export interface VatEstimate {
  year: number
  month: number
  period_start: string
  period_end: string
  debit: { sales: RateBlock; credit_notes: RateBlock; total: string }
  credit: { purchases: RateBlock; credit_notes: RateBlock; total: string }
  previous_balance: { amount: string; source: 'declared' | 'estimated' | 'none'; month: string; obligation_id: string | null }
  result: { to_pay: string; credit_balance: string }
  proration_warning: boolean
  warnings: { code: string; message: string }[]
  ledger_control: { available: boolean; matches: boolean | null; accounts: LedgerControlRow[]; message: string | null }
  form_120: {
    available: boolean
    version: number | null
    rule: RuleApplied | null
    boxes: Form120Box[]
    warnings: string[]
    message: string | null
  }
  obligation: { id: string; status: ObligationStatus; calculated_amount: string | null; declared_amount: string | null } | null
  rules_applied: RuleApplied[]
  rule_status: string | null
  is_estimate: boolean
}

export type AlertCode =
  | 'OBLIGATIONS_OVERDUE'
  | 'OBLIGATIONS_DUE_SOON'
  | 'REGISTER_UNCONFIRMED'
  | 'MONTHS_WITHOUT_VOUCHERS'
  | 'PROFILE_MISSING'
  | 'PROFILE_UNVERIFIED'
  | 'RULES_UNVERIFIED'
  | 'COUNTERPARTY_RUC_UNCHECKED'

export interface AlertObligationItem {
  id: string
  code: string
  dnit_code: string
  period_start: string
  period_end: string
  due_date: string
  remind_by: string
  shift_explanation: string | null
}

export interface TaxAlert {
  code: AlertCode
  severity: 'danger' | 'warning' | 'info'
  message: string
  count: number
  items: unknown[]
}

export interface TaxAlerts {
  as_of: string
  alert_days: number
  count: number
  alerts: TaxAlert[]
}

export interface TaxSettings {
  accounts: {
    field: string
    label: string
    default_code: string
    configured_id: string | null
    effective_id: string | null
    effective_code: string | null
    effective_name: string | null
  }[]
  alert_days: number
}
