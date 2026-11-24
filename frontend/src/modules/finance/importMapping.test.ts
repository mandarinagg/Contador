import { describe, expect, it } from 'vitest'
import {
  buildMapping,
  decodeText,
  detectDelimiter,
  EMPTY_FORM,
  formFromMapping,
  guessMapping,
  initialForm,
  missingColumns,
  parseCsv,
  tableView,
} from './importMapping'

const ITAU = [
  'Banco Ejemplo S.A.;;;;',
  'Extracto de cuenta corriente;;;;',
  'Fecha;Concepto;Nro. Operación;Débito;Crédito',
  '02/03/2026;Pago ANDE;1001;150.000;',
  '05/03/2026;"Transferencia; cliente";1002;;2.500.000',
  ';;;;',
].join('\r\n')

describe('lectura del CSV', () => {
  it('decodifica UTF-8 y, si no lo es, Windows-1252 (como la API)', () => {
    expect(decodeText(new TextEncoder().encode('Débito'))).toEqual({ text: 'Débito', encoding: 'utf-8' })
    // "Débito" en Windows-1252: la é es 0xE9, inválida como UTF-8.
    const cp1252 = new Uint8Array([0x44, 0xe9, 0x62, 0x69, 0x74, 0x6f])
    expect(decodeText(cp1252)).toEqual({ text: 'Débito', encoding: 'cp1252' })
  })

  it('detecta el separador', () => {
    expect(detectDelimiter(ITAU)).toBe(';')
    expect(detectDelimiter('a,b,c\n1,2,3\n4,5,6')).toBe(',')
    expect(detectDelimiter('a\tb\n1\t2')).toBe('\t')
    expect(detectDelimiter('fecha|monto\n01/01/2026|5')).toBe('|')
  })

  it('respeta las comillas y las comillas dobles', () => {
    expect(parseCsv('a;"b;c";"d ""e"""\n1;2;3', ';')).toEqual([
      ['a', 'b;c', 'd "e"'],
      ['1', '2', '3'],
    ])
    expect(parseCsv('﻿x,y\r\n1,2\r\n', ',')).toEqual([
      ['x', 'y'],
      ['1', '2'],
    ])
  })
})

describe('tableView', () => {
  const rows = parseCsv(ITAU, ';')

  it('saltea filas, ignora vacías y toma el encabezado', () => {
    const view = tableView(rows, 2, true)
    expect(view.columns).toEqual(['Fecha', 'Concepto', 'Nro. Operación', 'Débito', 'Crédito'])
    expect(view.data.map((r) => r.line)).toEqual([4, 5])
    expect(view.data[1].cells[1]).toBe('Transferencia; cliente')
  })

  it('sin encabezado las columnas se nombran por posición', () => {
    const view = tableView(rows, 3, false)
    expect(view.header).toEqual([])
    expect(view.columns).toEqual(['1', '2', '3', '4', '5'])
    expect(view.data).toHaveLength(2)
  })
})

describe('guessMapping', () => {
  it('reconoce los encabezados típicos de un extracto con débito y crédito', () => {
    const form = guessMapping(tableView(parseCsv(ITAU, ';'), 2, true), { ...EMPTY_FORM, skip_rows: '2' })
    expect(form).toMatchObject({
      date_column: 'Fecha',
      description_column: 'Concepto',
      reference_column: 'Nro. Operación',
      amount_mode: 'split',
      debit_column: 'Débito',
      credit_column: 'Crédito',
      date_format: '%d/%m/%Y',
    })
  })

  it('importe único y fecha ISO', () => {
    const view = tableView(parseCsv('Fecha,Descripción,Monto\n2026-03-01,Venta,100', ','), 0, true)
    expect(guessMapping(view, EMPTY_FORM)).toMatchObject({ amount_mode: 'single', amount_column: 'Monto', date_format: '%Y-%m-%d' })
  })
})

describe('initialForm', () => {
  it('encuentra el encabezado después de los títulos del banco y propone el mapeo', () => {
    const form = initialForm(parseCsv(ITAU, ';'), ';', 'utf-8')
    expect(form).toMatchObject({ skip_rows: '2', has_header: true, delimiter: ';', encoding: 'utf-8', debit_column: 'Débito', credit_column: 'Crédito' })
  })

  it('sin encabezado reconocible no saltea filas ni asume encabezado', () => {
    const form = initialForm(parseCsv('01/03/2026;Venta;100', ';'), ';')
    expect(form).toMatchObject({ skip_rows: '0', has_header: false })
  })
})

describe('buildMapping', () => {
  const filled = {
    ...EMPTY_FORM,
    skip_rows: '2',
    date_column: 'Fecha',
    description_column: ' Concepto ',
    reference_column: '',
    amount_mode: 'split' as const,
    debit_column: 'Débito',
    credit_column: 'Crédito',
  }

  it('arma el mapeo exacto de la API', () => {
    expect(buildMapping(filled).mapping).toEqual({
      has_header: true,
      delimiter: ';',
      encoding: 'auto',
      date_column: 'Fecha',
      date_format: '%d/%m/%Y',
      description_column: 'Concepto',
      reference_column: null,
      amount: { mode: 'split', debit_column: 'Débito', credit_column: 'Crédito' },
      decimal_separator: ',',
      thousands_separator: '.',
      skip_rows: 2,
    })
  })

  it('importe único: solo la columna del importe', () => {
    const r = buildMapping({ ...filled, amount_mode: 'single', amount_column: 'Importe', skip_rows: '' })
    expect(r.mapping?.amount).toEqual({ mode: 'single', column: 'Importe' })
    expect(r.mapping?.skip_rows).toBe(0)
  })

  it('valida columnas obligatorias, separadores y filas a saltear', () => {
    const r = buildMapping({ ...EMPTY_FORM, thousands_separator: ',', decimal_separator: ',', skip_rows: '-1', date_format: 'dd/mm' })
    expect(r.errors).toMatchObject({
      date_column: 'Elegí la columna.',
      description_column: 'Elegí la columna.',
      amount_column: 'Elegí la columna.',
      thousands_separator: 'Tiene que ser distinto del separador decimal.',
      skip_rows: 'Un número entre 0 y 1000.',
      date_format: 'El formato usa códigos como %d/%m/%Y.',
    })
    expect(buildMapping({ ...filled, credit_column: 'Débito' }).errors?.credit_column).toBe('Débito y crédito son columnas distintas.')
  })

  it('ida y vuelta: el mapeo de un lote anterior vuelve al formulario', () => {
    const mapping = buildMapping(filled).mapping
    if (!mapping) throw new Error('mapeo inválido')
    expect(buildMapping(formFromMapping(mapping)).mapping).toEqual(mapping)
  })
})

describe('missingColumns', () => {
  it('avisa las columnas del mapeo que no están en el archivo, sin distinguir tildes ni mayúsculas', () => {
    const form = { ...EMPTY_FORM, date_column: 'fecha', description_column: 'Concepto', amount_column: 'Importe' }
    expect(missingColumns(form, ['Fecha', 'Concepto', 'Débito'])).toEqual(['Importe'])
    expect(missingColumns(form, [])).toEqual([])
  })
})
