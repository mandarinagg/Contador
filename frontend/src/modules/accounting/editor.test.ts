import { describe, expect, it } from 'vitest'
import { buildEntry, emptyLine, fingerprint, linesFromEntry, remainderFor, totalsOf } from './editor'
import type { Entry } from './types'

const header = { entry_date: '2026-03-05', description: 'Cobro de factura', document_reference: '' }

describe('totales en vivo del editor', () => {
  it('suma el debe y el haber escritos en formato paraguayo y calcula la diferencia', () => {
    const lines = [emptyLine({ account_id: 'a', debit: '1.500.000' }), emptyLine({ account_id: 'b', credit: '1.000.000' }), emptyLine()]
    expect(totalsOf(lines)).toEqual({ debit: '1500000', credit: '1000000', difference: '500000', balanced: false, hasAmounts: true })
  })

  it('balancea cuando coinciden y no antes', () => {
    const lines = [emptyLine({ account_id: 'a', debit: '1.500.000' }), emptyLine({ account_id: 'b', credit: '1500000' })]
    expect(totalsOf(lines).balanced).toBe(true)
    expect(totalsOf([emptyLine(), emptyLine()]).balanced).toBe(false)
  })

  it('una celda inválida cuenta como cero (el error se muestra en la celda)', () => {
    const lines = [emptyLine({ debit: '1.000,50' }), emptyLine({ credit: 'abc' })]
    expect(totalsOf(lines)).toMatchObject({ debit: '0', credit: '0', hasAmounts: false })
  })

  it('no pierde exactitud con importes enormes', () => {
    const lines = [emptyLine({ debit: '9.007.199.254.740.993' }), emptyLine({ credit: '9.007.199.254.740.992' })]
    expect(totalsOf(lines).difference).toBe('1')
  })

  it('la línea nueva propone lo que falta para balancear, del lado que falta', () => {
    expect(remainderFor([emptyLine({ debit: '1.500.000' }), emptyLine({ credit: '1.000.000' })])).toEqual({ credit: '500.000' })
    expect(remainderFor([emptyLine({ credit: '200' })])).toEqual({ debit: '200' })
    expect(remainderFor([emptyLine({ debit: '5' }), emptyLine({ credit: '5' })])).toEqual({})
  })
})

describe('armado del cuerpo para la API', () => {
  it('borrador desbalanceado: válido, importes como string canónico, líneas vacías descartadas', () => {
    const r = buildEntry({ ...header, document_reference: ' F 001-001-0000001 ' }, [
      emptyLine({ account_id: 'a', debit: '1.500.000', description: ' Cobro ' }),
      emptyLine(),
      emptyLine({ account_id: 'b', credit: '1.000.000' }),
    ])
    expect(r.body).toEqual({
      entry_date: '2026-03-05',
      description: 'Cobro de factura',
      document_reference: 'F 001-001-0000001',
      lines: [
        { account_id: 'a', debit: '1500000', description: 'Cobro' },
        { account_id: 'b', credit: '1000000', description: null },
      ],
    })
  })

  it('cada línea: cuenta y exactamente un importe positivo', () => {
    const lines = [
      emptyLine({ debit: '100' }),
      emptyLine({ account_id: 'b', debit: '100', credit: '100' }),
      emptyLine({ account_id: 'c', description: 'sin importe' }),
      emptyLine({ account_id: 'd', debit: '-100' }),
      emptyLine({ account_id: 'e', credit: '10,5' }),
    ]
    const r = buildEntry(header, lines)
    expect(r.body).toBeNull()
    expect(r.lines[lines[0].key]).toEqual({ account: 'Elegí la cuenta.' })
    expect(r.lines[lines[1].key].amount).toMatch(/no los dos/)
    expect(r.lines[lines[2].key].amount).toMatch(/debe o en el haber/)
    expect(r.lines[lines[3].key].amount).toMatch(/Sin signo/)
    expect(r.lines[lines[4].key].amount).toMatch(/no llevan decimales/)
  })

  it('cabecera obligatoria y al menos una línea', () => {
    const r = buildEntry({ entry_date: '', description: '  ', document_reference: '' }, [emptyLine()])
    expect(r.header.entry_date).toBeTruthy()
    expect(r.header.description).toBeTruthy()
    expect(r.general).toBe('Agregá al menos una línea.')
  })

  it('moneda extranjera completa o nada; cotización con coma decimal', () => {
    const ok = buildEntry(header, [emptyLine({ account_id: 'a', debit: '878.585', fx: { currency: 'USD', amount: '120,35', rate: '7.300,25' } })])
    expect(ok.body?.lines[0]).toMatchObject({ fx_currency: 'USD', fx_amount: '120.35', fx_rate: '7300.25' })
    const partial = [emptyLine({ account_id: 'a', debit: '1', fx: { currency: 'USD', amount: '10', rate: '' } })]
    expect(buildEntry(header, partial).lines[partial[0].key].fx).toMatch(/Completá/)
  })
})

describe('líneas desde un borrador de la API', () => {
  it('lleva los importes a texto de pantalla y deja vacío el lado en cero', () => {
    const entry = {
      lines: [
        { id: '1', line_no: 1, account_id: 'a', account_code: '1', account_name: 'A', debit: '1500000', credit: '0', description: null, fx_currency: 'USD', fx_amount: '120.35', fx_rate: '7300.25' },
        { id: '2', line_no: 2, account_id: 'b', account_code: '2', account_name: 'B', debit: '0', credit: '1500000', description: 'x', fx_currency: null, fx_amount: null, fx_rate: null },
      ],
    } as unknown as Entry
    const lines = linesFromEntry(entry)
    expect(lines[0]).toMatchObject({ debit: '1.500.000', credit: '', fx: { currency: 'USD', amount: '120,35', rate: '7.300,25' } })
    expect(lines[1]).toMatchObject({ debit: '', credit: '1.500.000', description: 'x', fx: null })
    expect(totalsOf(lines).balanced).toBe(true)
  })

  it('la huella ignora las claves internas y las líneas vacías', () => {
    const a = [emptyLine({ account_id: 'a', debit: '1' })]
    const b = [emptyLine({ account_id: 'a', debit: '1' }), emptyLine()]
    expect(fingerprint(header, a)).toBe(fingerprint(header, b))
  })
})
