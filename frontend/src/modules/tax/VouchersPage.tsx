/**
 * Registro de comprobantes del mes (D-088): filtros en la URL, totales por dirección, y desde
 * acá se anula, se propone el asiento y se descargan el Excel y el archivo para Marangatu.
 */
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Plus, Search } from 'lucide-react'
import { type ReactNode, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { Pyg } from '../accounting/components'
import { ApiErrorNotice, TableSkeleton, Th } from '../finance/components'
import { fetchAll } from '../finance/data'
import { formatBookDate, todayIso } from '../finance/labels'
import { taxKeys, useConfirmedRegister, useTaxAlerts, useTaxPerms, useTaxProfile } from './data'
import { DIRECTION_PLURAL, monthTitle, VOUCHER_TYPE_LABELS } from './labels'
import { canProposeVoucher, hasLiveEntry, shiftMonth, type Totals, voucherTotals } from './logic'
import type { Direction, Voucher } from './types'
import { MarangatuButton, ProposeVoucherEntryForm, VoidVoucherForm, VoucherEntryBadge, XlsxButton } from './VoucherDialogs'

const signed = (v: Voucher, amount: string) => (v.voucher_type === 'credit_note' && amount !== '0' ? `-${amount}` : amount)

function TotalsRow({ label, t }: { label: string; t: Totals }) {
  return (
    <tr className="border-t border-line-strong bg-sunken/60">
      <th scope="row" colSpan={4} className="px-4 py-2.5 text-left font-semibold">
        {label} <span className="font-normal text-ink-2">({t.count})</span>
      </th>
      <td className="px-4 py-2.5 text-right">
        <Pyg value={t.taxed10.toString()} strong />
      </td>
      <td className="px-4 py-2.5 text-right">
        <Pyg value={t.taxed5.toString()} strong />
      </td>
      <td className="px-4 py-2.5 text-right">
        <Pyg value={t.exempt.toString()} strong />
      </td>
      <td className="px-4 py-2.5 text-right">
        <Pyg value={t.vat.toString()} strong />
      </td>
      <td className="px-4 py-2.5 text-right">
        <span className="ledger-rule">
          <Pyg value={t.total.toString()} strong />
        </span>
      </td>
      <td colSpan={2} />
    </tr>
  )
}

export function VouchersPage() {
  const perms = useTaxPerms()
  const toast = useToast()
  const alerts = useTaxAlerts()
  const profile = useTaxProfile()
  const [params, setParams] = useSearchParams()
  const today = alerts.data?.as_of ?? todayIso()
  const month = /^\d{4}-\d{2}$/.test(params.get('mes') ?? '') ? (params.get('mes') as string) : today.slice(0, 7)
  const direction = (params.get('dir') as Direction | null) || null
  const ruc = params.get('ruc') ?? ''
  const q = params.get('q') ?? ''
  const voided = params.get('anulados') === 'solo' ? 'only' : params.get('anulados') === 'si' ? 'include' : 'exclude'
  const [text, setText] = useState(q)
  const [rucText, setRucText] = useState(ruc)
  const [dialog, setDialog] = useState<{ kind: 'void' | 'propose'; v: Voucher } | null>(null)
  const confirmed = useConfirmedRegister(`${month}-01`)

  const setParam = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    setParams(next, { replace: true })
  }

  // La búsqueda de texto y el RUC se aplican al dejar de escribir.
  useEffect(() => {
    const id = setTimeout(() => {
      if (text !== q || rucText !== ruc) setParam({ q: text.trim() || null, ruc: rucText.trim() || null })
    }, 300)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar lo escrito
  }, [text, rucText])

  const filters: Record<string, string> = { month: `${month}-01`, voided }
  if (direction) filters.direction = direction
  if (ruc) filters.counterparty_ruc = ruc
  if (q) filters.q = q
  const list = useQuery({ queryKey: [...taxKeys.vouchers(), 'list', filters], queryFn: () => fetchAll<Voucher>('/tax/vouchers', filters) })
  const rows = [...(list.data ?? [])].sort((a, b) => (a.issued_on === b.issued_on ? a.number.localeCompare(b.number) : a.issued_on < b.issued_on ? -1 : 1))
  const totals = voucherTotals(rows)
  const filtered = Boolean(direction || ruc || q || voided !== 'exclude')
  const [year, monthNumber] = month.split('-').map(Number)

  const close = (changed: boolean, message: string) => {
    if (changed) toast('ok', message)
    setDialog(null)
  }

  const action = (v: Voucher): ReactNode => {
    const buttons: ReactNode[] = []
    if (perms.canProposeEntry && canProposeVoucher(v)) {
      buttons.push(
        <Button key="p" variant="ghost" className="h-7 px-2 text-sm" onClick={() => setDialog({ kind: 'propose', v })} aria-label={`Proponer asiento del comprobante ${v.number}`}>
          Proponer asiento
        </Button>,
      )
    }
    if (perms.canManage && !v.voided_at && !v.period_confirmed && !hasLiveEntry(v)) {
      buttons.push(
        <Button key="v" variant="ghost" className="h-7 px-2 text-sm text-debit" onClick={() => setDialog({ kind: 'void', v })} aria-label={`Anular el comprobante ${v.number}`}>
          Anular
        </Button>,
      )
    }
    return buttons
  }

  return (
    <>
      <PageHeader
        title="Comprobantes"
        description="Registro de compras y ventas del mes. Es la base del IVA y del archivo para Marangatu; los electrónicos se cargan igual para tu control."
        actions={
          perms.canManage &&
          !confirmed && (
            <Link
              to={`/impuestos/comprobantes/cargar?mes=${month}${direction ? `&dir=${direction}` : ''}`}
              className="inline-flex h-9 items-center gap-1.5 rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong"
            >
              <Plus size={16} aria-hidden />
              Cargar comprobantes
            </Link>
          )
        }
      />

      <form
        role="search"
        aria-label="Filtros de comprobantes"
        onSubmit={(e) => e.preventDefault()}
        className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-md border border-line bg-surface p-3.5"
      >
        <div className="flex items-end gap-1">
          <Button type="button" variant="ghost" className="px-2" aria-label="Mes anterior" onClick={() => setParam({ mes: shiftMonth(month, -1) })}>
            <ChevronLeft size={16} />
          </Button>
          <Field label="Mes">
            {(p) => <Input {...p} type="month" className="w-44" value={month} onChange={(e) => e.target.value && setParam({ mes: e.target.value })} />}
          </Field>
          <Button type="button" variant="ghost" className="px-2" aria-label="Mes siguiente" onClick={() => setParam({ mes: shiftMonth(month, 1) })}>
            <ChevronRight size={16} />
          </Button>
        </div>
        <Field label="Dirección">
          {(p) => (
            <Select {...p} className="w-36" value={direction ?? ''} onChange={(e) => setParam({ dir: e.target.value || null })}>
              <option value="">Compras y ventas</option>
              <option value="purchase">{DIRECTION_PLURAL.purchase}</option>
              <option value="sale">{DIRECTION_PLURAL.sale}</option>
            </Select>
          )}
        </Field>
        <Field label="RUC de la contraparte">
          {(p) => <Input {...p} className="w-36 tabular-nums" inputMode="numeric" maxLength={9} placeholder="Sin el DV" value={rucText} onChange={(e) => setRucText(e.target.value.toUpperCase())} />}
        </Field>
        <Field label="Buscar">
          {(p) => (
            <div className="relative">
              <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-3" />
              <Input {...p} type="search" className="w-56 pl-8" placeholder="Nombre, número o timbrado" value={text} onChange={(e) => setText(e.target.value)} />
            </div>
          )}
        </Field>
        <Field label="Anulados">
          {(p) => (
            <Select {...p} className="w-36" value={params.get('anulados') ?? ''} onChange={(e) => setParam({ anulados: e.target.value || null })}>
              <option value="">Sin anulados</option>
              <option value="si">Con anulados</option>
              <option value="solo">Solo anulados</option>
            </Select>
          )}
        </Field>
        <div className="ml-auto flex flex-wrap gap-2">
          <XlsxButton year={year} month={monthNumber} direction={direction} />
          <MarangatuButton year={year} month={monthNumber} ruc={profile.data?.ruc ?? null} />
        </div>
      </form>

      {confirmed && (
        <div className="mb-4">
          <Notice tone="warn" title={`El registro de ${monthTitle(month).toLowerCase()} está confirmado: solo lectura`}>
            No se cargan, cambian ni anulan comprobantes del mes.{' '}
            {perms.canManage && (
              <>
                <Link to={`/impuestos/calendario?mes=${confirmed.dueMonth}#ob-${confirmed.obligationId}`} className="font-medium underline">
                  Reabrir el registro
                </Link>{' '}
                desde el calendario, con motivo, para corregirlo.
              </>
            )}
          </Notice>
        </div>
      )}

      <Sheet className="overflow-hidden">
        <div className="flex items-baseline justify-between border-b border-line px-4 py-3">
          <h2 className="font-semibold">{monthTitle(month)}</h2>
          {list.data && (
            <p className="text-sm text-ink-2">
              {rows.length} {rows.length === 1 ? 'comprobante' : 'comprobantes'}
              {voided === 'include' ? ' (los anulados no suman)' : ''}
            </p>
          )}
        </div>
        {list.isPending ? (
          <TableSkeleton rows={6} cols={6} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudieron cargar los comprobantes." />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            title={filtered ? 'Ningún comprobante coincide' : `Sin comprobantes en ${monthTitle(month).toLowerCase()}`}
            action={
              filtered ? (
                <Button variant="secondary" onClick={() => { setText(''); setRucText(''); setParams(new URLSearchParams({ mes: month }), { replace: true }) }}>
                  Quitar filtros
                </Button>
              ) : perms.canManage && !confirmed ? (
                <Link to={`/impuestos/comprobantes/cargar?mes=${month}`} className="font-medium text-ledger hover:underline">
                  Cargar el primero
                </Link>
              ) : undefined
            }
          >
            {filtered ? 'Probá con otro mes o sacá algún filtro.' : 'Cargá las facturas de compra y de venta del mes: con ellas se estima el IVA y se arma el archivo para Marangatu.'}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Comprobantes de {monthTitle(month)}</caption>
              <thead className="border-b border-line text-ink-2">
                <tr>
                  <Th>Fecha</Th>
                  <Th>Comprobante</Th>
                  <Th>Contraparte</Th>
                  <Th>Estado</Th>
                  <Th align="right">Gravado 10 %</Th>
                  <Th align="right">Gravado 5 %</Th>
                  <Th align="right">Exento</Th>
                  <Th align="right">IVA</Th>
                  <Th align="right">Total</Th>
                  <Th>
                    <span className="sr-only">Acciones</span>
                  </Th>
                </tr>
              </thead>
              {(['purchase', 'sale'] as const)
                .filter((dir) => rows.some((v) => v.direction === dir))
                .map((dir) => (
                  <tbody key={dir} className="divide-y divide-line">
                    <tr className="bg-sunken">
                      <th scope="rowgroup" colSpan={10} className="px-4 py-1.5 text-left text-sm font-semibold">
                        {DIRECTION_PLURAL[dir]}
                      </th>
                    </tr>
                    {rows
                      .filter((v) => v.direction === dir)
                      .map((v) => (
                        <tr key={v.id} className={cx('align-top hover:bg-sunken/50', v.voided_at && 'text-ink-3 line-through decoration-ink-3/60')}>
                          <td className="px-4 py-2 whitespace-nowrap tabular-nums">{formatBookDate(v.issued_on)}</td>
                          <td className="px-4 py-2">
                            <Link to={`/impuestos/comprobantes/${v.id}`} className="font-medium whitespace-nowrap tabular-nums hover:text-ledger hover:underline">
                              {v.number}
                            </Link>
                            <span className="block text-xs text-ink-2 no-underline">
                              {VOUCHER_TYPE_LABELS[v.voucher_type]}
                              {v.is_electronic ? ' electrónica' : ''} · timbrado {v.timbrado}
                            </span>
                          </td>
                          <td className="max-w-56 px-4 py-2">
                            <span className="block truncate">{v.counterparty_name}</span>
                            {v.counterparty_ruc && (
                              <span className="block text-xs text-ink-2 tabular-nums">
                                {v.counterparty_ruc}
                                {v.counterparty_ruc_dv ? `-${v.counterparty_ruc_dv}` : ''}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2">
                            <span className="flex flex-wrap gap-1 no-underline">
                              {v.voided_at && <Badge tone="bad">Anulado</Badge>}
                              {v.counterparty_review_required && <Badge tone="warn">RUC a revisar</Badge>}
                              {!v.imputes_vat && <Badge tone="neutral">No imputa IVA</Badge>}
                              <VoucherEntryBadge voucher={v} />
                            </span>
                          </td>
                          <td className="px-4 py-2 text-right">
                            <Pyg value={signed(v, v.taxed_10)} />
                          </td>
                          <td className="px-4 py-2 text-right">
                            <Pyg value={signed(v, v.taxed_5)} />
                          </td>
                          <td className="px-4 py-2 text-right">
                            <Pyg value={signed(v, v.exempt)} />
                          </td>
                          <td className="px-4 py-2 text-right">
                            <Pyg value={signed(v, (BigInt(v.vat_10) + BigInt(v.vat_5)).toString())} />
                          </td>
                          <td className="px-4 py-2 text-right font-medium">
                            <Pyg value={signed(v, v.total)} />
                          </td>
                          <td className="px-2 py-1 text-right whitespace-nowrap">{action(v)}</td>
                        </tr>
                      ))}
                    <TotalsRow label={`Total ${DIRECTION_PLURAL[dir].toLowerCase()}`} t={totals[dir]} />
                  </tbody>
                ))}
            </table>
          </div>
        )}
      </Sheet>
      {!perms.canManage && <p className="mt-3 text-sm text-ink-3">{perms.manageReason}</p>}

      <Modal open={dialog?.kind === 'propose'} size="lg" title="Proponer el asiento" onClose={() => setDialog(null)}>
        {dialog?.kind === 'propose' && <ProposeVoucherEntryForm voucher={dialog.v} onDone={() => setDialog(null)} />}
      </Modal>
      <Modal open={dialog?.kind === 'void'} title="Anular el comprobante" onClose={() => setDialog(null)}>
        {dialog?.kind === 'void' && <VoidVoucherForm voucher={dialog.v} onDone={(changed) => close(changed, `Comprobante ${dialog.v.number} anulado.`)} />}
      </Modal>
    </>
  )
}
