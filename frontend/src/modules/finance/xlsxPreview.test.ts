import { describe, expect, it } from 'vitest'
import { excelSerialToIso, readXlsxRows } from './xlsxPreview'

/** ZIP mínimo (sin CRC: el lector no lo verifica) con entradas comprimidas o guardadas. */
async function zip(files: Record<string, string>, compress: boolean): Promise<Uint8Array> {
  const enc = new TextEncoder()
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0
  for (const [name, content] of Object.entries(files)) {
    const raw = enc.encode(content)
    const data = compress
      ? new Uint8Array(await new Response(new Response(raw).body!.pipeThrough(new CompressionStream('deflate-raw'))).arrayBuffer())
      : raw
    const nameBytes = enc.encode(name)
    const local = new Uint8Array(30 + nameBytes.length + data.length)
    const lv = new DataView(local.buffer)
    lv.setUint32(0, 0x04034b50, true)
    lv.setUint16(8, compress ? 8 : 0, true)
    lv.setUint32(18, data.length, true)
    lv.setUint32(22, raw.length, true)
    lv.setUint16(26, nameBytes.length, true)
    local.set(nameBytes, 30)
    local.set(data, 30 + nameBytes.length)
    const central = new Uint8Array(46 + nameBytes.length)
    const cv = new DataView(central.buffer)
    cv.setUint32(0, 0x02014b50, true)
    cv.setUint16(10, compress ? 8 : 0, true)
    cv.setUint32(20, data.length, true)
    cv.setUint32(24, raw.length, true)
    cv.setUint16(28, nameBytes.length, true)
    cv.setUint32(42, offset, true)
    central.set(nameBytes, 46)
    locals.push(local)
    centrals.push(central)
    offset += local.length
  }
  const centralSize = centrals.reduce((n, c) => n + c.length, 0)
  const end = new Uint8Array(22)
  const ev = new DataView(end.buffer)
  ev.setUint32(0, 0x06054b50, true)
  ev.setUint16(8, centrals.length, true)
  ev.setUint16(10, centrals.length, true)
  ev.setUint32(12, centralSize, true)
  ev.setUint32(16, offset, true)
  const out = new Uint8Array(offset + centralSize + 22)
  let p = 0
  for (const part of [...locals, ...centrals, end]) {
    out.set(part, p)
    p += part.length
  }
  return out
}

const NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
const FILES = {
  'xl/workbook.xml': `<workbook ${NS} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Extracto" sheetId="1" r:id="rId1"/></sheets></workbook>`,
  'xl/_rels/workbook.xml.rels': `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="worksheet" Target="worksheets/hoja.xml"/></Relationships>`,
  'xl/sharedStrings.xml': `<sst ${NS}><si><t>Fecha</t></si><si><t>Concepto</t></si><si><t>Importe</t></si><si><r><t>Pago </t></r><r><t>ANDE</t></r></si></sst>`,
  'xl/styles.xml': `<styleSheet ${NS}><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>`,
  'xl/worksheets/hoja.xml': `<worksheet ${NS}><sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>Banco Ejemplo</t></is></c></row>
    <row r="3"><c r="A3" t="s"><v>0</v></c><c r="B3" t="s"><v>1</v></c><c r="D3" t="s"><v>2</v></c></row>
    <row r="4"><c r="A4" s="1"><v>46083</v></c><c r="B4" t="s"><v>3</v></c><c r="D4"><v>-150000</v></c></row>
  </sheetData></worksheet>`,
}

describe('readXlsxRows', () => {
  for (const compress of [true, false]) {
    it(`lee la primera hoja ${compress ? 'comprimida' : 'sin comprimir'}: textos compartidos, fechas y huecos`, async () => {
      const file = new Blob([(await zip(FILES, compress)) as BlobPart])
      expect(await readXlsxRows(file)).toEqual([
        ['Banco Ejemplo'],
        [],
        ['Fecha', 'Concepto', '', 'Importe'],
        ['2026-03-02', 'Pago ANDE', '', '-150000'],
      ])
    })
  }

  it('un archivo que no es ZIP falla con un error (el asistente sigue sin vista previa)', async () => {
    await expect(readXlsxRows(new Blob(['hola']))).rejects.toThrow()
  })

  it('convierte el número de serie de Excel', () => {
    expect(excelSerialToIso(46083)).toBe('2026-03-02')
    expect(excelSerialToIso(45658)).toBe('2025-01-01')
  })
})
