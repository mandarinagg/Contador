/**
 * IRP del año (D-144): borrador del IRP-RSP y del Formulario 515 desde el registro de ingresos y
 * egresos (D-143), con el cuadre contra el registro (condición 3 de la D-119 sin contabilidad).
 * Es una estimación interna, como el IVA del mes: se presenta a mano en Marangatu.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CircleCheck, FileSpreadsheet, TriangleAlert } from 'lucide-react'
import { Fragment } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, EmptyState, Field, Input, Notice, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { saveBlob } from '../../lib/download'
import { getBlob, get } from '../../services/api'
import { Pyg } from '../accounting/components'
import { ApiErrorNotice, Th } from '../finance/components'
import { errorMessage } from '../finance/forms'
import { todayIso } from '../finance/labels'
import { DoubtNote, EstimateLegend, ObligationStatusBadge, RulesApplied, UnverifiedMark } from './components'
import { taxKeys, useRulesById, useTaxAlerts } from './data'
import { defaultIrpYear, irpXlsxName } from './logic'
import type { Form515Box, IrpEstimate, RegisterControl } from './types'

const BOX_STATUS: Record<Form515Box['status'], string> = {
  calculated: 'Calculada',
  not_calculated: 'Sin calcular',
  missing_data: 'No calculado: falta el dato',
}

const ORIGIN: Record<NonNullable<Form515Box['origin']>, { label: string; dir: string }> = {
  income: { label: 'Ingresos y ventas del registro', dir: 'income' },
  expense: { label: 'Egresos y compras del registro', dir: 'expense' },
}

function Origin({ box, year }: { box: Form515Box; year: number }) {
  if (box.origin === null) return <span className="text-ink-3">{box.status === 'calculated' ? 'Fórmula del formulario' : '—'}</span>
  const o = ORIGIN[box.origin]
  return (
    <Link to={`/impuestos/comprobantes?mes=${year}-01&dir=${o.dir}`} className="font-medium text-ledger hover:underline">
      {o.label}
    </Link>
  )
}

function Form515({ form, year }: { form: IrpEstimate['form_515']; year: number }) {
  if (!form.available) {
    return (
      <EmptyState title="Borrador del Formulario 515 no disponible">
        {form.message ?? 'Falta la regla del IRP: cargá las reglas candidatas en «Reglas y feriados».'}
      </EmptyState>
    )
  }
  const rubros = [...new Set(form.boxes.map((b) => b.rubro))]
  return (
    <>
      {form.warnings.length > 0 && (
        <ul className="flex flex-col gap-1 border-b border-line px-5 py-3 text-sm text-amber">
          {form.warnings.map((w) => (
            <li key={w} className="flex gap-2">
              <TriangleAlert size={14} className="mt-0.5 shrink-0" aria-hidden />
              {w}
            </li>
          ))}
        </ul>
      )}
      <table className="w-full text-base">
        <caption className="sr-only">Casillas del Formulario 515, versión {form.version}</caption>
        <thead className="text-sm text-ink-2">
          <tr>
            <Th className="w-20">Casilla</Th>
            <Th>Concepto</Th>
            <Th align="right">Importe</Th>
            <Th>Origen</Th>
            <Th>Estado</Th>
          </tr>
        </thead>
        <tbody>
          {rubros.map((r) => (
            <Fragment key={r}>
              <tr className="border-t border-line">
                <th scope="rowgroup" colSpan={5} className="bg-sunken/60 px-4 py-2 text-left font-medium">
                  Rubro {r}
                </th>
              </tr>
              {form.boxes
                .filter((b) => b.rubro === r)
                .map((b) => (
                  <tr key={b.box} data-testid={`f515-${b.box}`} className="border-t border-line align-top">
                    <td className="px-4 py-2 font-medium tabular-nums">{b.box}</td>
                    <td className="px-4 py-2">
                      {b.label}
                      {b.note && <span className="block text-sm text-ink-2">{b.note}</span>}
                      <DoubtNote codes={b.doubts} className="mt-1" />
                    </td>
                    <td className="px-4 py-2 text-right">{b.value === null ? <span className="text-ink-3">Vacía</span> : <Pyg value={b.value} />}</td>
                    <td className="px-4 py-2 text-sm">
                      <Origin box={b} year={year} />
                    </td>
                    <td className={cx('px-4 py-2 text-sm', b.status === 'calculated' ? 'text-ink-2' : 'text-amber')}>{BOX_STATUS[b.status]}</td>
                  </tr>
                ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </>
  )
}

function Cuadre({ control }: { control: RegisterControl }) {
  if (!control.available) return <p className="px-5 py-4 text-sm text-ink-2">{control.message ?? 'Sin cuadre disponible.'}</p>
  return (
    <>
      <p className={cx('flex items-center gap-2 px-5 py-3 text-sm font-medium', control.matches ? 'text-ledger' : 'text-amber')} data-testid="irp-cuadre">
        {control.matches ? <CircleCheck size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
        {control.matches
          ? `El borrador cuadra al guaraní con el registro (${control.vouchers} comprobantes).`
          : (control.message ?? 'El borrador no cuadra con el registro de comprobantes.')}
      </p>
      <table className="w-full text-base">
        <caption className="sr-only">Cuadre del borrador contra el registro de comprobantes</caption>
        <thead className="text-sm text-ink-2">
          <tr>
            <Th>Casilla</Th>
            <Th align="right">Borrador</Th>
            <Th align="right">Registro</Th>
            <Th align="right">Diferencia</Th>
          </tr>
        </thead>
        <tbody>
          {control.rows.map((r) => (
            <tr key={r.box} className="border-t border-line">
              <td className="px-4 py-2 tabular-nums">{r.box}</td>
              <td className="px-4 py-2 text-right">{r.draft === null ? <span className="text-ink-3">Vacía</span> : <Pyg value={r.draft} />}</td>
              <td className="px-4 py-2 text-right"><Pyg value={r.register} /></td>
              <td className={cx('px-4 py-2 text-right', !r.matches && 'font-semibold text-amber')}>
                {r.difference === null ? '—' : <Pyg value={r.difference} />}
                {!r.matches && <span className="sr-only"> (no cuadra)</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

export function IrpPage() {
  const toast = useToast()
  const alerts = useTaxAlerts()
  const byId = useRulesById()
  const [params, setParams] = useSearchParams()
  const today = alerts.data?.as_of ?? todayIso()
  const year = /^\d{4}$/.test(params.get('anio') ?? '') ? Number(params.get('anio')) : defaultIrpYear(today)
  const setYear = (y: number) => setParams(new URLSearchParams({ anio: String(y) }), { replace: true })

  const irp = useQuery({ queryKey: [...taxKeys.irp(), year], queryFn: () => get<IrpEstimate>(`/tax/irp/${year}`) })

  const xlsx = useMutation({
    mutationFn: () => getBlob(`/tax/irp/${year}?format=xlsx`),
    onSuccess: ({ blob, filename }) => {
      const name = filename ?? irpXlsxName(year)
      saveBlob(blob, name)
      toast('ok', `Borrador descargado: ${name}`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo generar el borrador.')),
  })

  const v = irp.data
  const pending = v?.rule_status === 'pending'
  const box = (n: string) => v?.form_515.boxes.find((b) => b.box === n)?.value ?? null

  return (
    <>
      <PageHeader
        title="IRP del año"
        description="Borrador del IRP por servicios personales y del Formulario 515, a partir de tu registro de ingresos y egresos. La declaración se presenta en Marangatu: esto sirve para prepararla y controlarla."
        actions={
          <Button variant="secondary" busy={xlsx.isPending} disabled={!v} onClick={() => xlsx.mutate()}>
            <FileSpreadsheet size={15} aria-hidden />
            Descargar borrador
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <Button type="button" variant="ghost" className="px-2" aria-label="Año anterior" onClick={() => setYear(year - 1)}>
          <ChevronLeft size={16} aria-hidden />
        </Button>
        <Field label="Ejercicio">
          {(p) => (
            <Input
              {...p}
              type="number"
              min={2000}
              max={2100}
              className="w-28"
              value={year}
              onChange={(e) => {
                const y = Number(e.target.value)
                if (y >= 2000 && y <= 2100) setYear(y)
              }}
            />
          )}
        </Field>
        <Button type="button" variant="ghost" className="px-2" aria-label="Año siguiente" onClick={() => setYear(year + 1)}>
          <ChevronRight size={16} aria-hidden />
        </Button>
      </div>

      {irp.isError ? (
        <ApiErrorNotice error={irp.error} title={`No se pudo armar el borrador del IRP de ${year}.`} />
      ) : !v ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <EstimateLegend />
            {pending && (
              <Notice tone="warn" title="Las reglas del IRP están sin verificar contra la fuente oficial">
                Las tasas, el monto no alcanzado y las casillas del 515 salen de reglas pendientes: el borrador sirve para controlar, no para presentar tal cual. Verificalas en{' '}
                <Link to="/impuestos/reglas" className="font-medium text-ledger hover:underline">
                  Reglas y feriados
                </Link>
                .
              </Notice>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <UnverifiedMark status={v.rule_status} />
              <RulesApplied rules={v.rules_applied} byId={byId} summary="Reglas aplicadas" />
              {v.obligation && (
                <span className="flex items-center gap-2 text-sm text-ink-2">
                  Obligación del año: <ObligationStatusBadge status={v.obligation.status} />
                </span>
              )}
            </div>
            {v.warnings
              .filter((w) => w.code !== 'RULE_PENDING')
              .map((w) => (
                <Notice key={w.code} tone="warn" title={w.message} />
              ))}
          </div>

          {v.result && (
            <section aria-label="Resultado del año" className="grid grid-cols-4 gap-4">
              <Sheet className="p-5">
                <p className="text-sm text-ink-2">Ingresos gravados (14)</p>
                <p className="mt-1 text-lg"><Pyg value={box('14') ?? '0'} strong /></p>
              </Sheet>
              <Sheet className="p-5">
                <p className="text-sm text-ink-2">Egresos deducidos (26)</p>
                <p className="mt-1 text-lg"><Pyg value={box('26') ?? '0'} strong /></p>
              </Sheet>
              <Sheet className="p-5">
                <p className="text-sm text-ink-2">Renta neta imponible (45)</p>
                <p className="mt-1 text-lg"><Pyg value={v.result.net_income} strong /></p>
              </Sheet>
              <Sheet className="p-5">
                <p className="text-sm text-ink-2">IRP a pagar (estimado)</p>
                <p className="mt-1 text-lg" data-testid="irp-to-pay">
                  <span className="ledger-rule"><Pyg value={v.result.to_pay} strong /></span>
                </p>
                {v.threshold && !v.threshold.reached && (
                  <p className="mt-1 text-sm text-ink-3">
                    No superás <Pyg value={v.threshold.amount} />: la DJ se presenta igual.
                  </p>
                )}
              </Sheet>
            </section>
          )}

          <Sheet>
            <h2 className="border-b border-line px-5 py-3.5 font-semibold">Cuadre con el registro de comprobantes</h2>
            <Cuadre control={v.register_control} />
          </Sheet>

          <Sheet>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
              <h2 className="font-semibold">
                Borrador del Formulario 515{v.form_515.version !== null && <span className="font-normal text-ink-2"> · versión {v.form_515.version}</span>}
              </h2>
              {v.form_515.rule && <UnverifiedMark status={v.form_515.rule.validation_status} />}
            </div>
            <Form515 form={v.form_515} year={year} />
          </Sheet>

          <p className="text-sm text-ink-2">
            Los importes salen de los comprobantes del año que imputan al IRP, en{' '}
            <Link to={`/impuestos/comprobantes?mes=${year}-01`} className="font-medium text-ledger hover:underline">
              Comprobantes
            </Link>
            .
          </p>
        </div>
      )}
    </>
  )
}
