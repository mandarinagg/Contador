/**
 * Componentes base del sistema de diseño. Cada uno usa solo tokens de
 * styles/index.css; ninguna pantalla define colores propios.
 */
import { X } from 'lucide-react'
import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type Ref,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useEffect,
  useId,
  useRef,
} from 'react'
import { cx } from '../../lib/cx'


// --- Botón -------------------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

const buttonStyles: Record<ButtonVariant, string> = {
  primary: 'bg-ledger text-surface hover:bg-ledger-strong border border-transparent',
  secondary: 'bg-surface text-ink border border-line-strong hover:bg-sunken',
  ghost: 'text-ink-2 hover:text-ink hover:bg-sunken border border-transparent',
  danger: 'bg-surface text-debit border border-line-strong hover:bg-debit-soft',
}

export function Button({
  variant = 'primary',
  busy = false,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        'inline-flex h-9 items-center justify-center gap-2 rounded-sm px-3.5 text-base font-medium',
        'transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-55',
        buttonStyles[variant],
        className,
      )}
    >
      {busy && (
        <span className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" />
      )}
      {children}
    </button>
  )
}

// --- Campos ------------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  children,
  id,
}: {
  label: string
  hint?: ReactNode
  error?: string
  children: (props: { id: string; 'aria-invalid'?: boolean; 'aria-describedby'?: string }) => ReactNode
  id?: string
}) {
  const autoId = useId()
  const fieldId = id ?? autoId
  const describedBy = error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={fieldId} className="text-sm font-medium text-ink-2">
        {label}
      </label>
      {children({ id: fieldId, 'aria-invalid': error ? true : undefined, 'aria-describedby': describedBy })}
      {error ? (
        <p id={`${fieldId}-error`} className="text-sm text-debit">
          {error}
        </p>
      ) : hint ? (
        <p id={`${fieldId}-hint`} className="text-sm text-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

const controlBase =
  'h-9 w-full rounded-sm border border-line-strong bg-surface px-3 text-base text-ink ' +
  'placeholder:text-ink-3 transition-colors hover:border-ink-3 ' +
  'aria-invalid:border-debit disabled:bg-sunken disabled:text-ink-3'

/** Acepta `ref` (React 19: es una prop más) para enfocar el campo desde afuera. */
export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  return <input {...props} className={cx(controlBase, className)} />
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx(controlBase, 'h-auto min-h-20 py-2 leading-snug', className)} />
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={cx(controlBase, 'pr-8', className)}>
      {children}
    </select>
  )
}

// --- Indicadores -------------------------------------------------------------------

type Tone = 'neutral' | 'ok' | 'warn' | 'bad'
const toneStyles: Record<Tone, string> = {
  neutral: 'bg-sunken text-ink-2',
  ok: 'bg-ledger-soft text-ledger',
  warn: 'bg-amber-soft text-amber',
  bad: 'bg-debit-soft text-debit',
}

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx('inline-flex items-center rounded-sm px-1.5 py-0.5 text-xs font-medium', toneStyles[tone])}>
      {children}
    </span>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cx('block animate-pulse rounded-sm bg-sunken', className)} />
}

export function Notice({ tone = 'neutral', title, children }: { tone?: Tone; title: string; children?: ReactNode }) {
  return (
    <div
      role={tone === 'bad' ? 'alert' : 'status'}
      className={cx('rounded-sm border-l-2 px-3.5 py-2.5', toneStyles[tone], {
        neutral: 'border-line-strong', ok: 'border-ledger', warn: 'border-amber', bad: 'border-debit',
      }[tone])}
    >
      <p className="font-medium">{title}</p>
      {children && <div className="mt-0.5 text-sm opacity-90">{children}</div>}
    </div>
  )
}

// --- Estructura de página ----------------------------------------------------------

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="mb-6 flex items-end justify-between gap-6">
      <div className="ledger-rule min-w-0 flex-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-[70ch] text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2 pb-2">{actions}</div>}
    </header>
  )
}

export function Sheet({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx('rounded-md border border-line bg-surface shadow-(--shadow-sheet)', className)}>
      {children}
    </section>
  )
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 px-6 py-10">
      <p className="text-md font-medium">{title}</p>
      {children && <p className="max-w-[60ch] text-ink-2">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

// --- Modal -------------------------------------------------------------------------

export function Modal({
  open,
  title,
  onClose,
  children,
  size = 'md',
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  /** `lg` para formularios con dos columnas o tablas. */
  size?: 'md' | 'lg'
}) {
  const ref = useRef<HTMLDialogElement>(null)
  // Un id por modal: una pantalla puede tener varios diálogos montados a la vez.
  const titleId = useId()
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={onClose}
      aria-labelledby={titleId}
      className={cx(
        'm-auto w-full rounded-md bg-surface p-0 text-ink shadow-(--shadow-float) backdrop:bg-black/35 open:animate-rise',
        size === 'lg' ? 'max-w-2xl' : 'max-w-lg',
      )}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <h2 id={titleId} className="text-md font-semibold">
          {title}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="rounded-sm p-1 text-ink-3 hover:bg-sunken hover:text-ink"
        >
          <X size={16} />
        </button>
      </div>
      <div className="px-5 py-4">{open && children}</div>
    </dialog>
  )
}
