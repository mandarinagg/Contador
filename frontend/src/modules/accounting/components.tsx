/** Piezas compartidas de contabilidad. Solo tokens del sistema de diseño (styles/index.css). */
import { useQuery } from '@tanstack/react-query'
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { type KeyboardEvent, type ReactNode, type Ref, useId, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Badge, Notice } from '../../components/ui'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { formatMoney, isNegative } from '../../lib/money'
import { get } from '../../services/api'
import { useSession } from '../../stores/session'
import type { Organization } from '../../types/api'
import { matchesAccount } from './chartTree'
import { KIND_LABELS, STATUS_LABELS } from './labels'
import type { AccountingSettings, ChartStatus, EntryStatus, LedgerAccount } from './types'

/**
 * Importe en guaraníes, alineado por cifras tabulares. Un negativo lleva el signo menos real
 * (U+2212) además del color: nunca depende solo del color (D-053).
 */
export function Pyg({ value, strong, muted, symbol = false, className }: { value: string; strong?: boolean; muted?: boolean; symbol?: boolean; className?: string }) {
  return (
    <span className={cx('whitespace-nowrap tabular-nums', isNegative(value) && 'text-debit', muted && 'text-ink-3', strong && 'font-semibold', className)}>
      {formatMoney(value, 'PYG', { symbol })}
    </span>
  )
}

/** Total con la doble raya contable debajo (la firma visual de la app). */
export function RuledTotal({ value, label }: { value: string; label?: string }) {
  return (
    <span className="ledger-rule inline-block min-w-24 text-right" aria-label={label}>
      <Pyg value={value} strong />
    </span>
  )
}

/** Celda vacía de un importe que no corresponde (el haber de una línea de debe). */
export const Blank = () => <span aria-hidden className="text-ink-3">·</span>

export function EntryStatusBadge({ status }: { status: EntryStatus }) {
  const tone = status === 'posted' ? 'ok' : status === 'draft' ? 'warn' : status === 'reversed' ? 'neutral' : 'bad'
  return <Badge tone={tone}>{STATUS_LABELS[status]}</Badge>
}

/** Aviso obligatorio mientras el plan no esté validado por un contador (D-038). */
export function UnvalidatedNotice({ status, compact = false }: { status: ChartStatus; compact?: boolean }) {
  if (status === 'validated') return null
  if (compact) {
    return (
      <p role="status" className="flex items-center gap-2 rounded-sm bg-amber-soft px-3 py-2 text-sm font-medium text-amber">
        <ShieldAlert size={15} aria-hidden />
        Plan de cuentas sin validar por un contador
      </p>
    )
  }
  return (
    <Notice tone="warn" title="Plan de cuentas sin validar por un contador">
      {status === 'none'
        ? 'Todavía no hay plan de cuentas cargado.'
        : 'Es una propuesta basada en la RG N° 49/2014. Hasta que un contador la revise y la marque como validada, estos números no son un estado contable firmado.'}
    </Notice>
  )
}

/** Franja de estado del plan, visible en todas las pantallas de contabilidad. */
export function ChartStatusStrip({ settings }: { settings: AccountingSettings | undefined }) {
  if (!settings) return <div className="h-9" />
  const validated = settings.chart_status === 'validated'
  return (
    <div
      role="note"
      aria-label="Estado del plan de cuentas"
      className={cx(
        'mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-4 py-2 text-sm',
        validated ? 'border-line bg-ledger-soft' : 'border-amber/40 bg-amber-soft',
      )}
    >
      {validated ? <ShieldCheck size={16} className="text-ledger" aria-hidden /> : <ShieldAlert size={16} className="text-amber" aria-hidden />}
      {validated ? (
        <span className="text-ink">
          <span className="font-semibold text-ledger">Plan de cuentas validado</span> por {settings.chart_validated_by_name} (matrícula{' '}
          {settings.chart_validated_reference}), el {formatDateTime(settings.chart_validated_at as string)}.
        </span>
      ) : settings.chart_status === 'pending' ? (
        <span className="text-ink">
          <span className="font-semibold text-amber">Plan de cuentas sin validar por un contador.</span> Los reportes lo van a decir hasta que se valide.
        </span>
      ) : (
        <span className="text-ink">
          <span className="font-semibold text-amber">Todavía no hay plan de cuentas.</span> Es lo primero para empezar la contabilidad.
        </span>
      )}
      <Link to="/contabilidad/plan" className="ml-auto font-medium text-ledger hover:underline">
        {settings.chart_status === 'none' ? 'Cargar el plan' : 'Ver el plan'}
      </Link>
    </div>
  )
}

/** Código y nombre de una cuenta, con el código en tinta secundaria y cifras tabulares. */
export function AccountName({ code, name, to }: { code: string; name: string; to?: string }) {
  const body = (
    <>
      <span className="mr-2 text-ink-2 tabular-nums">{code}</span>
      <span>{name}</span>
    </>
  )
  return to ? (
    <Link to={to} className="hover:text-ledger hover:underline">
      {body}
    </Link>
  ) : (
    <span>{body}</span>
  )
}

// --- Selector de cuenta (combobox con búsqueda por código o nombre) ----------------------

const MAX_OPTIONS = 80

export function AccountCombobox({
  accounts,
  value,
  onChange,
  known,
  id,
  placeholder = 'Código o nombre',
  inputRef,
  className,
  onKeyDown,
  ...aria
}: {
  /** Opciones elegibles (imputables, no archivadas). */
  accounts: LedgerAccount[]
  value: string
  onChange: (id: string) => void
  /** Todas las cuentas, para nombrar la elegida aunque ya no sea elegible. */
  known?: Map<string, LedgerAccount>
  id?: string
  placeholder?: string
  inputRef?: Ref<HTMLInputElement>
  className?: string
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>, open: boolean) => void
  'aria-label'?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}) {
  const listId = useId()
  const [query, setQuery] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLUListElement>(null)
  const selected = known?.get(value) ?? accounts.find((a) => a.id === value)
  const label = selected ? `${selected.code} ${selected.name}` : ''
  const options = useMemo(() => accounts.filter((a) => matchesAccount(a, query ?? '')).slice(0, MAX_OPTIONS), [accounts, query])

  const choose = (a: LedgerAccount | undefined) => {
    if (a) onChange(a.id)
    setQuery(null)
    setOpen(false)
  }
  const move = (delta: number) => {
    const next = Math.max(0, Math.min(options.length - 1, active + delta))
    setActive(next)
    listRef.current?.children[next]?.scrollIntoView({ block: 'nearest' })
  }

  return (
    <div className={cx('relative', className)}>
      <input
        ref={inputRef}
        id={id}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && options[active] ? `${listId}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        {...aria}
        value={query ?? label}
        title={label || undefined}
        className={cx(
          'h-9 w-full truncate rounded-sm border border-line-strong bg-surface px-3 text-base text-ink placeholder:text-ink-3',
          'transition-colors hover:border-ink-3 aria-invalid:border-debit',
        )}
        onFocus={(e) => e.target.select()}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
          setActive(0)
        }}
        onBlur={() => {
          setQuery(null)
          setOpen(false)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            if (!open) {
              setOpen(true)
              setActive(Math.max(0, options.findIndex((a) => a.id === value)))
            } else move(1)
          } else if (e.key === 'ArrowUp' && open) {
            e.preventDefault()
            move(-1)
          } else if (e.key === 'Enter' && open) {
            e.preventDefault()
            choose(options[active])
            return
          } else if (e.key === 'Tab' && open && query) {
            choose(options[active])
          } else if (e.key === 'Escape' && open) {
            e.preventDefault()
            e.stopPropagation()
            setQuery(null)
            setOpen(false)
            return
          }
          onKeyDown?.(e, open)
        }}
      />
      {open && (
        <ul
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label="Cuentas imputables"
          className="absolute top-full left-0 z-30 mt-1 max-h-72 w-[max(100%,30rem)] overflow-y-auto rounded-md bg-surface py-1 shadow-(--shadow-float)"
        >
          {options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-ink-3">Ninguna cuenta imputable coincide. Probá con el código (1.01) o parte del nombre.</li>
          ) : (
            options.map((a, i) => (
              <li
                key={a.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(a)}
                className={cx('flex cursor-pointer items-baseline gap-3 px-3 py-1.5', i === active ? 'bg-ledger-soft' : '')}
              >
                <span className="w-28 shrink-0 text-sm text-ink-2 tabular-nums">{a.code}</span>
                <span className="min-w-0 flex-1 truncate">{a.name}</span>
                <span className="shrink-0 text-xs text-ink-3">{KIND_LABELS[a.kind]}</span>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}

/** Selector nativo de cuentas imputables agrupadas por tipo (formularios cortos de configuración). */
export function LedgerAccountSelect({
  accounts,
  kinds,
  value,
  onChange,
  empty = 'Sin cuenta contable',
  ...props
}: {
  accounts: LedgerAccount[]
  kinds: LedgerAccount['kind'][]
  value: string
  onChange: (id: string) => void
  empty?: string
  id?: string
  disabled?: boolean
  'aria-label'?: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}) {
  const options = accounts.filter((a) => a.is_postable && (!a.archived_at || a.id === value) && kinds.includes(a.kind))
  return (
    <select
      {...props}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-sm border border-line-strong bg-surface px-3 pr-8 text-base text-ink hover:border-ink-3 disabled:bg-sunken disabled:text-ink-3"
    >
      <option value="">{empty}</option>
      {kinds.map((k) => {
        const ofKind = options.filter((a) => a.kind === k)
        if (ofKind.length === 0) return null
        return (
          <optgroup key={k} label={KIND_LABELS[k]}>
            {ofKind.map((a) => (
              <option key={a.id} value={a.id}>
                {a.code} {a.name}
                {a.archived_at ? ' (archivada)' : ''}
              </option>
            ))}
          </optgroup>
        )
      })}
    </select>
  )
}

/**
 * Encabezado de un libro o estado contable: empresa con su RUC, título, alcance y la moneda.
 * Al imprimir es el encabezado del papel (con la fecha de emisión); las acciones de `aside`
 * no se imprimen.
 */
export function ReportHeading({ title, scope, status, aside }: { title: string; scope: string; status: ChartStatus; aside?: ReactNode }) {
  const { me } = useSession()
  const org = useQuery({ queryKey: ['organization'], queryFn: () => get<Organization>('/organization'), staleTime: 60_000 })
  // La fecha de emisión se fija al montar (no en cada render).
  const [issuedAt] = useState(() => new Date().toISOString())
  const ruc = org.data?.ruc ? `RUC ${org.data.ruc}-${org.data.ruc_check_digit}` : org.data ? 'RUC sin cargar' : ''
  return (
    <div className="report-heading border-b border-line px-6 pt-5 pb-4">
      <div className="flex items-start justify-between gap-6">
        <div>
          <p className="text-sm text-ink-2">
            <span className="font-medium text-ink">{org.data?.legal_name ?? me?.organization.legal_name}</span>
            {ruc && <span className="ml-2">{ruc}</span>}
          </p>
          <h2 className="mt-0.5 text-lg font-semibold tracking-tight">{title}</h2>
          <p className="mt-0.5 text-sm text-ink-2">
            {scope}. Importes en guaraníes.
          </p>
          <p className="print-only mt-0.5 text-sm text-ink-2">Emitido el {formatDateTime(issuedAt)}</p>
        </div>
        {aside}
      </div>
      {status !== 'validated' && (
        <div className="mt-3">
          <UnvalidatedNotice status={status} compact />
        </div>
      )}
    </div>
  )
}
