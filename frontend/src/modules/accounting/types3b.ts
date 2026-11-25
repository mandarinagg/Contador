/**
 * Tipos de la API de la fase 3B (espejo de backend/app/modules/accounting/schemas_3b.py):
 * activos fijos, depreciación, centros de costos y asientos recurrentes. Importes como
 * string en guaraníes enteros; porcentajes como string con hasta dos decimales.
 */
import type { ChartStatus, Entry, EntryLineIn, StartRule } from './types'

export type ValidationStatus = 'pending' | 'validated'

export interface AssetCategory {
  id: string
  code: string | null
  name: string
  useful_life_months: number | null
  residual_rate: string | null
  asset_account_id: string | null
  accumulated_account_id: string | null
  expense_account_id: string | null
  source_url: string | null
  legal_reference: string | null
  citation: string | null
  note: string | null
  validation_status: ValidationStatus
  validated_by_name: string | null
  validated_reference: string | null
  validated_at: string | null
  archived_at: string | null
  /** Se puede usar: vida útil, residual y las tres cuentas válidas (D-068). */
  complete: boolean
  /** Lo que le falta, en palabras ("vida útil", "cuenta de gasto"). */
  missing: string[]
}

export interface AssetCategoryIn {
  name: string
  useful_life_months?: number | null
  residual_rate?: string | null
  asset_account_id?: string | null
  accumulated_account_id?: string | null
  expense_account_id?: string | null
  note?: string | null
  archived?: boolean
}

export type AssetStatus = 'active' | 'disposed'
export type DisposalKind = 'sale' | 'scrap' | 'donation'
export type InstallmentStatus = 'posted' | 'draft' | 'pending'

export interface Installment {
  installment: number
  /** Primer día del mes de la cuota. */
  month: string
  amount: string
  status: InstallmentStatus
  entry_id: string | null
}

export interface FixedAsset {
  id: string
  category_id: string
  category_name: string
  name: string
  description: string | null
  serial_or_reference: string | null
  acquired_on: string
  start_rule: StartRule
  depreciation_start: string
  cost: string
  residual_value: string
  useful_life_months: number
  fiscal_useful_life_months: number
  fiscal_residual_rate: string
  fiscal_residual_value: string
  /** D-125: autorización de la DNIT para una vida útil o residual fiscal fuera de la categoría. */
  fiscal_life_authorization: string | null
  acquisition_entry_id: string | null
  source_transaction_id: string | null
  status: AssetStatus
  disposed_on: string | null
  disposal_kind: DisposalKind | null
  disposal_reason: string | null
  disposal_document_reference: string | null
  disposal_entry_id: string | null
  accumulated_depreciation: string
  net_book_value: string
  warnings: string[]
  created_at: string
  /** Solo en el detalle (y en el alta). */
  installments: Installment[] | null
}

export interface FixedAssetIn {
  category_id?: string
  name?: string
  description?: string | null
  serial_or_reference?: string | null
  acquired_on?: string
  cost?: string
  residual_value?: string
  useful_life_months?: number
  fiscal_useful_life_months?: number
  fiscal_residual_rate?: string
  fiscal_life_authorization?: string | null
  start_rule?: StartRule
  acquisition_entry_id?: string | null
}

export interface DepreciationItem {
  asset_id: string
  asset_name: string
  category_id: string
  installment: number
  amount: string
}

export interface DepreciationRun {
  id: string
  period_id: string
  entry_id: string
  entry_status: Entry['status']
  total: string
  created_at: string
  entry: Entry | null
  items: DepreciationItem[] | null
}

// --- Cuadro de depreciación (RG 77/2020) ------------------------------------------------

export interface ScheduleRow {
  asset_id: string
  description: string
  acquired_on: string
  disposed_on: string | null
  cost: string
  revaluation_coefficient: string
  fiscal_residual_rate: string
  fiscal_residual_value: string
  fiscal_useful_life_months: number
  fiscal_useful_life_years: string
  fiscal_remaining_months: number
  fiscal_remaining_years: string
  fiscal_net_previous: string
  fiscal_depreciable: string
  fiscal_depreciation: string
  fiscal_accumulated: string
  fiscal_net_value: string
  residual_value: string
  useful_life_months: number
  useful_life_years: string
  remaining_months: number
  remaining_years: string
  accounting_net_previous: string
  accounting_depreciable: string
  accounting_depreciation: string
  non_deductible: string
  accounting_accumulated: string
  accounting_net_value: string
}

export type ScheduleTotals = Pick<
  ScheduleRow,
  | 'cost'
  | 'fiscal_residual_value'
  | 'fiscal_net_previous'
  | 'fiscal_depreciable'
  | 'fiscal_depreciation'
  | 'fiscal_accumulated'
  | 'fiscal_net_value'
  | 'residual_value'
  | 'accounting_net_previous'
  | 'accounting_depreciable'
  | 'accounting_depreciation'
  | 'non_deductible'
  | 'accounting_accumulated'
  | 'accounting_net_value'
>

export interface DepreciationSchedule {
  chart_status: ChartStatus
  fiscal_year_id: string
  date_from: string
  date_to: string
  warnings: string[]
  categories: { category_id: string; name: string; validation_status: ValidationStatus; assets: ScheduleRow[]; totals: ScheduleTotals }[]
  totals: ScheduleTotals
  reconciliation: {
    lines: { account_id: string; code: string; name: string; ledger_balance: string; schedule_amount: string; difference: string }[]
    schedule_total: string
    ledger_total: string
    reconciled: boolean
  }
}

// --- Centros de costos y recurrentes ------------------------------------------------------

export interface CostCenter {
  id: string
  code: string
  name: string
  archived_at: string | null
}

export type TemplateStatus = 'active' | 'paused'

export interface RecurringLine {
  line_no: number
  account_id: string
  account_code: string
  account_name: string
  debit: string
  credit: string
  description: string | null
  cost_center_id: string | null
}

export interface RecurringTemplate {
  id: string
  description: string
  document_reference: string | null
  day_of_month: number
  start_date: string
  end_date: string | null
  status: TemplateStatus
  total: string
  lines: RecurringLine[]
  created_at: string
}

export interface RecurringTemplateIn {
  description: string
  document_reference: string | null
  day_of_month: number
  start_date: string
  end_date: string | null
  status: TemplateStatus
  lines: EntryLineIn[]
}

export interface RecurringDue {
  template_id: string
  description: string
  entry_date: string
  total: string
}

export interface RecurringGenerated {
  created: Entry[]
  existing: Entry[]
}
