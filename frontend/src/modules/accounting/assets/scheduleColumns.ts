/** Columnas del Anexo de la RG 77/2020 para el cuadro de depreciación (D-067). */
import { formatBookDate } from '../../finance/labels'
import type { ScheduleRow, ScheduleTotals } from '../types3b'

type Money = keyof ScheduleTotals

export interface Col {
  n: number
  title: string
  /** Importe con total (si no, un dato del bien). */
  money?: Money
  render?: (r: ScheduleRow) => string
}

const years = (v: string) => v.replace('.', ',')
const pct = (v: string) => `${v.replace('.', ',')} %`

/** Columnas del Anexo de la RG 77/2020; la 1 (descripción) va siempre fija a la izquierda. */
export const COMMON_COLS: Col[] = [
  { n: 3, title: 'Fecha de adquisición', render: (r) => formatBookDate(r.acquired_on) },
  { n: 2, title: 'Valor de costo', money: 'cost' },
]

export const FISCAL_COLS: Col[] = [
  { n: 4, title: 'Coef. de revalúo', render: (r) => r.revaluation_coefficient.replace('.', ',') },
  { n: 5, title: '% residual fiscal', render: (r) => pct(r.fiscal_residual_rate) },
  { n: 6, title: 'Valor residual fiscal', money: 'fiscal_residual_value' },
  { n: 7, title: 'Vida útil (años)', render: (r) => years(r.fiscal_useful_life_years) },
  { n: 8, title: 'Vida útil restante (años)', render: (r) => years(r.fiscal_remaining_years) },
  { n: 9, title: 'Neto fiscal del ejercicio anterior', money: 'fiscal_net_previous' },
  { n: 10, title: 'Neto anterior menos residual', money: 'fiscal_depreciable' },
  { n: 11, title: 'Cuota fiscal del ejercicio', money: 'fiscal_depreciation' },
  { n: 12, title: 'Depreciación fiscal acumulada', money: 'fiscal_accumulated' },
  { n: 13, title: 'Neto fiscal al cierre', money: 'fiscal_net_value' },
]

export const ACCOUNTING_COLS: Col[] = [
  { n: 14, title: 'Valor residual contable', money: 'residual_value' },
  { n: 15, title: 'Vida útil (años)', render: (r) => years(r.useful_life_years) },
  { n: 16, title: 'Vida útil restante (años)', render: (r) => years(r.remaining_years) },
  { n: 17, title: 'Neto contable del ejercicio anterior', money: 'accounting_net_previous' },
  { n: 18, title: 'Neto anterior menos residual', money: 'accounting_depreciable' },
  { n: 19, title: 'Cuota contable del ejercicio', money: 'accounting_depreciation' },
  { n: 20, title: 'Cuota no deducible', money: 'non_deductible' },
  { n: 21, title: 'Depreciación contable acumulada', money: 'accounting_accumulated' },
  { n: 22, title: 'Neto contable al cierre', money: 'accounting_net_value' },
]
