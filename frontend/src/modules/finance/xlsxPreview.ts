/**
 * Lectura mínima de las primeras filas de un XLSX, **solo para mostrar sus columnas** en el
 * asistente de importación. La lectura que cuenta la hace la API (openpyxl, sin fórmulas ni
 * macros). Sin dependencias: el XLSX es un ZIP con XML; se descomprime con la
 * `DecompressionStream` nativa del navegador y se lee con `DOMParser`.
 *
 * Si algo falla, el asistente sigue: se pueden escribir los nombres de columna y la API
 * responde con las columnas disponibles (`IMPORT_COLUMN_NOT_FOUND`, `details.available`).
 */

interface ZipEntry {
  name: string
  method: number
  compressedSize: number
  localOffset: number
}

function readEntries(buf: Uint8Array): Map<string, ZipEntry> {
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  // Fin del directorio central: firma 0x06054b50 en los últimos 64 KB + 22 bytes.
  let eocd = -1
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('No es un ZIP')
  const count = view.getUint16(eocd + 10, true)
  let offset = view.getUint32(eocd + 16, true)
  const entries = new Map<string, ZipEntry>()
  const decoder = new TextDecoder()
  for (let n = 0; n < count; n++) {
    if (view.getUint32(offset, true) !== 0x02014b50) throw new Error('Directorio ZIP dañado')
    const method = view.getUint16(offset + 10, true)
    const compressedSize = view.getUint32(offset + 20, true)
    const nameLen = view.getUint16(offset + 28, true)
    const extraLen = view.getUint16(offset + 30, true)
    const commentLen = view.getUint16(offset + 32, true)
    const localOffset = view.getUint32(offset + 42, true)
    const name = decoder.decode(buf.subarray(offset + 46, offset + 46 + nameLen))
    entries.set(name, { name, method, compressedSize, localOffset })
    offset += 46 + nameLen + extraLen + commentLen
  }
  return entries
}

async function inflate(data: Uint8Array): Promise<Uint8Array> {
  const body = new Response(data as BodyInit).body
  if (!body) throw new Error('No se pudo leer el ZIP')
  return new Uint8Array(await new Response(body.pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer())
}

async function readFile(buf: Uint8Array, entries: Map<string, ZipEntry>, name: string): Promise<string | null> {
  const entry = entries.get(name)
  if (!entry) return null
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength)
  const start = entry.localOffset + 30 + view.getUint16(entry.localOffset + 26, true) + view.getUint16(entry.localOffset + 28, true)
  const raw = buf.subarray(start, start + entry.compressedSize)
  const bytes = entry.method === 0 ? raw : entry.method === 8 ? await inflate(raw) : null
  if (!bytes) throw new Error(`Compresión ZIP no soportada (${entry.method})`)
  return new TextDecoder().decode(bytes)
}

const xml = (text: string) => new DOMParser().parseFromString(text, 'application/xml')
const byTag = (node: Document | Element, tag: string) => Array.from(node.getElementsByTagNameNS('*', tag))

function columnIndex(ref: string): number {
  const letters = /^[A-Z]+/.exec(ref)?.[0] ?? 'A'
  let n = 0
  for (const ch of letters) n = n * 26 + (ch.charCodeAt(0) - 64)
  return n - 1
}

// Formatos de número de fecha incorporados en Excel (ECMA-376, 18.8.30).
const BUILTIN_DATE_FORMATS = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47])

function dateStyles(stylesXml: string | null): Set<number> {
  const dates = new Set<number>()
  if (!stylesXml) return dates
  const doc = xml(stylesXml)
  const custom = new Map<number, string>()
  for (const f of byTag(doc, 'numFmt')) custom.set(Number(f.getAttribute('numFmtId')), f.getAttribute('formatCode') ?? '')
  const cellXfs = byTag(doc, 'cellXfs')[0]
  if (!cellXfs) return dates
  byTag(cellXfs, 'xf').forEach((xf, i) => {
    const id = Number(xf.getAttribute('numFmtId') ?? 0)
    const code = custom.get(id)?.replace(/"[^"]*"|\[[^\]]*\]/g, '') ?? ''
    if (BUILTIN_DATE_FORMATS.has(id) || /[dy]/i.test(code)) dates.add(i)
  })
  return dates
}

/** Número de serie de Excel → "YYYY-MM-DD" (como lo muestra la API en `raw`). */
export function excelSerialToIso(serial: number): string {
  const ms = Math.round((serial - 25569) * 86400 * 1000)
  return new Date(ms).toISOString().slice(0, 10)
}

/** Primeras filas de la primera hoja como texto. */
export async function readXlsxRows(file: Blob, maxRows = 40): Promise<string[][]> {
  const buf = new Uint8Array(await file.arrayBuffer())
  const entries = readEntries(buf)
  const workbook = await readFile(buf, entries, 'xl/workbook.xml')
  const rels = await readFile(buf, entries, 'xl/_rels/workbook.xml.rels')
  let sheetPath = 'xl/worksheets/sheet1.xml'
  if (workbook && rels) {
    const firstSheet = byTag(xml(workbook), 'sheet')[0]
    const rid = firstSheet?.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id') ?? firstSheet?.getAttribute('r:id')
    const target = byTag(xml(rels), 'Relationship').find((r) => r.getAttribute('Id') === rid)?.getAttribute('Target')
    if (target) sheetPath = target.startsWith('/') ? target.slice(1) : `xl/${target.replace(/^\.\//, '')}`
  }
  const sheet = await readFile(buf, entries, sheetPath)
  if (!sheet) throw new Error('El libro no tiene hojas')
  const sharedXml = await readFile(buf, entries, 'xl/sharedStrings.xml')
  const shared = sharedXml ? byTag(xml(sharedXml), 'si').map((si) => byTag(si, 't').map((t) => t.textContent ?? '').join('')) : []
  const dates = dateStyles(await readFile(buf, entries, 'xl/styles.xml'))

  const out: string[][] = []
  for (const row of byTag(xml(sheet), 'row')) {
    const r = Number(row.getAttribute('r') ?? out.length + 1)
    if (r > maxRows) break
    while (out.length < r - 1) out.push([]) // filas vacías intermedias
    const cells: string[] = []
    for (const c of byTag(row, 'c')) {
      const index = columnIndex(c.getAttribute('r') ?? '')
      const type = c.getAttribute('t')
      const v = byTag(c, 'v')[0]?.textContent ?? ''
      let text: string
      if (type === 's') text = shared[Number(v)] ?? ''
      else if (type === 'inlineStr') text = byTag(c, 't').map((t) => t.textContent ?? '').join('')
      else if (type === 'b') text = v === '1' ? 'VERDADERO' : 'FALSO'
      else if (v !== '' && dates.has(Number(c.getAttribute('s') ?? -1))) text = excelSerialToIso(Number(v))
      else text = v
      while (cells.length < index) cells.push('')
      cells[index] = text.trim()
    }
    out.push(cells)
  }
  return out
}
