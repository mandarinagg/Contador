/** Piezas compartidas por las pantallas de finanzas. Solo tokens del sistema de diseño. */
import { Building2, LockKeyhole } from 'lucide-react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { Input, Notice, Skeleton } from '../../components/ui'
import { cx } from '../../lib/cx'
import { businessContextLabel } from '../../lib/format'
import { CURRENCY_DECIMALS, formatMoney, isNegative, isZeroAmount, parseAmountInput, toInputText } from '../../lib/money'
import { ApiError } from '../../services/api'
import { useSession } from '../../stores/session'
import type { FinanceContext } from './types'

/**
 * Importe con su signo **y** su color: entra (+, verde de libro) o sale (−, rojo débito).
 * `flow`: muestra "+" en las entradas; si no, solo el "−" de las salidas (saldos).
 */
export function Amount({
  value,
  currency,
  flow = false,
  className,
  strong = false,
}: {
  value: string
  currency: string
  flow?: boolean
  className?: string
  strong?: boolean
}) {
  const negative = isNegative(value)
  const zero = isZeroAmount(value)
  return (
    <span
      className={cx(
        'whitespace-nowrap tabular-nums',
        negative ? 'text-debit' : flow && !zero ? 'text-ledger' : '',
        strong && 'font-semibold',
        className,
      )}
    >
      {formatMoney(value, currency, { sign: flow ? 'always' : 'negative' })}
    </span>
  )
}

/**
 * Entrada de importe en formato paraguayo. Guarda el texto tal como se escribe; al salir
 * del campo lo reescribe con puntos de miles si es válido y muestra el error si no.
 * El valor para la API se obtiene con `parseAmountInput` al enviar.
 */
export function AmountInput({
  value,
  currency,
  onChange,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'> & {
  value: string
  currency: string
  onChange: (text: string) => void
}) {
  return (
    <div className="relative">
      <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-ink-3">
        {currency === 'PYG' ? '₲' : currency}
      </span>
      <Input
        {...props}
        inputMode="decimal"
        autoComplete="off"
        className={cx('text-right tabular-nums', currency === 'PYG' ? 'pl-7' : 'pl-12')}
        placeholder={CURRENCY_DECIMALS[currency] === 0 ? '1.234.567' : '1.234,50'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => {
          const parsed = parseAmountInput(value, currency)
          if (parsed.ok) onChange((parsed.value.startsWith('-') ? '-' : '') + toInputText(parsed.value, currency))
          props.onBlur?.(e)
        }}
      />
    </div>
  )
}

/** Error de la API (o de red) en español, con los mensajes por campo si los hay. */
export function ApiErrorNotice({ error, title }: { error: unknown; title?: string }) {
  if (!error) return null
  const api = error instanceof ApiError ? error : null
  const fields = api ? Object.values(api.fieldErrors()) : []
  return (
    <Notice tone="bad" title={title ?? api?.message ?? 'Algo falló. Intentá de nuevo.'}>
      {title && api ? api.message : null}
      {fields.length > 0 && (
        <ul className="mt-1 list-disc pl-4">
          {fields.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </Notice>
  )
}

/** Identidad del contexto: icono + nombre (+ "privado") con su color. Nunca solo el color. */
export function ContextTag({ context, size = 'sm' }: { context: FinanceContext; size?: 'sm' | 'md' }) {
  const personal = context.kind === 'personal'
  const businessLabel = businessContextLabel(useSession().me?.organization.legal_form)
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-sm font-medium',
        size === 'md' ? 'px-2 py-1 text-base' : 'px-1.5 py-0.5 text-xs',
        personal ? 'bg-personal-soft text-personal' : 'bg-ledger-soft text-ledger',
      )}
    >
      {personal ? <LockKeyhole size={size === 'md' ? 15 : 12} aria-hidden /> : <Building2 size={size === 'md' ? 15 : 12} aria-hidden />}
      {personal ? 'Personal' : businessLabel}
      {personal && <span className="font-normal opacity-80">· privado</span>}
    </span>
  )
}

export function TableSkeleton({ rows = 4, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="flex flex-col gap-3 p-5" aria-busy="true" aria-label="Cargando">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="grid gap-4" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, j) => (
            <Skeleton key={j} className="h-5" />
          ))}
        </div>
      ))}
    </div>
  )
}

/** Encabezado de una tabla con el estilo de la app. */
export function Th({ children, className, align = 'left' }: { children?: ReactNode; className?: string; align?: 'left' | 'right' }) {
  return (
    <th scope="col" className={cx('px-4 py-2.5 font-medium', align === 'right' ? 'text-right' : 'text-left', className)}>
      {children}
    </th>
  )
}

/** Explica, junto a una acción deshabilitada, por qué no se puede usar. */
export function ReadOnlyHint({ reason }: { reason: string }) {
  if (!reason) return null
  return <p className="text-sm text-ink-3">{reason}</p>
}

/** Interruptor accesible (casilla) con etiqueta. */
export function Check({
  label,
  checked,
  onChange,
  disabled,
  hint,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
  hint?: string
}) {
  return (
    <label className={cx('flex items-start gap-2 text-base', disabled ? 'text-ink-3' : 'cursor-pointer')}>
      <input
        type="checkbox"
        className="mt-0.5 size-4 accent-(--ledger)"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        {label}
        {hint && <span className="block text-sm text-ink-3">{hint}</span>}
      </span>
    </label>
  )
}
