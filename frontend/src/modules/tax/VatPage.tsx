/**
 * IVA del mes (D-090, D-097, D-112): estimación desde los comprobantes cargados, el saldo a
 * favor del mes anterior, el control contra el mayor y el borrador del Formulario 120.
 * Es una estimación interna (BR-TAX-03): se presenta a mano en Marangatu.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CircleCheck, CopyCheck, FileSpreadsheet, TriangleAlert } from 'lucide-react'
import { Fragment } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Button, EmptyState, Field, Input, Notice, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { saveBlob } from '../../lib/download'
import { getBlob, get, post } from '../../services/api'
import { Pyg } from '../accounting/components'
import { ApiErrorNotice, Th } from '../finance/components'
import { errorMessage } from '../finance/forms'
import { todayIso } from '../finance/labels'
import { DoubtNote, EstimateLegend, ObligationStatusBadge, RulesApplied, UnverifiedMark } from './components'
import { taxKeys, useInvalidateTax, useRulesById, useTaxAlerts, useTaxPerms } from './data'
import { monthTitle } from './labels'
import { shiftMonth, vatXlsxName } from './logic'
import type { Form120Box, RateBlock, VatEstimate } from './types'

const PREVIOUS_SOURCE: Record<VatEstimate['previous_balance']['source'], string> = {
  declared: 'declarado en el mes anterior',
  estimated: 'estimado (el mes anterior no tiene lo declarado cargado)',
  none: 'sin saldo anterior',
}

const BOX_STATUS: Record<Form120Box['status'], string> = {
  calculated: 'Calculada',
  from_previous: 'Del mes anterior',
  not_calculated: 'Sin calcular',
}

function BlockRows({ label, block, negative }: { label: string; block: RateBlock; negative?: boolean }) {
  const sign = (v: string) => (negative && v !== '0' ? `-${v}` : v)
  return (
    <>
      <tr className="border-t border-line">
        <th scope="rowgroup" colSpan={4} className="bg-sunken/60 px-4 py-2 text-left font-medium">
          {label} <span className="font-normal text-ink-2">({block.count})</span>
        </th>
      </tr>
      <tr className="border-t border-line">
        <th scope="row" className="px-4 py-2 text-left font-normal text-ink-2">
          Gravado 10 %
        </th>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_10.taxed)} /></td>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_10.base)} muted /></td>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_10.vat)} /></td>
      </tr>
      <tr className="border-t border-line">
        <th scope="row" className="px-4 py-2 text-left font-normal text-ink-2">
          Gravado 5 %
        </th>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_5.taxed)} /></td>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_5.base)} muted /></td>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.rate_5.vat)} /></td>
      </tr>
      <tr className="border-t border-line">
        <th scope="row" className="px-4 py-2 text-left font-normal text-ink-2">
          Exento
        </th>
        <td className="px-4 py-2 text-right"><Pyg value={sign(block.exempt)} /></td>
        <td colSpan={2} />
      </tr>
    </>
  )
}

function SideTable({ title, caption, main, mainLabel, notes, notesLabel, total }: {
  title: string
  caption: string
  main: RateBlock
  mainLabel: string
  notes: RateBlock
  notesLabel: string
  total: string
}) {
  return (
    <Sheet>
      <h2 className="border-b border-line px-5 py-3.5 font-semibold">{title}</h2>
      <table className="w-full text-base">
        <caption className="sr-only">{caption}</caption>
        <thead className="text-sm text-ink-2">
          <tr>
            <Th />
            <Th align="right">Con IVA</Th>
            <Th align="right">Base</Th>
            <Th align="right">IVA</Th>
          </tr>
        </thead>
        <tbody>
          <BlockRows label={mainLabel} block={main} />
          <BlockRows label={notesLabel} block={notes} negative />
        </tbody>
        <tfoot>
          <tr className="border-t border-line-strong">
            <th scope="row" colSpan={3} className="px-4 py-3 text-left font-semibold">
              Total {title.toLowerCase()}
            </th>
            <td className="px-4 py-3 text-right">
              <span className="ledger-rule">
                <Pyg value={total} strong />
              </span>
            </td>
          </tr>
        </tfoot>
      </table>
    </Sheet>
  )
}

function Form120({ form }: { form: VatEstimate['form_120'] }) {
  if (!form.available) {
    return (
      <EmptyState title="Borrador del Formulario 120 no disponible">
        {form.message ?? 'Falta la regla del formulario: cargá las reglas candidatas en «Reglas y feriados».'}
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
        <caption className="sr-only">Casillas del Formulario 120, versión {form.version}</caption>
        <thead className="text-sm text-ink-2">
          <tr>
            <Th className="w-20">Casilla</Th>
            <Th>Concepto</Th>
            <Th align="right">Importe</Th>
            <Th>Estado</Th>
          </tr>
        </thead>
        <tbody>
          {rubros.map((r) => (
            <Fragment key={r}>
              <tr className="border-t border-line">
                <th scope="rowgroup" colSpan={4} className="bg-sunken/60 px-4 py-2 text-left font-medium">
                  Rubro {r}
                </th>
              </tr>
              {form.boxes
                .filter((b) => b.rubro === r)
                .map((b) => (
                  <tr key={b.box} data-testid={`f120-${b.box}`} className="border-t border-line align-top">
                    <td className="px-4 py-2 font-medium tabular-nums">{b.box}</td>
                    <td className="px-4 py-2">
                      {b.label}
                      {b.note && <span className="block text-sm text-ink-2">{b.note}</span>}
                      <DoubtNote codes={b.doubts} className="mt-1" />
                    </td>
                    <td className="px-4 py-2 text-right">{b.value === null ? <span className="text-ink-3">Vacía</span> : <Pyg value={b.value} />}</td>
                    <td className={cx('px-4 py-2 text-sm', b.status === 'not_calculated' ? 'text-amber' : 'text-ink-2')}>{BOX_STATUS[b.status]}</td>
                  </tr>
                ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </>
  )
}

function LedgerControl({ control }: { control: VatEstimate['ledger_control'] }) {
  if (!control.available) return <p className="px-5 py-4 text-sm text-ink-2">{control.message ?? 'Sin contabilidad para comparar.'}</p>
  return (
    <>
      <p className={cx('flex items-center gap-2 px-5 py-3 text-sm font-medium', control.matches ? 'text-ledger' : 'text-amber')}>
        {control.matches ? <CircleCheck size={15} aria-hidden /> : <TriangleAlert size={15} aria-hidden />}
        {control.matches ? 'El mayor coincide con la estimación.' : (control.message ?? 'El mayor no coincide con la estimación: revisá los asientos del mes.')}
      </p>
      <table className="w-full text-base">
        <caption className="sr-only">Control contra el libro mayor</caption>
        <thead className="text-sm text-ink-2">
          <tr>
            <Th>Cuenta</Th>
            <Th align="right">Mayor</Th>
            <Th align="right">Estimación</Th>
            <Th align="right">Diferencia</Th>
          </tr>
        </thead>
        <tbody>
          {control.accounts.map((a) => (
            <tr key={a.field} className="border-t border-line">
              <td className="px-4 py-2">
                <span className="tabular-nums text-ink-2">{a.account_code}</span> {a.account_name}
              </td>
              <td className="px-4 py-2 text-right"><Pyg value={a.ledger} /></td>
              <td className="px-4 py-2 text-right"><Pyg value={a.estimate} /></td>
              <td className={cx('px-4 py-2 text-right', !a.matches && 'font-semibold text-amber')}>
                <Pyg value={a.difference} />
                {!a.matches && <span className="sr-only"> (no coincide)</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

export function VatPage() {
  const perms = useTaxPerms()
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const alerts = useTaxAlerts()
  const byId = useRulesById()
  const [params, setParams] = useSearchParams()
  const today = alerts.data?.as_of ?? todayIso()
  const month = /^\d{4}-\d{2}$/.test(params.get('mes') ?? '') ? (params.get('mes') as string) : shiftMonth(today.slice(0, 7), -1)
  const [year, monthNumber] = month.split('-').map(Number)
  const setMonth = (m: string) => setParams(new URLSearchParams({ mes: m }), { replace: true })

  const vat = useQuery({ queryKey: [...taxKeys.vat(), month], queryFn: () => get<VatEstimate>(`/tax/vat/${year}/${monthNumber}`) })

  const xlsx = useMutation({
    mutationFn: () => getBlob(`/tax/vat/${year}/${monthNumber}?format=xlsx`),
    onSuccess: ({ blob, filename }) => {
      const name = filename ?? vatXlsxName(year, monthNumber)
      saveBlob(blob, name)
      toast('ok', `Excel descargado: ${name}`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo generar el Excel.')),
  })

  const apply = useMutation({
    mutationFn: () => post(`/tax/vat/${year}/${monthNumber}/apply`),
    onSuccess: () => {
      invalidate()
      toast('ok', 'Estimación copiada a la obligación del IVA del mes.')
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo copiar la estimación.')),
  })

  const v = vat.data
  const obligation = v?.obligation ?? null
  const canApply = perms.canManage && obligation !== null && obligation.status === 'pending'
  const applyReason = !perms.canManage
    ? perms.manageReason
    : obligation === null
      ? 'Este mes no tiene obligación del IVA en el calendario (revisá el perfil fiscal).'
      : obligation.status !== 'pending'
        ? 'La obligación del mes ya está presentada: no se recalcula.'
        : ''

  return (
    <>
      <PageHeader
        title="IVA del mes"
        description="Estimación del IVA a partir de los comprobantes cargados, con el borrador del Formulario 120. La declaración se presenta en Marangatu: esto sirve para controlarla."
        actions={
          <>
            <Button variant="secondary" busy={xlsx.isPending} disabled={!v} onClick={() => xlsx.mutate()}>
              <FileSpreadsheet size={15} aria-hidden />
              Descargar Excel
            </Button>
            <Button busy={apply.isPending} disabled={!canApply} title={applyReason || undefined} onClick={() => apply.mutate()}>
              <CopyCheck size={15} aria-hidden />
              Copiar a la obligación
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-end gap-2">
        <Button type="button" variant="ghost" className="px-2" aria-label="Mes anterior" onClick={() => setMonth(shiftMonth(month, -1))}>
          <ChevronLeft size={16} aria-hidden />
        </Button>
        <Field label="Mes">
          {(p) => <Input {...p} type="month" className="w-44" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />}
        </Field>
        <Button type="button" variant="ghost" className="px-2" aria-label="Mes siguiente" onClick={() => setMonth(shiftMonth(month, 1))}>
          <ChevronRight size={16} aria-hidden />
        </Button>
        {applyReason && v && <p className="ml-4 pb-2 text-sm text-ink-3">{applyReason}</p>}
      </div>

      {vat.isError ? (
        <ApiErrorNotice error={vat.error} title="No se pudo calcular el IVA del mes." />
      ) : !v ? (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-10" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-3">
            <EstimateLegend />
            <div className="flex flex-wrap items-center gap-3">
              <UnverifiedMark status={v.rule_status} />
              <RulesApplied rules={v.rules_applied} byId={byId} summary="Reglas aplicadas" />
              {obligation && (
                <span className="flex items-center gap-2 text-sm text-ink-2">
                  Obligación del mes: <ObligationStatusBadge status={obligation.status} />
                  {obligation.calculated_amount !== null && (
                    <>
                      calculado <Pyg value={obligation.calculated_amount} />
                    </>
                  )}
                </span>
              )}
            </div>
            {v.proration_warning && (
              <Notice tone="warn" title="Hay ventas exentas y compras con IVA: puede corresponder el prorrateo del crédito fiscal">
                La app no prorratea todavía (D-F4-14): las casillas del prorrateo quedan vacías hasta resolverlo contra la norma.
              </Notice>
            )}
            {v.warnings.map((w) => (
              <Notice key={w.code} tone="warn" title={w.message} />
            ))}
          </div>

          <section aria-label="Resultado del mes" className="grid grid-cols-3 gap-4">
            <Sheet className="p-5">
              <p className="text-sm text-ink-2">Saldo a favor anterior</p>
              <p className="mt-1 text-lg">
                <Pyg value={v.previous_balance.amount} strong />
              </p>
              <p className="mt-1 text-sm text-ink-3">
                {monthTitle(v.previous_balance.month.slice(0, 7))}: {PREVIOUS_SOURCE[v.previous_balance.source]}
              </p>
            </Sheet>
            <Sheet className="p-5">
              <p className="text-sm text-ink-2">IVA a pagar (estimado)</p>
              <p className="mt-1 text-lg" data-testid="vat-to-pay">
                <span className="ledger-rule">
                  <Pyg value={v.result.to_pay} strong />
                </span>
              </p>
            </Sheet>
            <Sheet className="p-5">
              <p className="text-sm text-ink-2">Saldo a favor para el mes siguiente</p>
              <p className="mt-1 text-lg" data-testid="vat-credit-balance">
                <Pyg value={v.result.credit_balance} strong />
              </p>
            </Sheet>
          </section>

          <div className="grid grid-cols-2 items-start gap-6">
            <SideTable
              title="Débito fiscal"
              caption={`Débito fiscal de ${monthTitle(month)}`}
              main={v.debit.sales}
              mainLabel="Ventas"
              notes={v.debit.credit_notes}
              notesLabel="Notas de crédito de ventas (restan)"
              total={v.debit.total}
            />
            <SideTable
              title="Crédito fiscal"
              caption={`Crédito fiscal de ${monthTitle(month)}`}
              main={v.credit.purchases}
              mainLabel="Compras que imputan IVA"
              notes={v.credit.credit_notes}
              notesLabel="Notas de crédito de compras (restan)"
              total={v.credit.total}
            />
          </div>

          <Sheet>
            <h2 className="border-b border-line px-5 py-3.5 font-semibold">Control contra el libro mayor</h2>
            <LedgerControl control={v.ledger_control} />
          </Sheet>

          <Sheet>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
              <h2 className="font-semibold">
                Borrador del Formulario 120{v.form_120.version !== null && <span className="font-normal text-ink-2"> · versión {v.form_120.version}</span>}
              </h2>
              {v.form_120.rule && <UnverifiedMark status={v.form_120.rule.validation_status} />}
            </div>
            <Form120 form={v.form_120} />
          </Sheet>

          <p className="text-sm text-ink-2">
            Los importes salen de los comprobantes del mes en{' '}
            <Link to={`/impuestos/comprobantes?mes=${month}`} className="font-medium text-ledger hover:underline">
              Comprobantes
            </Link>
            ; las cuentas del control, de la{' '}
            <Link to="/impuestos/configuracion" className="font-medium text-ledger hover:underline">
              configuración
            </Link>
            .
          </p>
        </div>
      )}
    </>
  )
}
