import { describe, expect, it } from 'vitest'
import { auditActionLabel } from './format'

describe('acciones de la auditoría', () => {
  it('nombra las de contabilidad, incluidas las de la fase 3B', () => {
    expect(auditActionLabel('accounting.journal_entry.posted')).toBe('Asiento contabilizado')
    expect(auditActionLabel('accounting.fixed_asset.disposed')).toBe('Bien de uso dado de baja')
    expect(auditActionLabel('accounting.depreciation_run.created')).toMatch(/Depreciación del mes/)
    expect(auditActionLabel('accounting.recurring_generation.created')).toBe('Asiento recurrente generado')
    expect(auditActionLabel('accounting.ledger_account.archived')).toBe('Cuenta contable archivada')
  })

  it('mantiene las de finanzas y deja tal cual las desconocidas', () => {
    expect(auditActionLabel('finance.transaction.voided')).toBe('Movimiento anulado')
    expect(auditActionLabel('accounting.algo.nuevo')).toBe('accounting.algo.nuevo')
  })
})
