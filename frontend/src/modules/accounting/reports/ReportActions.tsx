/** Exportar un reporte: XLSX desde la API (D-063) e impresión, que también sirve para guardar en PDF. */
import { useMutation } from '@tanstack/react-query'
import { FileSpreadsheet, Printer } from 'lucide-react'
import { Button } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { type ExportReport, exportFilename, saveBlob } from '../../../lib/download'
import { getBlob } from '../../../services/api'
import { errorMessage } from '../../finance/forms'

export function ReportActions({
  path,
  report,
  scope,
  disabled,
}: {
  /** Ruta del reporte en la API, ya con sus parámetros (sin `format`). */
  path: string
  report: ExportReport
  scope: { from?: string; to?: string; at?: string }
  disabled?: boolean
}) {
  const toast = useToast()
  const download = useMutation({
    mutationFn: () => getBlob(`${path}${path.includes('?') ? '&' : '?'}format=xlsx`),
    onSuccess: ({ blob, filename }) => {
      const name = filename ?? exportFilename(report, scope)
      saveBlob(blob, name)
      toast('ok', `Excel descargado: ${name}`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo generar el Excel.')),
  })
  return (
    <div data-print="hide" className="flex shrink-0 flex-wrap justify-end gap-2">
      <Button variant="secondary" className="h-8" busy={download.isPending} disabled={disabled} onClick={() => download.mutate()}>
        <FileSpreadsheet size={15} aria-hidden />
        Descargar Excel
      </Button>
      <Button variant="secondary" className="h-8" disabled={disabled} onClick={() => window.print()} title="Abre la impresión: elegí la impresora o «Guardar como PDF»">
        <Printer size={15} aria-hidden />
        Imprimir / PDF
      </Button>
    </div>
  )
}
