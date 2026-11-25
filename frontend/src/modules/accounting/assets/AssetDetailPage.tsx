/**
 * Detalle de un bien: parámetros, valor neto, el plan de cuotas (contabilizadas, en borrador y
 * pendientes) con el asiento de cada una, y la baja (D-059) con acta obligatoria.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, PackageMinus, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Badge, Button, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Skeleton, Textarea } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { cx } from '../../../lib/cx'
import { formatMoney } from '../../../lib/money'
import { get, post } from '../../../services/api'
import { ApiErrorNotice, Th } from '../../finance/components'
import { formatBookDate, todayIso } from '../../finance/labels'
import { pygToBig, sumPyg } from '../amounts'
import { Pyg, RuledTotal } from '../components'
import { accountingKeys, useAccountingPerms, useEntry, useInvalidateAccounting } from '../data'
import { DISPOSAL_KIND_LABELS, INSTALLMENT_STATUS_LABELS, monthName, monthsText, monthYear, percentText, START_RULE_LABELS } from '../labels'
import type { Entry } from '../types'
import type { DisposalKind, FixedAsset, Installment, InstallmentStatus } from '../types3b'
import { byYear, disposeErrors, planTotals } from './logic'

const STATUS_TONE: Record<InstallmentStatus, 'ok' | 'warn' | 'neutral'> = { posted: 'ok', draft: 'warn', pending: 'neutral' }

/** Ancho proporcional de una parte del total, solo para dibujar (no para operar importes). */
const share = (part: string, total: string) => (pygToBig(total) === 0n ? 0 : Number((pygToBig(part) * 10_000n) / pygToBig(total)) / 100)

function PlanMeter({ installments }: { installments: Installment[] }) {
  const t = planTotals(installments)
  const parts = [
    { key: 'posted', label: 'Contabilizado', ...t.posted, className: 'bg-ledger' },
    { key: 'draft', label: 'En borrador', ...t.draft, className: 'bg-amber' },
    { key: 'pending', label: 'Pendiente', ...t.pending, className: 'bg-line-strong' },
  ]
  return (
    <div>
      <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-sm bg-sunken" aria-hidden>
        {parts.map((p) => (p.count > 0 ? <div key={p.key} className={p.className} style={{ width: `${share(p.amount, t.total)}%` }} /> : null))}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-4 text-sm">
        {parts.map((p) => (
          <div key={p.key}>
            <dt className="flex items-center gap-1.5 text-ink-2">
              <span className={cx('inline-block size-2.5 rounded-xs', p.className)} aria-hidden />
              {p.label}
            </dt>
            <dd className="mt-0.5">
              <Pyg value={p.amount} strong /> <span className="text-ink-3">en {p.count} {p.count === 1 ? 'cuota' : 'cuotas'}</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function InstallmentTable({ installments }: { installments: Installment[] }) {
  return (
    <table className="w-full" aria-label="Plan de cuotas">
      <thead className="border-b border-line bg-sunken text-sm text-ink-2">
        <tr>
          <Th className="w-20">Cuota</Th>
          <Th>Mes</Th>
          <Th align="right" className="w-40">
            Importe
          </Th>
          <Th className="w-40">Estado</Th>
          <Th className="w-40">Asiento</Th>
        </tr>
      </thead>
      {byYear(installments).map(([year, rows]) => (
        <tbody key={year} className="divide-y divide-line border-b border-line">
          <tr className="bg-sunken/40">
            <th scope="rowgroup" colSpan={2} className="px-4 py-1.5 text-left text-sm font-semibold">
              {year}
            </th>
            <td className="px-4 py-1.5 text-right text-sm">
              <Pyg value={sumPyg(rows.map((r) => r.amount))} className="font-medium" />
            </td>
            <td colSpan={2} className="px-4 py-1.5 text-sm text-ink-3">
              {rows.length} {rows.length === 1 ? 'cuota' : 'cuotas'}
            </td>
          </tr>
          {rows.map((i) => (
            <tr key={i.installment} className={cx(i.status === 'pending' && 'text-ink-2')}>
              <td className="px-4 py-1.5 tabular-nums">{i.installment}</td>
              <td className="px-4 py-1.5">{monthName(i.month)}</td>
              <td className="px-4 py-1.5 text-right">
                <Pyg value={i.amount} muted={i.status === 'pending'} />
              </td>
              <td className="px-4 py-1.5">
                <Badge tone={STATUS_TONE[i.status]}>{INSTALLMENT_STATUS_LABELS[i.status]}</Badge>
              </td>
              <td className="px-4 py-1.5 text-sm">
                {i.entry_id ? (
                  <Link to={`/contabilidad/asientos/${i.entry_id}`} className="font-medium text-ledger hover:underline">
                    {i.status === 'draft' ? 'Abrir el borrador' : 'Ver el asiento'}
                  </Link>
                ) : (
                  <span className="text-ink-3">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      ))}
      <tfoot>
        <tr>
          <td colSpan={2} className="px-4 py-3 font-semibold">
            Total a depreciar
          </td>
          <td className="px-4 py-3 text-right">
            <RuledTotal value={sumPyg(installments.map((i) => i.amount))} label="Total a depreciar" />
          </td>
          <td colSpan={2} />
        </tr>
      </tfoot>
    </table>
  )
}

function DisposeForm({ asset, onDone }: { asset: FixedAsset; onDone: () => void }) {
  const navigate = useNavigate()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [date, setDate] = useState(todayIso())
  const [kind, setKind] = useState<DisposalKind>('scrap')
  const [reason, setReason] = useState('')
  const [document, setDocument] = useState('')
  const [touched, setTouched] = useState(false)
  const errors = disposeErrors({ date, reason, document })
  const run = useMutation({
    mutationFn: () => post<Entry>(`/accounting/fixed-assets/${asset.id}/dispose`, { date, kind, reason: reason.trim(), document_reference: document.trim() }),
    onSuccess: (entry) => {
      invalidate()
      toast('ok', `Borrador de baja de «${asset.name}» generado: revisalo y contabilizalo.`)
      onDone()
      navigate(`/contabilidad/asientos/${entry.id}`)
    },
  })
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        setTouched(true)
        if (!errors.date && !errors.reason && !errors.document) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Se genera un borrador que cancela el costo y la depreciación acumulada y lleva el valor neto a resultados. El bien queda de baja recién al
        contabilizarlo. Si en el mes de la baja falta la depreciación, la API la exige antes.
      </p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <div className="grid grid-cols-2 gap-4">
        <Field label="Fecha de la baja" error={touched ? errors.date : undefined}>
          {(p) => <Input {...p} type="date" min={asset.acquired_on} value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field label="Tipo de baja">
          {(p) => (
            <Select {...p} value={kind} onChange={(e) => setKind(e.target.value as DisposalKind)}>
              {(Object.keys(DISPOSAL_KIND_LABELS) as DisposalKind[]).map((k) => (
                <option key={k} value={k}>
                  {DISPOSAL_KIND_LABELS[k]}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      {kind === 'sale' && (
        <Notice tone="neutral" title="La venta se factura aparte">
          Este asiento da de baja el bien. El ingreso por la venta (y su IVA) se registra con su comprobante, como cualquier venta.
        </Notice>
      )}
      <Field label="Motivo" error={touched ? errors.reason : undefined}>
        {(p) => <Textarea {...p} rows={2} maxLength={300} placeholder="Rota sin reparación, robada con denuncia, vendida a…" value={reason} onChange={(e) => setReason(e.target.value)} />}
      </Field>
      <Field label="Acta de baja" error={touched ? errors.document : undefined} hint="N° o referencia del acta del contador o de la constancia del auditor externo (Decreto 3182, art. 58).">
        {(p) => <Input {...p} maxLength={100} placeholder="Acta 3/2026" value={document} onChange={(e) => setDocument(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" variant="danger" busy={run.isPending}>
          <PackageMinus size={15} />
          Generar el borrador de baja
        </Button>
      </div>
    </form>
  )
}

function EntryLink({ id, label }: { id: string; label: string }) {
  const entry = useEntry(id)
  return (
    <Link to={`/contabilidad/asientos/${id}`} className="font-medium text-ledger hover:underline">
      {label}
      {entry.data ? (entry.data.number !== null ? ` N° ${entry.data.number}` : ' (borrador)') : ''}
    </Link>
  )
}

export function AssetDetailPage() {
  const { id = '' } = useParams()
  const perms = useAccountingPerms()
  const [disposing, setDisposing] = useState(false)
  const asset = useQuery({ queryKey: accountingKeys.asset(id), queryFn: () => get<FixedAsset>(`/accounting/fixed-assets/${id}`) })
  const a = asset.data
  const installments = a?.installments ?? []
  const disposalDraft = a && a.disposal_entry_id && a.status !== 'disposed'
  const sameParams = a && a.useful_life_months === a.fiscal_useful_life_months && a.residual_value === a.fiscal_residual_value

  return (
    <>
      <Link to="/contabilidad/activos" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft size={15} aria-hidden />
        Volver a los bienes
      </Link>
      {asset.isPending ? (
        <Sheet className="flex flex-col gap-3 p-5">
          <Skeleton className="h-7 w-72" />
          <Skeleton className="h-24" />
          <Skeleton className="h-48" />
        </Sheet>
      ) : asset.isError || !a ? (
        <ApiErrorNotice error={asset.error} title="No se pudo cargar el bien." />
      ) : (
        <>
          <PageHeader
            title={a.name}
            description={`${a.category_name}${a.serial_or_reference ? `, ref. ${a.serial_or_reference}` : ''}. ${a.description ?? ''}`.trim()}
            actions={
              perms.canManage && (
                <>
                  <Link
                    to={`/contabilidad/activos/${a.id}/editar`}
                    className="inline-flex h-9 items-center gap-2 rounded-sm border border-line-strong bg-surface px-3.5 font-medium text-ink hover:bg-sunken"
                  >
                    <Pencil size={15} />
                    Editar
                  </Link>
                  {!a.disposal_entry_id && (
                    <Button variant="danger" onClick={() => setDisposing(true)}>
                      <PackageMinus size={15} />
                      Dar de baja
                    </Button>
                  )}
                </>
              )
            }
          />
          <div className="mb-5 flex flex-col gap-3">
            {a.status === 'disposed' && (
              <Notice tone="neutral" title={`Dado de baja el ${formatBookDate(a.disposed_on ?? '')}`}>
                {a.disposal_kind ? DISPOSAL_KIND_LABELS[a.disposal_kind] : 'Baja'}: {a.disposal_reason}. Acta: {a.disposal_document_reference}.{' '}
                {a.disposal_entry_id && <EntryLink id={a.disposal_entry_id} label="Ver el asiento de baja" />}
              </Notice>
            )}
            {disposalDraft && a.disposal_entry_id && (
              <Notice tone="warn" title="Baja en borrador">
                El bien sigue en uso hasta que se contabilice el borrador de baja del {formatBookDate(a.disposed_on ?? '')}.{' '}
                <EntryLink id={a.disposal_entry_id} label="Abrir el borrador de baja" />
              </Notice>
            )}
            {a.warnings.map((w) => (
              <Notice key={w} tone="warn" title="Revisá los parámetros">
                {w}
              </Notice>
            ))}
          </div>

          <div className="grid grid-cols-[minmax(0,1fr)_20rem] items-start gap-6">
            <div className="flex flex-col gap-6">
              <Sheet className="p-5">
                <div className="mb-4 flex items-baseline justify-between gap-4">
                  <h2 className="font-semibold">Plan de depreciación</h2>
                  <p className="text-sm text-ink-3">
                    Lineal mensual desde {monthYear(a.depreciation_start)}; la última cuota absorbe el redondeo.
                  </p>
                </div>
                {installments.length > 0 ? <PlanMeter installments={installments} /> : <p className="text-sm text-ink-3">El bien no tiene cuotas.</p>}
              </Sheet>
              {installments.length > 0 && (
                <Sheet>
                  <InstallmentTable installments={installments} />
                </Sheet>
              )}
            </div>
            <div className="flex flex-col gap-6">
              <Sheet className="p-5">
                <h2 className="font-semibold">Valor del bien</h2>
                <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-sm">
                  <dt className="text-ink-2">Costo de adquisición</dt>
                  <dd className="text-right">
                    <Pyg value={a.cost} />
                  </dd>
                  <dt className="text-ink-2">Depreciación acumulada</dt>
                  <dd className="text-right">
                    <Pyg value={a.accumulated_depreciation} />
                  </dd>
                  <dt className="border-t border-line pt-1.5 font-medium">Valor neto contable</dt>
                  <dd className="border-t border-line pt-1.5 text-right">
                    <RuledTotal value={a.net_book_value} label={`Valor neto contable ${formatMoney(a.net_book_value, 'PYG')}`} />
                  </dd>
                </dl>
                <p className="mt-2 text-sm text-ink-3">La acumulada cuenta solo las cuotas contabilizadas.</p>
              </Sheet>
              <Sheet className="p-5">
                <h2 className="font-semibold">Parámetros</h2>
                <dl className="mt-3 flex flex-col gap-2 text-sm">
                  <div>
                    <dt className="text-ink-3">Adquisición</dt>
                    <dd>{formatBookDate(a.acquired_on)}</dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Inicio</dt>
                    <dd>
                      {START_RULE_LABELS[a.start_rule]}: {monthYear(a.depreciation_start)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Fiscal</dt>
                    <dd>
                      {monthsText(a.fiscal_useful_life_months)}, residual {percentText(a.fiscal_residual_rate)} ({formatMoney(a.fiscal_residual_value, 'PYG')})
                      {a.fiscal_life_authorization && <span className="block text-sm text-ink-3">Autorizado por la DNIT: {a.fiscal_life_authorization}</span>}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-ink-3">Contable</dt>
                    <dd>
                      {sameParams ? 'Igual a la fiscal' : `${monthsText(a.useful_life_months)}, residual ${formatMoney(a.residual_value, 'PYG')}`}
                    </dd>
                  </div>
                  {!sameParams && (
                    <p className="text-ink-2">
                      Los parámetros contables difieren de los fiscales: la parte de la cuota contable que supere la fiscal no es deducible en el IRE.
                    </p>
                  )}
                  <div>
                    <dt className="text-ink-3">Asiento de compra</dt>
                    <dd>{a.acquisition_entry_id ? <EntryLink id={a.acquisition_entry_id} label="Asiento" /> : <span className="text-ink-3">Sin vincular</span>}</dd>
                  </div>
                </dl>
              </Sheet>
            </div>
          </div>
          <Modal open={disposing} title={`Dar de baja «${a.name}»`} onClose={() => setDisposing(false)}>
            <DisposeForm asset={a} onDone={() => setDisposing(false)} />
          </Modal>
        </>
      )}
    </>
  )
}
