/**
 * Acciones sobre comprobantes que abren un diálogo: proponer el asiento (D-091, D-106),
 * anular con motivo y exportar el archivo de importación de Marangatu (D-096, D-113).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BookPlus, Download, FileArchive, FileSpreadsheet, TriangleAlert } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Badge, Button, Field, Input, Modal, Notice, Select } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { saveBlob } from '../../lib/download'
import { formatMoney } from '../../lib/money'
import { ApiError, get, getBlob, post, qs } from '../../services/api'
import { AccountCombobox, LedgerAccountSelect } from '../accounting/components'
import { accountingKeys, useChart, useInvalidateAccounting } from '../accounting/data'
import type { Entry } from '../accounting/types'
import { ApiErrorNotice } from '../finance/components'
import { errorMessage } from '../finance/forms'
import { formatBookDate } from '../finance/labels'
import { DoubtNote, ReasonForm, UnverifiedMark } from './components'
import { useInvalidateTax } from './data'
import { CONDITION_LABELS, DIRECTION_LABELS, monthTitle, VOUCHER_TYPE_LABELS } from './labels'
import { marangatuName, voucherXlsxName } from './logic'
import { annualRegisterName, registerDate } from './registerDraft'
import type { Direction, ExcludedVoucher, MarangatuPreview, Voucher } from './types'

// --- Proponer asiento --------------------------------------------------------------------

function ProposeError({ error }: { error: ApiError }) {
  const d = (error.details ?? {}) as { entry_id?: string; missing?: unknown[] }
  let extra: ReactNode = null
  if ((error.code === 'VOUCHER_HAS_ENTRY' || error.code === 'VOUCHER_TRANSACTION_HAS_ENTRY') && d.entry_id) {
    extra = (
      <>
        {error.code === 'VOUCHER_TRANSACTION_HAS_ENTRY' && (
          <span className="block">Nunca dos asientos vivos para el mismo hecho (BR-TAX-10): el pago y la factura son la misma operación.</span>
        )}
        <Link to={`/contabilidad/asientos/${d.entry_id}`} className="font-medium underline">
          Ver el asiento existente
        </Link>
      </>
    )
  } else if (error.code === 'TAX_ACCOUNT_MISSING') {
    extra = (
      <Link to="/impuestos/configuracion" className="font-medium underline">
        Configurar las cuentas de impuestos
      </Link>
    )
  } else if (error.code === 'LEDGER_ACCOUNT_MISSING') {
    extra = (
      <Link to="/finanzas" className="font-medium underline">
        Asignar la cuenta contable en Finanzas → Cuentas
      </Link>
    )
  } else if (error.code === 'FISCAL_YEAR_NOT_FOUND' || error.code === 'FISCAL_YEAR_CLOSED' || error.code === 'PERIOD_CLOSED') {
    extra = (
      <Link to="/contabilidad/ejercicios" className="font-medium underline">
        Ir a Ejercicios y períodos
      </Link>
    )
  }
  return (
    <Notice tone="bad" title={error.message}>
      {extra}
    </Notice>
  )
}

export function ProposeVoucherEntryForm({ voucher, onDone }: { voucher: Voucher; onDone: () => void }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const invalidateAccounting = useInvalidateAccounting()
  const invalidateTax = useInvalidateTax()
  const chart = useChart()
  const accounts = (chart.data?.accounts ?? []).filter((a) => a.is_postable && !a.archived_at)
  const purchase = voucher.direction === 'purchase'
  const mainKinds = purchase ? ['expense', 'asset'] : ['income']
  const needsCounterpart = voucher.condition === 'cash' && !voucher.transaction_id
  const [account, setAccount] = useState('')
  const [counterpart, setCounterpart] = useState('')
  const [description, setDescription] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const propose = useMutation({
    mutationFn: () =>
      post<Entry>(`/tax/vouchers/${voucher.id}/propose-entry`, {
        account_id: account,
        ...(counterpart ? { counterpart_account_id: counterpart } : {}),
        ...(description.trim() ? { description: description.trim() } : {}),
      }),
    onSuccess: (entry) => {
      qc.setQueryData(accountingKeys.entry(entry.id), entry)
      invalidateAccounting()
      invalidateTax()
      toast('ok', 'Borrador de asiento creado desde el comprobante. Revisalo y contabilizalo cuando esté bien.')
      onDone()
      navigate(`/contabilidad/asientos/${entry.id}`)
    },
  })
  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string> = {}
    if (!account) next.account = purchase ? 'Elegí la cuenta de gasto o de activo.' : 'Elegí la cuenta de ingreso.'
    if (needsCounterpart && !counterpart) next.counterpart = 'Es al contado y sin movimiento vinculado: elegí la caja o el banco.'
    setErrors(next)
    if (Object.keys(next).length === 0) propose.mutate()
  }
  const vat = BigInt(voucher.vat_10) + BigInt(voucher.vat_5)
  const takesVat = !purchase || voucher.imputes_vat
  const err = propose.error instanceof ApiError ? propose.error : null

  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <div className="rounded-sm border border-line px-3.5 py-2.5">
        <p className="font-medium">
          {VOUCHER_TYPE_LABELS[voucher.voucher_type]} {voucher.number} · {voucher.counterparty_name}
        </p>
        <p className="text-sm text-ink-2">
          {DIRECTION_LABELS[voucher.direction]} del {formatBookDate(voucher.issued_on)} · {CONDITION_LABELS[voucher.condition]} · total{' '}
          {formatMoney(voucher.total, 'PYG')} · IVA {formatMoney(vat.toString(), 'PYG')}
        </p>
      </div>
      <p className="text-ink-2">
        Se arma un <span className="font-medium text-ink">borrador</span> fechado el {formatBookDate(voucher.issued_on)}:{' '}
        {purchase
          ? `debe en la cuenta que elijas por la base${takesVat ? ' y en IVA crédito fiscal por el impuesto' : ' (sin crédito fiscal: el IVA va al costo)'}, haber en `
          : 'haber en la cuenta de ingreso por la base y en IVA débito fiscal por el impuesto, debe en '}
        {voucher.condition === 'credit' ? (purchase ? 'proveedores' : 'clientes') : voucher.transaction_id ? 'la cuenta del banco del movimiento vinculado' : 'la caja o el banco que elijas'}
        {voucher.voucher_type === 'credit_note' ? ', invertido por ser una nota de crédito' : ''}. Lo contabiliza una persona.
      </p>
      <Field label={purchase ? 'Cuenta de gasto o de activo' : 'Cuenta de ingreso'} error={errors.account}>
        {(p) => (
          <AccountCombobox
            {...p}
            accounts={accounts.filter((a) => mainKinds.includes(a.kind))}
            value={account}
            onChange={setAccount}
            placeholder="Código o nombre (por ejemplo 5.01)"
          />
        )}
      </Field>
      {needsCounterpart && (
        <Field label="Caja o banco del pago" error={errors.counterpart} hint="Al contado y sin movimiento de finanzas vinculado: ¿de dónde salió (o a dónde entró) la plata?">
          {(p) => <LedgerAccountSelect {...p} accounts={accounts} kinds={['asset', 'liability']} value={counterpart} onChange={setCounterpart} empty="Elegí la cuenta" />}
        </Field>
      )}
      <Field label="Descripción del asiento (opcional)" hint="Si la dejás vacía: tipo, número y contraparte del comprobante.">
        {(p) => <Input {...p} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />}
      </Field>
      {err && <ProposeError error={err} />}
      {propose.error && !err ? <ApiErrorNotice error={propose.error} /> : null}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={propose.isPending}>
          <BookPlus size={16} aria-hidden />
          Proponer asiento
        </Button>
      </div>
    </form>
  )
}

// --- Anular ---------------------------------------------------------------------------------

export function VoidVoucherForm({ voucher, onDone }: { voucher: Voucher; onDone: (changed: boolean) => void }) {
  const invalidate = useInvalidateTax()
  return (
    <ReasonForm
      intro={
        <p className="text-ink-2">
          {VOUCHER_TYPE_LABELS[voucher.voucher_type]} {voucher.number} de {voucher.counterparty_name}. Un comprobante no se borra: queda anulado, con el motivo, y deja de
          contar en el IVA, el libro y el archivo de Marangatu.
        </p>
      }
      label="Motivo de la anulación"
      submit="Anular comprobante"
      danger
      onCancel={() => onDone(false)}
      onSubmit={async (reason) => {
        await post(`/tax/vouchers/${voucher.id}/void`, { reason })
        invalidate()
        onDone(true)
      }}
    />
  )
}

// --- Exportar -------------------------------------------------------------------------------

export function XlsxButton({ year, month, direction }: { year: number; month: number | null; direction: Direction | null }) {
  const toast = useToast()
  const download = useMutation({
    mutationFn: () => getBlob(`/tax/vouchers/export${qs({ year, month, direction, format: 'xlsx' })}`),
    onSuccess: ({ blob, filename }) => {
      const name = filename ?? voucherXlsxName(year, month, direction)
      saveBlob(blob, name)
      toast('ok', `Excel descargado: ${name}`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo generar el Excel.')),
  })
  return (
    <Button variant="secondary" busy={download.isPending} onClick={() => download.mutate()}>
      <FileSpreadsheet size={15} aria-hidden />
      Descargar Excel
    </Button>
  )
}

function ExcludedList({ title, items, children }: { title: string; items: ExcludedVoucher[]; children: ReactNode }) {
  if (items.length === 0) return null
  return (
    <div className="rounded-sm border border-line">
      <p className="border-b border-line bg-sunken px-3 py-2 text-sm font-medium">
        {title} ({items.length})
      </p>
      <p className="px-3 pt-2 text-sm text-ink-2">{children}</p>
      <ul className="max-h-40 divide-y divide-line overflow-y-auto px-3 py-1 text-sm">
        {items.map((v) => (
          <li key={v.id} className="flex flex-wrap gap-x-3 py-1.5">
            <Link to={`/impuestos/comprobantes/${v.id}`} className="font-medium tabular-nums hover:text-ledger hover:underline">
              {v.number ?? registerDate(v)}
            </Link>
            <span>{v.counterparty_name}</span>
            <span className="text-ink-2">
              {DIRECTION_LABELS[v.direction]}, {formatBookDate(v.issued_on)}
            </span>
            {v.cdc && <span className="text-ink-3 tabular-nums">CDC …{v.cdc.slice(-8)}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Vista previa y descarga del registro mensual (955, con `month`) o del anual (956, `month` null; D-143). */
function MarangatuDialogBody({ year, month, ruc, onClose, yearPicker }: { year: number; month: number | null; ruc: string | null; onClose: () => void; yearPicker?: ReactNode }) {
  const annual = month === null
  const toast = useToast()
  const [separator, setSeparator] = useState<'semicolon' | 'comma'>('semicolon')
  const [limitText, setLimitText] = useState('')
  const [firstIdText, setFirstIdText] = useState('1')
  const limit = /^\d+$/.test(limitText) && Number(limitText) > 0 ? Number(limitText) : null
  const firstId = /^\d{1,5}$/.test(firstIdText) && Number(firstIdText) > 0 ? Number(firstIdText) : null
  const params = { year, month, separator, limit, first_id: firstId ?? 1 }
  const preview = useQuery({
    queryKey: ['tax', annual ? 'annual-preview' : 'marangatu-preview', params],
    queryFn: () => get<MarangatuPreview>(annual ? `/tax/vouchers/export/annual-preview${qs({ year, separator, limit, first_id: firstId ?? 1 })}` : `/tax/vouchers/export/marangatu-preview${qs(params)}`),
    retry: false,
  })
  const download = useMutation({
    mutationFn: () => getBlob(annual ? `/tax/vouchers/export/annual${qs({ year, separator, limit, first_id: firstId ?? 1 })}` : `/tax/vouchers/export${qs({ ...params, format: 'marangatu' })}`),
    onSuccess: ({ blob, filename }) => {
      const batches = preview.data?.batches.length ?? 1
      const name = filename ?? (month === null ? annualRegisterName(ruc ?? 'RUC', year, firstId ?? 1, batches) : marangatuName(ruc ?? 'RUC', year, month, firstId ?? 1, batches))
      saveBlob(blob, name)
      toast('ok', `${annual ? 'Registro anual' : 'Archivo para Marangatu'} descargado: ${name}`)
    },
  })
  const p = preview.data
  const nothing = p && p.rows === 0

  return (
    <div className="flex flex-col gap-4">
      <Notice tone="warn" title="Es un borrador: probalo antes">
        {p?.notice ??
          'Borrador del archivo de importación de Marangatu, sin verificar contra la fuente oficial. Probá primero con un archivo de uno o dos comprobantes y usá un identificador distinto en cada archivo.'}
      </Notice>

      <div className={cx('grid items-start gap-4', yearPicker ? 'grid-cols-[7rem_minmax(0,1fr)_9rem_9rem]' : 'grid-cols-[minmax(0,1fr)_9rem_9rem]')}>
        {yearPicker}
        <fieldset>
          <legend className="text-sm font-medium text-ink-2">Separador del CSV</legend>
          <div className="mt-1.5 flex gap-2">
            {(
              [
                ['semicolon', 'Punto y coma (;)', 'el del ejemplo oficial'],
                ['comma', 'Coma (,)', 'lo que dice el texto'],
              ] as const
            ).map(([value, label, hint]) => (
              <label
                key={value}
                className={cx(
                  'flex cursor-pointer items-start gap-2 rounded-sm border px-3 py-2 has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
                  separator === value ? 'border-ledger bg-ledger-soft/50' : 'border-line-strong',
                )}
              >
                <input type="radio" name="separator" className="mt-1 accent-(--ledger)" checked={separator === value} onChange={() => setSeparator(value)} />
                <span>
                  <span className="font-medium">{label}</span>
                  <span className="block text-xs text-ink-2">{hint}</span>
                </span>
              </label>
            ))}
          </div>
          <DoubtNote codes={['D-F4-1']} className="mt-2" />
        </fieldset>
        <Field label="Solo los primeros" hint="Vacío: todos. Para probar, 1 o 2.">
          {(fp) => <Input {...fp} inputMode="numeric" placeholder="Todos" value={limitText} onChange={(e) => setLimitText(e.target.value.replace(/\D/g, '').slice(0, 4))} />}
        </Field>
        <Field label="N° de archivo" hint={`Uno distinto en cada envío ${annual ? 'del año' : 'del mes'}.`} error={firstId ? undefined : 'De 1 a 99999.'}>
          {(fp) => <Input {...fp} inputMode="numeric" value={firstIdText} onChange={(e) => setFirstIdText(e.target.value.replace(/\D/g, '').slice(0, 5))} />}
        </Field>
      </div>

      {preview.isPending ? (
        <p className="text-ink-2">Armando la vista previa…</p>
      ) : preview.isError ? (
        <ApiErrorNotice error={preview.error} title="No se pudo armar la vista previa." />
      ) : p ? (
        <>
          <div className="flex flex-wrap items-baseline justify-between gap-3 rounded-sm border border-line px-4 py-3">
            <p>
              <span className="text-lg font-semibold tabular-nums">{p.rows}</span> {p.rows === 1 ? 'comprobante va' : 'comprobantes van'} en el archivo de{' '}
              {month === null ? `${year} (registro anual)` : monthTitle(`${year}-${String(month).padStart(2, '0')}`).toLowerCase()}
              {p.batches.length > 0 && (
                <span className="block text-sm text-ink-2">
                  {p.batches.map((b) => `${b.name} (${b.rows} filas)`).join(', ')} · CSV {p.encoding}, sin encabezado, separador {p.separator === 'semicolon' ? '«;»' : '«,»'}
                </span>
              )}
            </p>
            <UnverifiedMark status={p.rule_status} />
          </div>
          <ExcludedList title="Electrónicos que quedan afuera" items={p.excluded_electronic.vouchers}>
            Los comprobantes electrónicos no se importan: se imputan en Marangatu, en «Obtener Comprobantes Electrónicos y Virtuales».
          </ExcludedList>
          <ExcludedList title="Sin imputación, quedan afuera" items={p.excluded_not_imputed.vouchers}>
            Marangatu exige que cada comprobante impute a algún impuesto: estos no imputan a ninguno.
          </ExcludedList>
          {p.warnings.length > 0 && (
            <Notice tone="warn" title="Avisos">
              <ul className="list-disc pl-4">
                {p.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Notice>
          )}
          <DoubtNote codes={p.doubts.map((d) => d.code).filter((c) => c !== 'D-F4-1')} />
        </>
      ) : null}

      {download.error instanceof ApiError && <ApiErrorNotice error={download.error} />}
      <div className="flex items-center justify-end gap-2 border-t border-line pt-4">
        {nothing && (
          <p className="mr-auto flex items-center gap-1.5 text-sm text-ink-2">
            <TriangleAlert size={14} aria-hidden />
            No hay comprobantes para importar en ese {annual ? 'año' : 'mes'}.
          </p>
        )}
        <Button type="button" variant="ghost" onClick={onClose}>
          Cerrar
        </Button>
        <Button busy={download.isPending} disabled={!p || nothing || !firstId} onClick={() => download.mutate()}>
          <Download size={15} aria-hidden />
          Descargar el archivo
        </Button>
      </div>
    </div>
  )
}

export function MarangatuButton({ year, month, ruc }: { year: number; month: number | null; ruc: string | null }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button
        variant="secondary"
        disabled={month === null}
        title={month === null ? 'El archivo es de un mes: elegí el mes en el filtro.' : 'Vista previa y descarga del archivo de importación'}
        onClick={() => setOpen(true)}
      >
        <FileArchive size={15} aria-hidden />
        Archivo para Marangatu
      </Button>
      <Modal open={open} size="lg" title="Archivo para Marangatu" onClose={() => setOpen(false)}>
        {open && month !== null && <MarangatuDialogBody year={year} month={month} ruc={ruc} onClose={() => setOpen(false)} />}
      </Modal>
    </>
  )
}

/**
 * Registro anual de comprobantes (956) del IRP-RSP: compras, ventas, ingresos y egresos del
 * año en un archivo, con el mismo formato y nombre `<RUC>_REG_<AAAA>_<N>` (D-143).
 */
export function AnnualRegisterButton({ defaultYear, ruc }: { defaultYear: number; ruc: string | null }) {
  const [open, setOpen] = useState(false)
  const [year, setYear] = useState(defaultYear)
  // El registro rige desde 2021 (RG 90/2021).
  const years = Array.from({ length: Math.max(1, defaultYear - 2020) }, (_, i) => defaultYear - i)
  return (
    <>
      <Button
        variant="secondary"
        title="Vista previa y descarga del registro anual de comprobantes (956)"
        onClick={() => {
          setYear(defaultYear)
          setOpen(true)
        }}
      >
        <FileArchive size={15} aria-hidden />
        Descargar registro anual (956)
      </Button>
      <Modal open={open} size="lg" title="Registro anual de comprobantes (956)" onClose={() => setOpen(false)}>
        {open && (
          <MarangatuDialogBody
            key={year}
            year={year}
            month={null}
            ruc={ruc}
            onClose={() => setOpen(false)}
            yearPicker={
              <Field label="Año">
                {(fp) => (
                  <Select {...fp} value={String(year)} onChange={(e) => setYear(Number(e.target.value))}>
                    {years.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
            }
          />
        )}
      </Modal>
    </>
  )
}

/** Marca de asiento del comprobante, con enlace (como en finanzas). */
export function VoucherEntryBadge({ voucher }: { voucher: Voucher }) {
  if (!voucher.journal_entry_id || !voucher.journal_entry_status) return null
  const s = voucher.journal_entry_status
  return (
    <Link to={`/contabilidad/asientos/${voucher.journal_entry_id}`} className="hover:underline" title="Ver el asiento">
      <Badge tone={s === 'posted' ? 'ok' : s === 'draft' ? 'warn' : 'neutral'}>
        {s === 'posted' ? 'Asiento contabilizado' : s === 'draft' ? 'Asiento en borrador' : s === 'reversed' ? 'Asiento revertido' : 'Asiento descartado'}
      </Badge>
    </Link>
  )
}
