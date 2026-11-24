import { describe, expect, it } from 'vitest'
import { filenameFromDisposition } from '../services/api'
import { exportFilename } from './download'

describe('nombre del Excel descargado', () => {
  it('lee el nombre que manda la API en Content-Disposition', () => {
    expect(filenameFromDisposition('attachment; filename="libro-diario-2026-01-01-2026-12-31.xlsx"')).toBe('libro-diario-2026-01-01-2026-12-31.xlsx')
    expect(filenameFromDisposition('attachment; filename=balance.xlsx')).toBe('balance.xlsx')
    expect(filenameFromDisposition("attachment; filename*=UTF-8''cuadro%20de%20depreciaci%C3%B3n.xlsx")).toBe('cuadro de depreciación.xlsx')
  })

  it('nunca devuelve una ruta ni un nombre vacío', () => {
    expect(filenameFromDisposition('attachment; filename="../../etc/passwd"')).toBe('passwd')
    expect(filenameFromDisposition('attachment; filename="C:\\temp\\x.xlsx"')).toBe('x.xlsx')
    expect(filenameFromDisposition('attachment; filename=""')).toBeNull()
    expect(filenameFromDisposition('attachment')).toBeNull()
    expect(filenameFromDisposition(null)).toBeNull()
  })

  it('sin la cabecera (CORS), arma el mismo nombre que la API', () => {
    const range = { from: '2026-01-01', to: '2026-03-31' }
    expect(exportFilename('journal', range)).toBe('libro-diario-2026-01-01-2026-03-31.xlsx')
    expect(exportFilename('ledger', range)).toBe('libro-mayor-2026-01-01-2026-03-31.xlsx')
    expect(exportFilename('trial-balance', range)).toBe('balance-de-comprobacion-2026-01-01-2026-03-31.xlsx')
    expect(exportFilename('income-statement', range)).toBe('estado-de-resultados-2026-01-01-2026-03-31.xlsx')
    expect(exportFilename('balance-sheet', { at: '2026-03-31' })).toBe('balance-general-2026-03-31.xlsx')
    expect(exportFilename('depreciation-schedule', {})).toBe('cuadro-de-depreciacion.xlsx')
  })
})
