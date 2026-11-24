/**
 * Guardar un archivo generado por la API. En el navegador y en el WebView de la app de
 * escritorio (WebView2 en Windows) un enlace con `download` sobre un `blob:` abre la descarga
 * normal del sistema, con el nombre indicado.
 */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  a.style.display = 'none'
  document.body.append(a)
  a.click()
  a.remove()
  // Se libera después: algunos motores leen el blob recién al confirmar la descarga.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export type ExportReport = 'journal' | 'ledger' | 'trial-balance' | 'balance-sheet' | 'income-statement' | 'depreciation-schedule'

/**
 * Nombre del XLSX si el navegador no deja leer `Content-Disposition`: el mismo que arma la API
 * (`backend/app/modules/accounting/router.py`, `_xlsx`), para que el archivo se llame igual
 * en cualquier caso.
 */
export function exportFilename(report: ExportReport, scope: { from?: string; to?: string; at?: string }): string {
  const range = `${scope.from}-${scope.to}`
  switch (report) {
    case 'journal':
      return `libro-diario-${range}.xlsx`
    case 'ledger':
      return `libro-mayor-${range}.xlsx`
    case 'trial-balance':
      return `balance-de-comprobacion-${range}.xlsx`
    case 'balance-sheet':
      return `balance-general-${scope.at}.xlsx`
    case 'income-statement':
      return `estado-de-resultados-${range}.xlsx`
    case 'depreciation-schedule':
      return 'cuadro-de-depreciacion.xlsx'
  }
}
