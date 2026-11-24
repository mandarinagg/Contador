import { describe, expect, it } from 'vitest'
import { ApiError } from '../../services/api'
import type { Transaction } from '../finance/types'
import { canPropose, postedEntryFromError, postedEntryOf } from './entryRefs'

const tx = (over: Partial<Transaction> = {}): Transaction =>
  ({
    id: 't1',
    voided_at: null,
    transfer_group_id: null,
    journal_entry: null,
    ...over,
  }) as Transaction

describe('canPropose', () => {
  it('ofrece proponer un movimiento sin asiento o con el asiento revertido', () => {
    expect(canPropose(tx())).toBe(true)
    expect(canPropose(tx({ journal_entry: { id: 'e', number: 4, status: 'reversed' } }))).toBe(true)
  })

  it('no ofrece proponer si ya hay borrador o asiento, si está anulado o es transferencia', () => {
    expect(canPropose(tx({ journal_entry: { id: 'e', number: null, status: 'draft' } }))).toBe(false)
    expect(canPropose(tx({ journal_entry: { id: 'e', number: 3, status: 'posted' } }))).toBe(false)
    expect(canPropose(tx({ voided_at: '2026-03-01T10:00:00Z' }))).toBe(false)
    expect(canPropose(tx({ transfer_group_id: 'g' }))).toBe(false)
  })
})

describe('asiento contabilizado que bloquea el movimiento (D-048)', () => {
  it('solo cuenta el asiento contabilizado', () => {
    expect(postedEntryOf({ id: 'e', number: 3, status: 'posted' })).toEqual({ id: 'e', number: 3, status: 'posted' })
    expect(postedEntryOf({ id: 'e', number: null, status: 'draft' })).toBeNull()
    expect(postedEntryOf(null)).toBeNull()
  })

  it('lee el asiento del 409 TRANSACTION_HAS_POSTED_ENTRY', () => {
    const err = new ApiError(409, 'TRANSACTION_HAS_POSTED_ENTRY', 'revertí primero el asiento N° 3', { entry_id: 'e3', number: 3 })
    expect(postedEntryFromError(err)).toEqual({ id: 'e3', number: 3, status: 'posted' })
    expect(postedEntryFromError(new ApiError(409, 'OTRO', 'x'))).toBeNull()
    expect(postedEntryFromError(new Error('x'))).toBeNull()
  })
})
