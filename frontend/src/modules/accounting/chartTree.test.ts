import { describe, expect, it } from 'vitest'
import { buildTree, compareCodes, flatten, idsToDepth, matchesAccount, postableAccounts, suggestChildSegment, visibleRows } from './chartTree'
import type { LedgerAccount } from './types'

function acc(code: string, name: string, parent: string | null, extra: Partial<LedgerAccount> = {}): LedgerAccount {
  return {
    id: code,
    code,
    name,
    kind: 'asset',
    normal_side: 'debit',
    is_postable: false,
    parent_id: parent,
    origin: 'rg49_2014',
    note: null,
    archived_at: null,
    in_use: false,
    ...extra,
  }
}

// Desordenado a propósito: el árbol no depende del orden de llegada.
const PLAN = [
  acc('10', 'GASTOS DE VENTAS', null, { kind: 'expense' }),
  acc('1.01.01.02', 'CAJA', '1.01.01', { is_postable: true }),
  acc('1', 'ACTIVO', null),
  acc('1.01', 'ACTIVO CORRIENTE', '1'),
  acc('1.01.01', 'DISPONIBILIDADES', '1.01'),
  acc('1.01.03', 'CRÉDITOS', '1.01'),
  acc('1.01.03.01', 'DEUDORES POR VENTAS', '1.01.03', { is_postable: true }),
  acc('1.01.01.10', 'BANCO NUEVO', '1.01.01', { is_postable: true, origin: 'user' }),
  acc('1.01.01.03', 'FONDOS FIJOS', '1.01.01', { is_postable: true, archived_at: '2026-01-01T00:00:00Z' }),
  acc('2', 'PASIVO', null, { kind: 'liability', normal_side: 'credit' }),
]

describe('orden de códigos', () => {
  it('por segmentos numéricos, no alfabético', () => {
    const codes = ['10', '2', '1.01.10', '1.01.02', '1', '1.01']
    expect(codes.sort(compareCodes)).toEqual(['1', '1.01', '1.01.02', '1.01.10', '2', '10'])
  })
})

describe('armado del árbol', () => {
  it('jerarquía y profundidad desde la lista plana', () => {
    const roots = buildTree(PLAN)
    expect(roots.map((r) => r.account.code)).toEqual(['1', '2', '10'])
    const disp = flatten(roots).find((n) => n.account.code === '1.01.01')
    expect(disp?.depth).toBe(2)
    expect(disp?.children.map((c) => c.account.code)).toEqual(['1.01.01.02', '1.01.01.03', '1.01.01.10'])
    expect(disp?.parent?.account.code).toBe('1.01')
  })

  it('una cuenta con padre desconocido queda en la raíz (no se pierde)', () => {
    const roots = buildTree([acc('9.01', 'HUÉRFANA', 'no-existe')])
    expect(roots).toHaveLength(1)
  })
})

describe('filas visibles', () => {
  const roots = buildTree(PLAN)

  it('sin expandir: solo las raíces', () => {
    expect(visibleRows(roots, new Set()).map((r) => r.node.account.code)).toEqual(['1', '2', '10'])
  })

  it('expandiendo dos niveles', () => {
    const rows = visibleRows(roots, idsToDepth(roots, 2))
    expect(rows.map((r) => r.node.account.code)).toEqual(['1', '1.01', '1.01.01', '1.01.03', '2', '10'])
    expect(rows[0]).toMatchObject({ expanded: true, hasChildren: true })
    expect(rows.find((r) => r.node.account.code === '2')).toMatchObject({ hasChildren: false })
  })

  it('búsqueda por nombre sin tildes: la cuenta y sus ancestros, expandidos', () => {
    const rows = visibleRows(roots, new Set(), { query: 'creditos' })
    expect(rows.map((r) => [r.node.account.code, r.match])).toEqual([
      ['1', false],
      ['1.01', false],
      ['1.01.03', true],
    ])
    expect(rows[2].hasChildren).toBe(true)
  })

  it('búsqueda por código (prefijo)', () => {
    const rows = visibleRows(roots, new Set(), { query: '1.01.01.1' })
    expect(rows.filter((r) => r.match).map((r) => r.node.account.code)).toEqual(['1.01.01.10'])
  })

  it('ocultar archivadas', () => {
    const all = visibleRows(roots, idsToDepth(roots, 9))
    const active = visibleRows(roots, idsToDepth(roots, 9), { hideArchived: true })
    expect(all.some((r) => r.node.account.code === '1.01.01.03')).toBe(true)
    expect(active.some((r) => r.node.account.code === '1.01.01.03')).toBe(false)
  })
})

describe('ayudas', () => {
  it('coincidencia por código o nombre', () => {
    expect(matchesAccount({ code: '1.01.01.02', name: 'CAJA' }, '1.01')).toBe(true)
    expect(matchesAccount({ code: '1.01.01.02', name: 'CAJA' }, 'caja')).toBe(true)
    expect(matchesAccount({ code: '1.01.01.02', name: 'CAJA' }, '01.02')).toBe(false)
    expect(matchesAccount({ code: '1.01.01.02', name: 'CAJA' }, '1.01.01.02 caja')).toBe(true)
  })

  it('segmento sugerido para una subcuenta', () => {
    expect(suggestChildSegment('1.01.01', ['1.01.01.02', '1.01.01.10', '1.01.01.03'])).toBe('11')
    expect(suggestChildSegment('1.01.01.04', ['1.01.01.04.01', '1.01.01.04.02'])).toBe('03')
    expect(suggestChildSegment('1.02', [])).toBe('01')
    expect(suggestChildSegment(null, ['1', '2', '10'])).toBe('11')
  })

  it('imputables y no archivadas, en orden de código', () => {
    expect(postableAccounts(PLAN).map((a) => a.code)).toEqual(['1.01.01.02', '1.01.01.10', '1.01.03.01'])
  })
})
