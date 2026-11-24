/** Marco de contabilidad: el estado del plan de cuentas siempre a la vista (D-038). */
import { Outlet, useMatch } from 'react-router'
import { ChartStatusStrip } from './components'
import { useChart } from './data'

export function AccountingLayout() {
  const chart = useChart()
  // En el plan de cuentas el estado ocupa su propio panel, con las acciones.
  const onChartPage = useMatch('/contabilidad/plan')
  return (
    <>
      {!onChartPage && <ChartStatusStrip settings={chart.data} />}
      <Outlet />
    </>
  )
}
