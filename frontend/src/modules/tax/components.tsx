/** Piezas compartidas de la tributación. Solo tokens del sistema de diseño (styles/index.css). */
import { useMutation } from '@tanstack/react-query'
import { Ban, CalendarClock, CircleAlert, CircleCheck, CircleDashed, ExternalLink, FileCheck2, HelpCircle, ShieldAlert, ShieldCheck } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import { Badge, Button, Field, Input, Textarea } from '../../components/ui'
import { cx } from '../../lib/cx'
import { ApiErrorNotice } from '../finance/components'
import { doubtText, OBLIGATION_STATUS_LABELS, RULE_STATUS_LABELS } from './labels'
import type { DisplayStatus } from './logic'
import type { Rule, RuleApplied } from './types'

/** Marca «sin verificar» (D-082): todo lo que depende de una regla pendiente la lleva, con texto y no solo color. */
export function UnverifiedMark({ status, className, label = 'Sin verificar' }: { status: string | null | undefined; className?: string; label?: string }) {
  if (status === 'verified') {
    return (
      <span className={cx('inline-flex items-center gap-1 rounded-sm bg-ledger-soft px-1.5 py-0.5 text-xs font-medium text-ledger', className)}>
        <ShieldCheck size={12} aria-hidden />
        Verificada
      </span>
    )
  }
  return (
    <span
      className={cx('inline-flex items-center gap-1 rounded-sm bg-amber-soft px-1.5 py-0.5 text-xs font-medium text-amber', className)}
      title="Depende de reglas que ningún contador verificó todavía: no es un dato oficial."
    >
      <ShieldAlert size={12} aria-hidden />
      {status === 'deprecated' ? 'Regla deprecada' : label}
    </span>
  )
}

export function RuleStatusBadge({ status }: { status: string }) {
  return <Badge tone={status === 'verified' ? 'ok' : status === 'deprecated' ? 'neutral' : 'warn'}>{RULE_STATUS_LABELS[status] ?? status}</Badge>
}

/**
 * Las reglas aplicadas a un cálculo (BR-TAX-01/02), a un clic: código, versión, estado,
 * norma y enlace a la fuente (que viene del listado de reglas).
 */
export function RulesApplied({ rules, byId, summary = 'Regla y norma' }: { rules: RuleApplied[]; byId: Map<string, Rule>; summary?: string }) {
  if (rules.length === 0) return <span className="text-sm text-ink-3">Sin regla</span>
  return (
    <details className="group text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-ledger hover:underline [&::-webkit-details-marker]:hidden">
        {summary}
        <span aria-hidden className="transition-transform group-open:rotate-90">›</span>
      </summary>
      <ul className="mt-1.5 flex flex-col gap-1.5 border-l-2 border-line pl-3">
        {rules.map((r) => {
          const full = byId.get(r.id)
          return (
            <li key={r.id}>
              <span className="font-medium tabular-nums">
                {r.code} v{r.version}
              </span>{' '}
              <RuleStatusBadge status={r.validation_status} />
              {r.legal_reference && <span className="block text-ink-2">{r.legal_reference}</span>}
              {full?.source_url && (
                <a href={full.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-ledger hover:underline">
                  Ver la fuente
                  <ExternalLink size={12} aria-hidden />
                  <span className="sr-only">(se abre aparte)</span>
                </a>
              )}
            </li>
          )
        })}
      </ul>
    </details>
  )
}

/** Duda abierta de la investigación (D-F4-x): se muestra donde afecta, para que el contador la resuelva. */
export function DoubtNote({ codes, className }: { codes: string[]; className?: string }) {
  if (codes.length === 0) return null
  return (
    <details className={cx('group text-sm', className)}>
      <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm font-medium text-amber hover:underline [&::-webkit-details-marker]:hidden">
        <HelpCircle size={13} aria-hidden />
        Duda abierta para el contador ({codes.join(', ')})
      </summary>
      <ul className="mt-1 flex flex-col gap-1 pl-4 text-ink-2">
        {codes.map((c) => (
          <li key={c}>
            <span className="font-medium text-ink">{c}.</span> {doubtText(c)}
          </li>
        ))}
      </ul>
    </details>
  )
}

const STATUS_STYLE: Record<DisplayStatus, { tone: string; icon: ReactNode }> = {
  overdue: { tone: 'bg-debit-soft text-debit', icon: <CircleAlert size={13} aria-hidden /> },
  due_soon: { tone: 'bg-amber-soft text-amber', icon: <CalendarClock size={13} aria-hidden /> },
  pending: { tone: 'bg-sunken text-ink-2', icon: <CircleDashed size={13} aria-hidden /> },
  filed: { tone: 'bg-ledger-soft text-ledger', icon: <FileCheck2 size={13} aria-hidden /> },
  paid: { tone: 'bg-ledger-soft text-ledger', icon: <CircleCheck size={13} aria-hidden /> },
  not_applicable: { tone: 'bg-sunken text-ink-3', icon: <Ban size={13} aria-hidden /> },
}

/** Estado de una obligación con icono y texto (nunca solo el color). */
export function ObligationStatusBadge({ status }: { status: DisplayStatus }) {
  const s = STATUS_STYLE[status]
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium whitespace-nowrap', s.tone)}>
      {s.icon}
      {OBLIGATION_STATUS_LABELS[status]}
    </span>
  )
}

/** Leyenda fija de toda estimación (BR-TAX-03). */
export function EstimateLegend({ className }: { className?: string }) {
  return (
    <p role="note" aria-label="Estimación interna" className={cx('flex items-center gap-2 rounded-sm border border-amber/40 bg-amber-soft px-3 py-2 text-sm font-medium text-amber', className)}>
      <ShieldAlert size={15} aria-hidden />
      Estimación interna: no es una declaración. Se presenta en Marangatu.
    </p>
  )
}

/** Formulario de un motivo (anular, no aplica, reabrir, deprecar): 3 a 300 caracteres. */
export function ReasonForm({
  label = 'Motivo',
  hint,
  submit,
  danger,
  intro,
  onSubmit,
  onCancel,
}: {
  label?: string
  hint?: string
  submit: string
  danger?: boolean
  intro?: ReactNode
  onSubmit: (reason: string) => Promise<unknown>
  onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string>()
  const run = useMutation({ mutationFn: onSubmit })
  const send = (e: FormEvent) => {
    e.preventDefault()
    const text = reason.trim()
    if (text.length < 3) {
      setError('Escribí el motivo (al menos 3 caracteres).')
      return
    }
    run.mutate(text)
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      {intro}
      <Field label={label} hint={hint ?? 'Queda en la auditoría.'} error={error}>
        {(p) => <Textarea {...p} autoFocus maxLength={300} value={reason} onChange={(e) => { setReason(e.target.value); setError(undefined) }} />}
      </Field>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" variant={danger ? 'danger' : 'primary'} busy={run.isPending}>
          {submit}
        </Button>
      </div>
    </form>
  )
}

/**
 * Verificación profesional (BR-TAX-12): nombre y matrícula del contador, y una tercera
 * referencia (nota o constancia de RUC).
 */
export function VerifyForm({
  intro,
  thirdLabel,
  thirdHint,
  thirdRequired,
  submit,
  onSubmit,
  onCancel,
}: {
  intro: ReactNode
  thirdLabel: string
  thirdHint: string
  thirdRequired: boolean
  submit: string
  onSubmit: (v: { name: string; license: string; third: string }) => Promise<unknown>
  onCancel: () => void
}) {
  const [name, setName] = useState('')
  const [license, setLicense] = useState('')
  const [third, setThird] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const run = useMutation({ mutationFn: onSubmit })
  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string> = {}
    if (name.trim().length < 3) next.name = 'Escribí el nombre completo de quien verifica.'
    if (license.trim().length < 2) next.license = 'La matrícula es obligatoria: la verificación es un acto profesional.'
    if (thirdRequired && third.trim().length < 2) next.third = 'Indicá la referencia del documento.'
    setErrors(next)
    if (Object.keys(next).length === 0) run.mutate({ name: name.trim(), license: license.trim(), third: third.trim() })
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <div className="text-ink-2">{intro}</div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Nombre del contador" error={errors.name}>
          {(p) => <Input {...p} autoFocus value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Matrícula profesional" error={errors.license} hint="Número de registro del Colegio de Contadores o de la DNIT.">
          {(p) => <Input {...p} value={license} onChange={(e) => setLicense(e.target.value)} />}
        </Field>
      </div>
      <Field label={thirdLabel} hint={thirdHint} error={errors.third}>
        {(p) => <Input {...p} value={third} onChange={(e) => setThird(e.target.value)} />}
      </Field>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          <ShieldCheck size={16} aria-hidden />
          {submit}
        </Button>
      </div>
    </form>
  )
}

/** Fila de definición para fichas (detalle de un comprobante, una obligación). */
export function Item({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  )
}

/** Fecha en dos pisos (día grande, mes chico): la forma de una hoja de calendario de escritorio. */
export function DayStub({ iso, tone = 'neutral' }: { iso: string; tone?: 'neutral' | 'bad' | 'warn' }) {
  const [y, m, d] = iso.split('-').map(Number)
  const month = new Intl.DateTimeFormat('es-PY', { month: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d))).replace('.', '')
  const weekday = new Intl.DateTimeFormat('es-PY', { weekday: 'short', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, d))).replace('.', '')
  return (
    <span
      className={
        'flex w-12 shrink-0 flex-col items-center rounded-sm border pt-0.5 pb-1 leading-none ' +
        (tone === 'bad' ? 'border-debit/50 text-debit' : tone === 'warn' ? 'border-amber/50 text-amber' : 'border-line-strong text-ink')
      }
      aria-hidden
    >
      <span className="text-[0.65rem] text-ink-2">{weekday}</span>
      <span className="text-lg font-semibold tabular-nums">{d}</span>
      <span className="text-[0.65rem] text-ink-2">{month}</span>
    </span>
  )
}
