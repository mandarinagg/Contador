import { describe, expect, it } from 'vitest'
import type { DepreciationRun, Installment } from '../types3b'
import { byYear, disposeErrors, liveRunByMonth, planTotals } from './logic'
import { ACCOUNTING_COLS, COMMON_COLS, FISCAL_COLS } from './scheduleColumns'

const inst = (n: number, month: string, amount: string, status: Installment['status']): Installment => ({
  installment: n,
  month,
  amount,
  status,
  entry_id: status === 'pending' ? null : `e${n}`,
})

describe('plan de cuotas en pantalla', () => {
  const plan = [
    inst(1, '2026-11-01', '450000', 'posted'),
    inst(2, '2026-12-01', '450000', 'draft'),
    inst(3, '2027-01-01', '450000', 'pending'),
    inst(4, '2027-02-01', '450001', 'pending'),
  ]

  it('suma por estado con BigInt y el total cuadra', () => {
    const t = planTotals(plan)
    expect(t.posted).toEqual({ count: 1, amount: '450000' })
    expect(t.draft).toEqual({ count: 1, amount: '450000' })
    expect(t.pending).toEqual({ count: 2, amount: '900001' })
    expect(t.total).toBe('1800001')
  })

  it('agrupa por año calendario en orden', () => {
    expect(byYear(plan).map(([y, rows]) => [y, rows.map((r) => r.installment)])).toEqual([
      ['2026', [1, 2]],
      ['2027', [3, 4]],
    ])
  })
})

describe('baja de un bien', () => {
  it('el acta es obligatoria, igual que la fecha y el motivo', () => {
    expect(disposeErrors({ date: '', reason: 'x', document: ' ' })).toEqual({
      date: expect.any(String),
      reason: expect.any(String),
      document: expect.stringContaining('acta'),
    })
    expect(disposeErrors({ date: '2026-03-15', reason: 'Rota sin reparación', document: 'Acta 3/2026' })).toEqual({
      date: undefined,
      reason: undefined,
      document: undefined,
    })
  })
})

describe('corridas de depreciación', () => {
  it('solo cuentan las vivas (borrador o contabilizada), no las revertidas ni descartadas', () => {
    const run = (id: string, period: string, status: DepreciationRun['entry_status']) =>
      ({ id, period_id: period, entry_id: `e-${id}`, entry_status: status, total: '1', created_at: '', entry: null, items: null }) as DepreciationRun
    const map = liveRunByMonth([run('a', 'p1', 'reversed'), run('b', 'p1', 'posted'), run('c', 'p2', 'discarded'), run('d', 'p3', 'draft')])
    expect([...map.entries()].map(([p, r]) => [p, r.id])).toEqual([
      ['p1', 'b'],
      ['p3', 'd'],
    ])
  })
})

describe('columnas del cuadro (RG 77/2020)', () => {
  it('la vista fiscal tiene las columnas 2 a 13 y la contable, 2, 3 y 14 a 22', () => {
    const nums = (cols: { n: number }[]) => cols.map((c) => c.n).sort((a, b) => a - b)
    expect(nums([...COMMON_COLS, ...FISCAL_COLS])).toEqual([2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    expect(nums([...COMMON_COLS, ...ACCOUNTING_COLS])).toEqual([2, 3, 14, 15, 16, 17, 18, 19, 20, 21, 22])
  })
})
