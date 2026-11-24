/**
 * Carga en serie de comprobantes (`/impuestos/comprobantes/cargar`) y ficha de uno
 * (`/impuestos/comprobantes/:id`): ver, corregir, anular y proponer el asiento.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, BookPlus, Ban, Pencil } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Modal, Notice, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { formatMoney } from '../../lib/money'
import { ApiError, get, patch, post } from '../../services/api'
import { useContexts } from '../finance/data'
import { formatBookDate, todayIso } from '../finance/labels'
import { RulesApplied, UnverifiedMark } from './components'
import { taxKeys, useConfirmedRegister, useInvalidateTax, useRulesById, useTaxPerms, useTaxProfile } from './data'
import { CONDITION_LABELS, DIRECTION_LABELS, DOC_TYPE_LABELS, monthTitle, VOUCHER_TYPE_LABELS } from './labels'
import { canProposeVoucher, hasLiveEntry } from './logic'
import type { Direction, Voucher, VoucherIn } from './types'
import { ProposeVoucherEntryForm, VoidVoucherForm, VoucherEntryBadge } from './VoucherDialogs'
import { useRatesAt, VoucherForm } from './VoucherForm'
import { type DraftErrors, draftFromVoucher, draftToBody, emptyDraft, fieldOfApiError, nextNumber, type VoucherDraft } from './voucherForm'

const MEMORY_KEY = 'contador.tax.voucher-entry'

function remembered(): { direction?: Direction; issued_on?: string } {
  try {
    return JSON.parse(sessionStorage.getItem(MEMORY_KEY) ?? '{}') as { direction?: Direction; issued_on?: string }
  } catch {
    return {}
  }
}

function remember(direction: Direction, issuedOn: string) {
  try {
    sessionStorage.setItem(MEMORY_KEY, JSON.stringify({ direction, issued_on: issuedOn }))
  } catch {
    // Sin almacenamiento de sesión: se recuerda solo mientras la página siga abierta.
  }
}

/** Errores de la API ubicados en su campo. */
function apiFieldErrors(error: unknown): DraftErrors {
  if (!(error instanceof ApiError)) return {}
  const field = fieldOfApiError(error.code, error.details)
  if (field) return { [field]: error.message }
  return {}
}

/** Solo lo que cambió: con asiento vivo la API acepta solo las notas (D-091). */
function changedFields(next: VoucherIn, before: VoucherIn): Partial<VoucherIn> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(next)) {
    if (k === 'direction') continue
    if (JSON.stringify(v) !== JSON.stringify((before as unknown as Record<string, unknown>)[k])) out[k] = v
  }
  return out as Partial<VoucherIn>
}

function SessionList({ items }: { items: Voucher[] }) {
  if (items.length === 0) return null
  const total = items.reduce((acc, v) => acc + (v.voucher_type === 'credit_note' ? -BigInt(v.total) : BigInt(v.total)), 0n)
  return (
    <Sheet>
      <h2 className="border-b border-line px-4 py-3 font-semibold">{`Cargados en esta tanda (${items.length})`}</h2>
      <ol className="divide-y divide-line text-sm" aria-label="Comprobantes cargados en esta tanda">
        {items.map((v) => (
          <li key={v.id} className="flex items-baseline gap-3 px-4 py-2">
            <span className="w-16 shrink-0 text-ink-2">{DIRECTION_LABELS[v.direction]}</span>
            <Link to={`/impuestos/comprobantes/${v.id}`} className="min-w-0 flex-1 truncate hover:text-ledger hover:underline">
              <span className="tabular-nums">{v.number}</span> · {v.counterparty_name}
            </Link>
            <span className="tabular-nums">{formatMoney(v.voucher_type === 'credit_note' ? `-${v.total}` : v.total, 'PYG')}</span>
          </li>
        ))}
      </ol>
      <p className="flex justify-between border-t border-line px-4 py-2 text-sm">
        <span className="text-ink-2">Suma (las notas de crédito restan)</span>
        <span className="font-semibold tabular-nums">{formatMoney(total.toString(), 'PYG')}</span>
      </p>
    </Sheet>
  )
}

function NewVoucher() {
  const perms = useTaxPerms()
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateTax()
  const profile = useTaxProfile()
  const [params] = useSearchParams()
  const memory = remembered()
  const month = params.get('mes')
  const direction = (params.get('dir') as Direction | null) ?? memory.direction ?? 'purchase'
  const initialDate = month && /^\d{4}-\d{2}$/.test(month) ? (todayIso().startsWith(month) ? todayIso() : `${month}-01`) : (memory.issued_on ?? todayIso())
  const imputesIre = profile.data?.current?.ire_regime === 'ire_simple'
  const [draft, setDraft] = useState<VoucherDraft>(() => emptyDraft(direction, initialDate, imputesIre))
  const [loaded, setLoaded] = useState<Voucher[]>([])
  const first = useRef<HTMLInputElement>(null)
  const { rates } = useRatesAt(draft.issued_on || '9999-12-31')
  const confirmed = useConfirmedRegister(draft.issued_on)

  const create = useMutation({
    mutationFn: (body: VoucherIn) => post<Voucher>('/tax/vouchers', body),
    onSuccess: (v) => {
      qc.setQueryData([...taxKeys.vouchers(), 'one', v.id], v)
      invalidate()
      setLoaded((prev) => [v, ...prev])
      remember(v.direction, v.issued_on)
      toast('ok', `${VOUCHER_TYPE_LABELS[v.voucher_type]} ${v.number} cargada: ${formatMoney(v.total, 'PYG')}.`)
      const next = emptyDraft(v.direction, v.issued_on, draft.imputes_ire)
      // En ventas el talonario es propio: queda listo el número siguiente.
      if (v.direction === 'sale' && !v.is_electronic) {
        next.timbrado = v.timbrado
        next.number = nextNumber(v.number)
      }
      setDraft(next)
      requestAnimationFrame(() => first.current?.focus())
    },
  })

  if (!perms.canManage) {
    return (
      <EmptyState title="No podés cargar comprobantes" action={<Link to="/impuestos/comprobantes" className="font-medium text-ledger hover:underline">Ver los comprobantes</Link>}>
        {perms.manageReason}
      </EmptyState>
    )
  }

  return (
    <>
      <PageHeader
        title="Cargar comprobantes"
        description="Facturas de compra y de venta, una tras otra con el teclado. Los importes van con IVA incluido, como en la factura; el IVA se calcula solo."
        actions={
          <Link to={`/impuestos/comprobantes${draft.issued_on ? `?mes=${draft.issued_on.slice(0, 7)}` : ''}`} className="inline-flex h-9 items-center gap-1.5 rounded-sm px-3 font-medium text-ledger hover:bg-ledger-soft">
            <ArrowLeft size={15} aria-hidden />
            Ver los del mes
          </Link>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)_20rem] items-start gap-6">
        <Sheet>
          <div className="p-5">
            <VoucherForm
              draft={draft}
              setDraft={(d) => {
                if (create.error) create.reset()
                setDraft(d)
              }}
              mode="new"
              organizationRuc={{ ruc: profile.data?.ruc ?? null, dv: profile.data?.ruc_check_digit ?? null }}
              confirmedMonth={confirmed}
              busy={create.isPending}
              apiError={create.error}
              fieldErrors={apiFieldErrors(create.error)}
              onSubmit={(d) => {
                const { body } = draftToBody(d, rates)
                if (body) create.mutate(body)
              }}
              submitLabel="Guardar y seguir"
              firstFieldRef={first}
            />
          </div>
        </Sheet>
        <aside className="sticky top-4 flex flex-col gap-4">
          <SessionList items={loaded} />
          <Notice tone="neutral" title="Atajos">
            <ul className="list-disc pl-4 text-sm">
              <li>Tab avanza; Enter guarda y vuelve al RUC.</li>
              <li>En el RUC, ↓ y Enter eligen una contraparte de finanzas.</li>
              <li>El número acepta «1-1-145» y lo completa a 001-001-0000145.</li>
              <li>Con 44 dígitos de CDC se completan el número, la fecha y el RUC.</li>
            </ul>
          </Notice>
        </aside>
      </div>
    </>
  )
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function VoucherDetail({ id }: { id: string }) {
  const perms = useTaxPerms()
  const toast = useToast()
  const qc = useQueryClient()
  const invalidate = useInvalidateTax()
  const navigate = useNavigate()
  const profile = useTaxProfile()
  const rulesById = useRulesById()
  const contexts = useContexts()
  const business = contexts.data?.find((c) => c.kind === 'business')
  const query = useQuery({ queryKey: [...taxKeys.vouchers(), 'one', id], queryFn: () => get<Voucher>(`/tax/vouchers/${id}`) })
  const v = query.data
  const related = useQuery({
    enabled: Boolean(v?.related_voucher_id),
    queryKey: [...taxKeys.vouchers(), 'one', v?.related_voucher_id ?? ''],
    queryFn: () => get<Voucher>(`/tax/vouchers/${v?.related_voucher_id}`),
  })
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<VoucherDraft | null>(null)
  const [dialog, setDialog] = useState<'void' | 'propose' | null>(null)
  const { rates } = useRatesAt(draft?.issued_on || v?.issued_on || '9999-12-31')
  const confirmed = useConfirmedRegister(v?.issued_on ?? '')
  const original = useMemo(() => (v ? draftToBody(draftFromVoucher(v, rates), rates).body : null), [v, rates])

  const save = useMutation({
    mutationFn: (body: Partial<VoucherIn>) => patch<Voucher>(`/tax/vouchers/${id}`, body),
    onSuccess: (saved) => {
      qc.setQueryData([...taxKeys.vouchers(), 'one', id], saved)
      invalidate()
      setEditing(false)
      toast('ok', 'Comprobante actualizado.')
    },
  })

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true" aria-label="Cargando el comprobante">
        <Skeleton className="h-8 w-80" />
        <Skeleton className="h-64" />
      </div>
    )
  }
  if (query.isError || !v) {
    return (
      <EmptyState title="No se encontró el comprobante" action={<Link to="/impuestos/comprobantes" className="font-medium text-ledger hover:underline">Volver a los comprobantes</Link>}>
        {query.error instanceof ApiError ? query.error.message : 'Puede que la dirección esté mal.'}
      </EmptyState>
    )
  }

  const locked = v.period_confirmed || Boolean(confirmed)
  const voided = Boolean(v.voided_at)
  const negative = v.voucher_type === 'credit_note'
  const canEdit = perms.canManage && !voided && !locked
  const canVoid = perms.canManage && !voided && !locked && !hasLiveEntry(v)
  const canPropose = perms.canProposeEntry && canProposeVoucher(v)
  const month = v.issued_on.slice(0, 7)

  return (
    <>
      <PageHeader
        title={`${VOUCHER_TYPE_LABELS[v.voucher_type]} ${v.number}`}
        description={`${DIRECTION_LABELS[v.direction]} del ${formatBookDate(v.issued_on)} · ${v.counterparty_name}`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to={`/impuestos/comprobantes?mes=${month}`} className="inline-flex h-9 items-center gap-1.5 rounded-sm px-3 font-medium text-ledger hover:bg-ledger-soft">
              <ArrowLeft size={15} aria-hidden />
              {monthTitle(month)}
            </Link>
            {canPropose && (
              <Button variant="secondary" onClick={() => setDialog('propose')}>
                <BookPlus size={15} aria-hidden />
                Proponer asiento
              </Button>
            )}
            {canEdit && !editing && (
              <Button
                variant="secondary"
                onClick={() => {
                  setDraft(draftFromVoucher(v, rates))
                  save.reset()
                  setEditing(true)
                }}
              >
                <Pencil size={15} aria-hidden />
                {hasLiveEntry(v) ? 'Editar notas' : 'Corregir'}
              </Button>
            )}
            {canVoid && (
              <Button variant="danger" onClick={() => setDialog('void')}>
                <Ban size={15} aria-hidden />
                Anular
              </Button>
            )}
          </div>
        }
      />

      <div className="mb-4 flex flex-col gap-3">
        {voided && (
          <Notice tone="bad" title={`Anulado el ${formatBookDate(v.voided_at!.slice(0, 10))}`}>
            Motivo: {v.void_reason}. No cuenta en el IVA, el libro ni el archivo de Marangatu.
          </Notice>
        )}
        {locked && !voided && (
          <Notice tone="warn" title="Mes confirmado en Marangatu: solo lectura">
            El registro de comprobantes de {monthTitle(month).toLowerCase()} está confirmado.{' '}
            {confirmed ? (
              <Link to={`/impuestos/calendario?mes=${confirmed.dueMonth}#ob-${confirmed.obligationId}`} className="font-medium underline">
                Reabrir el registro
              </Link>
            ) : (
              <Link to={`/impuestos/calendario?codigo=REG-COMPROB-MENSUAL`} className="font-medium underline">
                Reabrir el registro
              </Link>
            )}{' '}
            para corregirlo (con motivo, como una rectificativa).
          </Notice>
        )}
        {v.counterparty_review_required && (
          <Notice tone="warn" title="RUC sin verificar">
            Es un RUC antiguo con letra, sin dígito verificador: confirmalo contra la constancia del contribuyente (D-099).
          </Notice>
        )}
        {!perms.canProposeEntry && perms.canManage && canProposeVoucher(v) && (
          <p className="text-sm text-ink-3">Proponer el asiento requiere además el permiso de cargar asientos en Contabilidad.</p>
        )}
      </div>

      {editing && draft ? (
        <Sheet>
              <h2 className="border-b border-line px-4 py-3 font-semibold">Corregir el comprobante</h2>
          <div className="p-5">
            <VoucherForm
              draft={draft}
              setDraft={(d) => {
                if (save.error) save.reset()
                setDraft(d)
              }}
              mode="edit"
              editing={v}
              notesOnly={hasLiveEntry(v)}
              organizationRuc={{ ruc: profile.data?.ruc ?? null, dv: profile.data?.ruc_check_digit ?? null }}
              confirmedMonth={null}
              busy={save.isPending}
              apiError={save.error}
              fieldErrors={apiFieldErrors(save.error)}
              onSubmit={(d) => {
                if (hasLiveEntry(v)) {
                  save.mutate({ notes: d.notes.trim() || null })
                  return
                }
                const { body } = draftToBody(d, rates)
                if (!body || !original) return
                const changes = changedFields(body, original)
                if (Object.keys(changes).length === 0) {
                  setEditing(false)
                  return
                }
                save.mutate(changes)
              }}
              onCancel={() => setEditing(false)}
              submitLabel="Guardar cambios"
            />
          </div>
        </Sheet>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)_20rem] items-start gap-6">
          <Sheet>
            <dl className="grid grid-cols-3 gap-x-6 gap-y-4 p-5">
              <Detail label="Contraparte">
                <span className="font-medium">{v.counterparty_name}</span>
                <span className="block text-sm text-ink-2 tabular-nums">
                  {v.counterparty_doc_type === 'ruc'
                    ? `RUC ${v.counterparty_ruc}${v.counterparty_ruc_dv ? `-${v.counterparty_ruc_dv}` : ''}`
                    : `${DOC_TYPE_LABELS[v.counterparty_doc_type]}${v.counterparty_document ? ` ${v.counterparty_document}` : ''}`}
                </span>
              </Detail>
              <Detail label="Timbrado y número">
                <span className="tabular-nums">
                  {v.timbrado} · {v.number}
                </span>
              </Detail>
              <Detail label="Condición">{CONDITION_LABELS[v.condition]}</Detail>
              {v.is_electronic && (
                <div className="col-span-3">
                  <Detail label="CDC">
                    <span className="tracking-wide tabular-nums">{v.cdc?.replace(/(\d{4})(?=\d)/g, '$1 ')}</span>
                  </Detail>
                </div>
              )}
              {v.currency !== 'PYG' && (
                <Detail label="Moneda">
                  {v.foreign_total} {v.currency} a {v.fx_rate} ₲
                </Detail>
              )}
              <Detail label="Imputa a">{[v.imputes_vat && 'IVA', v.imputes_ire && 'IRE', v.imputes_irp && 'IRP'].filter(Boolean).join(', ') || 'Ningún impuesto'}</Detail>
              {v.related_voucher_id && (
                <Detail label="Corrige a">
                  <Link to={`/impuestos/comprobantes/${v.related_voucher_id}`} className="text-ledger hover:underline">
                    {related.data ? `Factura ${related.data.number} del ${formatBookDate(related.data.issued_on)}` : 'La factura original'}
                  </Link>
                </Detail>
              )}
              {v.transaction_id && (
                <Detail label="Movimiento de finanzas">
                  {business ? (
                    <Link to={`/finanzas/${business.id}/movimientos?tx=${v.transaction_id}`} className="text-ledger hover:underline">
                      Ver el movimiento
                    </Link>
                  ) : (
                    'Vinculado'
                  )}
                </Detail>
              )}
              {v.notes && (
                <div className="col-span-3">
                  <Detail label="Notas">{v.notes}</Detail>
                </div>
              )}
            </dl>

            <table className="w-full border-t border-line text-sm">
              <caption className="sr-only">Importes del comprobante</caption>
              <thead>
                <tr className="text-left text-ink-2">
                  <th scope="col" className="px-5 py-2 font-medium">
                    Tasa
                  </th>
                  <th scope="col" className="px-5 py-2 text-right font-medium">
                    Importe con IVA
                  </th>
                  <th scope="col" className="px-5 py-2 text-right font-medium">
                    Base
                  </th>
                  <th scope="col" className="px-5 py-2 text-right font-medium">
                    IVA
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line border-y border-line tabular-nums">
                {(
                  [
                    ['Gravado 10 %', v.taxed_10, v.vat_10],
                    ['Gravado 5 %', v.taxed_5, v.vat_5],
                    ['Exento', v.exempt, '0'],
                  ] as const
                ).map(([label, amount, vat]) => (
                  <tr key={label}>
                    <th scope="row" className="px-5 py-2 text-left font-normal">
                      {label}
                    </th>
                    <td className="px-5 py-2 text-right">{formatMoney(amount, 'PYG')}</td>
                    <td className="px-5 py-2 text-right">{formatMoney((BigInt(amount) - BigInt(vat)).toString(), 'PYG')}</td>
                    <td className="px-5 py-2 text-right">{formatMoney(vat, 'PYG')}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row" className="px-5 py-3 text-left font-semibold">
                    Total{negative ? ' (resta)' : ''}
                  </th>
                  <td className="px-5 py-3 text-right font-semibold tabular-nums">
                    <span className="ledger-rule">{formatMoney(negative ? `-${v.total}` : v.total, 'PYG')}</span>
                  </td>
                  <td />
                  <td className="px-5 py-3 text-right font-medium tabular-nums">{formatMoney((BigInt(v.vat_10) + BigInt(v.vat_5)).toString(), 'PYG')}</td>
                </tr>
              </tfoot>
            </table>
          </Sheet>

          <aside className="flex flex-col gap-4">
            <Sheet>
              <h2 className="border-b border-line px-4 py-3 font-semibold">Estado</h2>
              <div className="flex flex-col gap-3 p-4 text-sm">
                <p className="flex flex-wrap gap-1.5">
                  {voided ? <Badge tone="bad">Anulado</Badge> : <Badge tone="ok">Vigente</Badge>}
                  {locked && <Badge tone="neutral">Mes confirmado</Badge>}
                  {v.is_electronic && <Badge tone="neutral">Electrónico</Badge>}
                  <VoucherEntryBadge voucher={v} />
                </p>
                {!v.journal_entry_id && !voided && <p className="text-ink-2">Sin asiento todavía.</p>}
                <div className="flex flex-col gap-1">
                  <span className="text-ink-2">Regla de las tasas</span>
                  <span className="flex items-center gap-2">
                    <RulesApplied rules={v.rules_applied} byId={rulesById} />
                    <UnverifiedMark status={v.rule_status} />
                  </span>
                </div>
                <p className="text-ink-3">Cargado el {formatBookDate(v.created_at.slice(0, 10))}.</p>
              </div>
            </Sheet>
            {perms.canManage && !locked && (
              <Link to={`/impuestos/comprobantes/cargar?mes=${month}&dir=${v.direction}`} className="text-sm font-medium text-ledger hover:underline">
                Cargar otro comprobante de {monthTitle(month).toLowerCase()}
              </Link>
            )}
          </aside>
        </div>
      )}

      <Modal open={dialog === 'propose'} size="lg" title="Proponer el asiento" onClose={() => setDialog(null)}>
        {dialog === 'propose' && <ProposeVoucherEntryForm voucher={v} onDone={() => setDialog(null)} />}
      </Modal>
      <Modal open={dialog === 'void'} title="Anular el comprobante" onClose={() => setDialog(null)}>
        {dialog === 'void' && (
          <VoidVoucherForm
            voucher={v}
            onDone={(changed) => {
              setDialog(null)
              if (changed) {
                toast('ok', `Comprobante ${v.number} anulado.`)
                qc.invalidateQueries({ queryKey: [...taxKeys.vouchers(), 'one', id] })
                navigate(`/impuestos/comprobantes/${id}`, { replace: true })
              }
            }}
          />
        )}
      </Modal>
    </>
  )
}

export function VoucherEntryPage() {
  const { id } = useParams()
  return id ? <VoucherDetail key={id} id={id} /> : <NewVoucher />
}
