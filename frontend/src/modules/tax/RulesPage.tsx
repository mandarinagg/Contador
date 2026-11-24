/**
 * Reglas y feriados (D-082, D-108, D-114, D-102): las normas que usa la app, a la vista del
 * contador para verificarlas (BR-TAX-12). Tres pestañas: reglas, feriados y excepciones de
 * vencimiento. Todo nace «sin verificar»; verificar es un acto profesional (`tax.verify`).
 */
import { useMutation } from '@tanstack/react-query'
import { CalendarPlus, Download, ExternalLink, Pencil, ShieldCheck, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { plural } from '../../lib/format'
import { api, patch, post } from '../../services/api'
import { ApiErrorNotice, Check, ReadOnlyHint, TableSkeleton, Th } from '../finance/components'
import { errorMessage } from '../finance/forms'
import { formatBookDate } from '../finance/labels'
import { ReasonForm, RuleStatusBadge, VerifyForm } from './components'
import { type TaxPerms, useExceptions, useHolidays, useInvalidateTax, useRules, useTaxPerms } from './data'
import { CONFIDENCE_LABELS, monthTitle, OBLIGATION_LABELS, obligationLabel } from './labels'
import type { DueDateException, Holiday, Rule, RuleLoadResult } from './types'

type Tab = 'reglas' | 'feriados' | 'excepciones'
const TABS: { id: Tab; label: string }[] = [
  { id: 'reglas', label: 'Reglas' },
  { id: 'feriados', label: 'Feriados' },
  { id: 'excepciones', label: 'Excepciones de vencimiento' },
]

const SourceLink = ({ url }: { url: string | null }) =>
  url ? (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-ledger hover:underline">
      Ver la fuente
      <ExternalLink size={12} aria-hidden />
      <span className="sr-only">(se abre aparte)</span>
    </a>
  ) : null

function loadSummary(r: RuleLoadResult): string {
  const parts = [`${plural(r.created, 'regla nueva', 'reglas nuevas')}`, `${r.unchanged} sin cambios`]
  if (r.differing.length) parts.push(`${r.differing.length} distintas de las cargadas (no se pisaron)`)
  if (r.rejected.length) parts.push(`${r.rejected.length} rechazadas`)
  if (r.exceptions_created) parts.push(plural(r.exceptions_created, 'excepción creada', 'excepciones creadas'))
  return `Reglas candidatas: ${parts.join(', ')}.`
}

// --- Reglas ------------------------------------------------------------------------------

function RuleRow({ rule, perms, onVerify, onDeprecate }: { rule: Rule; perms: TaxPerms; onVerify: () => void; onDeprecate: () => void }) {
  return (
    <li id={`regla-${rule.code}`} data-testid={`rule-${rule.code}`} className={cx('flex gap-4 px-5 py-4', rule.validation_status === 'deprecated' && 'opacity-70')}>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="font-medium tabular-nums">
            {rule.code} v{rule.version}
          </span>
          <RuleStatusBadge status={rule.validation_status} />
          {rule.used_by_calculations && <Badge>La usa la app</Badge>}
          {rule.confidence && <span className="text-sm text-ink-3">{CONFIDENCE_LABELS[rule.confidence] ?? rule.confidence}</span>}
        </p>
        <p className="mt-1 text-ink-2">{rule.description}</p>
        <p className="mt-1 text-sm text-ink-2">
          {rule.valid_from ? `Vigente desde el ${formatBookDate(rule.valid_from)}` : 'Sin fecha de vigencia: no rige'}
          {rule.valid_to && ` hasta el ${formatBookDate(rule.valid_to)}`}
          {rule.legal_reference && ` · ${rule.legal_reference}`}
        </p>
        <div className="mt-1 flex flex-wrap gap-x-4">
          <SourceLink url={rule.source_url} />
          {(rule.notes || Object.keys(rule.parameters).length > 0) && (
            <details className="text-sm">
              <summary className="cursor-pointer text-ledger hover:underline">Parámetros y notas</summary>
              {rule.notes && <p className="mt-1 max-w-[80ch] text-ink-2">{rule.notes}</p>}
              <pre className="mt-1 max-h-56 overflow-auto rounded-sm bg-sunken p-2 text-xs">{JSON.stringify(rule.parameters, null, 2)}</pre>
            </details>
          )}
        </div>
        {rule.validation_status === 'verified' && (
          <p className="mt-1 text-sm text-ledger">
            Verificada por {rule.reviewed_by_name} (matrícula {rule.reviewed_reference}){rule.reviewed_at && ` el ${formatBookDate(rule.reviewed_at.slice(0, 10))}`}
            {rule.review_note && `: ${rule.review_note}`}
          </p>
        )}
        {rule.validation_status === 'deprecated' && <p className="mt-1 text-sm text-ink-2">Deprecada: {rule.deprecation_reason}</p>}
      </div>
      {perms.canVerify && rule.validation_status !== 'deprecated' && (
        <div className="flex shrink-0 flex-col items-end gap-2">
          {rule.validation_status === 'pending' && (
            <Button variant="secondary" onClick={onVerify}>
              <ShieldCheck size={15} aria-hidden />
              Verificar
            </Button>
          )}
          <Button variant="ghost" onClick={onDeprecate}>
            Deprecar
          </Button>
        </div>
      )}
    </li>
  )
}

function RulesTab({ perms }: { perms: TaxPerms }) {
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const rules = useRules()
  const [status, setStatus] = useState('')
  const [usedOnly, setUsedOnly] = useState(true)
  const [verifying, setVerifying] = useState<Rule | null>(null)
  const [deprecating, setDeprecating] = useState<Rule | null>(null)
  const [lastLoad, setLastLoad] = useState<RuleLoadResult | null>(null)

  const load = useMutation({
    mutationFn: () => post<RuleLoadResult>('/tax/rules/load-candidates'),
    onSuccess: (r) => {
      invalidate()
      setLastLoad(r)
      toast('ok', loadSummary(r))
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudieron cargar las reglas.')),
  })

  const all = rules.data ?? []
  const list = all.filter((r) => (!status || r.validation_status === status) && (!usedOnly || r.used_by_calculations))
  const pendingUsed = all.filter((r) => r.used_by_calculations && r.validation_status === 'pending').length

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="Estado">
            {(p) => (
              <Select {...p} className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Todos</option>
                <option value="pending">Sin verificar</option>
                <option value="verified">Verificadas</option>
                <option value="deprecated">Deprecadas</option>
              </Select>
            )}
          </Field>
          <div className="pb-2">
            <Check label="Solo las que usa la app" checked={usedOnly} onChange={setUsedOnly} />
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button variant="secondary" busy={load.isPending} disabled={!perms.canManage} onClick={() => load.mutate()}>
            <Download size={15} aria-hidden />
            Cargar reglas candidatas
          </Button>
          <ReadOnlyHint reason={perms.manageReason} />
        </div>
      </div>

      {pendingUsed > 0 && (
        <div className="mb-4">
          <Notice tone="warn" title={`${plural(pendingUsed, 'regla en uso está', 'reglas en uso están')} sin verificar`}>
            Lo que calcula la app con ellas lleva la marca «sin verificar». {perms.canVerify ? 'Revisá la norma y la fuente de cada una antes de verificarla.' : perms.verifyReason}
          </Notice>
        </div>
      )}
      {lastLoad && lastLoad.rejected.length > 0 && (
        <div className="mb-4">
          <Notice tone="bad" title={`${plural(lastLoad.rejected.length, 'regla rechazada', 'reglas rechazadas')} por parámetros inválidos`}>
            No se cargaron; revisá el archivo de reglas candidatas.
          </Notice>
        </div>
      )}

      <Sheet>
        {rules.isPending ? (
          <TableSkeleton rows={5} cols={3} />
        ) : rules.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={rules.error} />
          </div>
        ) : all.length === 0 ? (
          <EmptyState title="Todavía no hay reglas cargadas">
            Sin reglas no hay calendario ni cálculos. Cargá las candidatas de la investigación: nacen «sin verificar» y el contador las revisa una por una.
          </EmptyState>
        ) : list.length === 0 ? (
          <EmptyState title="Ninguna regla coincide con el filtro" />
        ) : (
          <ul className="divide-y divide-line" aria-label="Reglas">
            {list.map((r) => (
              <RuleRow key={r.id} rule={r} perms={perms} onVerify={() => setVerifying(r)} onDeprecate={() => setDeprecating(r)} />
            ))}
          </ul>
        )}
      </Sheet>

      <Modal open={verifying !== null} title={verifying ? `Verificar ${verifying.code} v${verifying.version}` : 'Verificar regla'} onClose={() => setVerifying(null)}>
        {verifying && (
          <VerifyForm
            intro={
              <>
                Confirmás que la regla coincide con la norma vigente ({verifying.legal_reference ?? 'sin referencia'}). Queda registrado tu nombre y matrícula; lo que calcule con ella deja de
                marcarse «sin verificar».
              </>
            }
            thirdLabel="Nota (opcional)"
            thirdHint="Por ejemplo, qué documento consultaste."
            thirdRequired={false}
            submit="Verificar regla"
            onCancel={() => setVerifying(null)}
            onSubmit={async ({ name, license, third }) => {
              await post(`/tax/rules/${verifying.id}/verify`, { reviewed_by_name: name, reviewed_reference: license, review_note: third || null })
              invalidate()
              setVerifying(null)
              toast('ok', `Regla ${verifying.code} verificada.`)
            }}
          />
        )}
      </Modal>

      <Modal open={deprecating !== null} title={deprecating ? `Deprecar ${deprecating.code} v${deprecating.version}` : 'Deprecar regla'} onClose={() => setDeprecating(null)}>
        {deprecating && (
          <ReasonForm
            intro={<p className="text-ink-2">Una regla deprecada deja de regir y no se puede reactivar. Lo ya presentado no cambia; lo pendiente se recalcula con la regla que la reemplace.</p>}
            submit="Deprecar"
            danger
            onCancel={() => setDeprecating(null)}
            onSubmit={async (reason) => {
              await post(`/tax/rules/${deprecating.id}/deprecate`, { reason })
              invalidate()
              setDeprecating(null)
              toast('ok', `Regla ${deprecating.code} deprecada.`)
            }}
          />
        )}
      </Modal>
    </>
  )
}

// --- Feriados ----------------------------------------------------------------------------

interface HolidayDraft {
  day: string
  name: string
  legal_reference: string
  source_url: string
  notes: string
}

const emptyHoliday: HolidayDraft = { day: '', name: '', legal_reference: '', source_url: '', notes: '' }

function HolidayForm({ initial, onSubmit, onCancel }: { initial: HolidayDraft; onSubmit: (d: HolidayDraft) => Promise<unknown>; onCancel: () => void }) {
  const [d, setD] = useState(initial)
  const [errors, setErrors] = useState<Partial<Record<keyof HolidayDraft, string>>>({})
  const run = useMutation({ mutationFn: onSubmit })
  const set = (k: keyof HolidayDraft) => (e: { target: { value: string } }) => setD({ ...d, [k]: e.target.value })
  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: typeof errors = {}
    if (!d.day) next.day = 'Elegí el día.'
    if (d.name.trim().length < 3) next.name = 'Escribí el nombre del feriado.'
    if (!d.legal_reference.trim() && !d.source_url.trim()) next.legal_reference = 'Indicá la norma o el enlace a la fuente (al menos uno).'
    setErrors(next)
    if (Object.keys(next).length === 0) run.mutate({ ...d, name: d.name.trim(), legal_reference: d.legal_reference.trim(), source_url: d.source_url.trim(), notes: d.notes.trim() })
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <div className="grid grid-cols-[12rem_minmax(0,1fr)] gap-4">
        <Field label="Día" error={errors.day}>
          {(p) => <Input {...p} type="date" autoFocus value={d.day} onChange={set('day')} />}
        </Field>
        <Field label="Nombre" error={errors.name}>
          {(p) => <Input {...p} maxLength={150} value={d.name} onChange={set('name')} />}
        </Field>
      </div>
      <Field label="Norma" error={errors.legal_reference} hint="Ley o decreto que lo establece o lo traslada.">
        {(p) => <Input {...p} maxLength={300} value={d.legal_reference} onChange={set('legal_reference')} />}
      </Field>
      <Field label="Enlace a la fuente">
        {(p) => <Input {...p} type="url" placeholder="https://" value={d.source_url} onChange={set('source_url')} />}
      </Field>
      <Field label="Notas">
        {(p) => <Textarea {...p} maxLength={500} value={d.notes} onChange={set('notes')} />}
      </Field>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          Guardar
        </Button>
      </div>
    </form>
  )
}

const holidayBody = (d: HolidayDraft) => ({
  day: d.day,
  name: d.name,
  legal_reference: d.legal_reference || null,
  source_url: d.source_url || null,
  notes: d.notes || null,
})

function HolidaysTab({ perms }: { perms: TaxPerms }) {
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const holidays = useHolidays()
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [editing, setEditing] = useState<Holiday | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Holiday | null>(null)

  const load = useMutation({
    mutationFn: () => post<{ created: number; unchanged: number; differing: unknown[] }>('/tax/holidays/load-candidates'),
    onSuccess: (r) => {
      invalidate()
      const extra = r.differing.length ? `, ${r.differing.length} distintos de los cargados (no se pisaron)` : ''
      toast('ok', `Feriados: ${plural(r.created, 'nuevo', 'nuevos')}, ${r.unchanged} sin cambios${extra}.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudieron cargar los feriados.')),
  })
  const verify = useMutation({
    mutationFn: (h: Holiday) => patch(`/tax/holidays/${h.id}`, { validation_status: 'verified' }),
    onSuccess: () => {
      invalidate()
      toast('ok', 'Feriado verificado.')
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo verificar el feriado.')),
  })
  const remove = useMutation({
    mutationFn: (h: Holiday) => api('DELETE', `/tax/holidays/${h.id}`),
    onSuccess: () => {
      invalidate()
      setDeleting(null)
      toast('ok', 'Feriado eliminado.')
    },
  })

  const all = holidays.data ?? []
  const years = [...new Set([year, ...all.map((h) => Number(h.day.slice(0, 4)))])].sort()
  const list = all.filter((h) => h.day.startsWith(String(year))).sort((a, b) => a.day.localeCompare(b.day))

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <Field label="Año">
          {(p) => (
            <Select {...p} className="w-32" value={year} onChange={(e) => setYear(Number(e.target.value))}>
              {years.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <div className="flex flex-col items-end gap-1">
          <div className="flex gap-2">
            <Button variant="secondary" busy={load.isPending} disabled={!perms.canManage} onClick={() => load.mutate()}>
              <Download size={15} aria-hidden />
              Cargar feriados candidatos
            </Button>
            <Button disabled={!perms.canManage} onClick={() => setEditing('new')}>
              <CalendarPlus size={15} aria-hidden />
              Agregar feriado
            </Button>
          </div>
          <ReadOnlyHint reason={perms.manageReason} />
        </div>
      </div>
      <p className="mb-4 max-w-[80ch] text-sm text-ink-2">
        Los feriados corren los vencimientos al día hábil siguiente. Si un feriado nacional corre o no un vencimiento de la DNIT es una duda abierta (D-F4-12): el calendario
        lo explica en cada obligación corrida.
      </p>
      <Sheet>
        {holidays.isPending ? (
          <TableSkeleton rows={5} cols={4} />
        ) : holidays.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={holidays.error} />
          </div>
        ) : list.length === 0 ? (
          <EmptyState title={`Sin feriados cargados en ${year}`}>Cargá los candidatos (Ley 7544/2025 y los traslados conocidos) o agregalos a mano con su fuente.</EmptyState>
        ) : (
          <table className="w-full text-base">
            <caption className="sr-only">Feriados de {year}</caption>
            <thead className="text-sm text-ink-2">
              <tr>
                <Th className="w-36">Día</Th>
                <Th>Feriado</Th>
                <Th>Norma</Th>
                <Th>Estado</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {list.map((h) => (
                <tr key={h.id} data-testid={`holiday-${h.day}`} className="border-t border-line align-top">
                  <td className="px-4 py-2.5 tabular-nums">{formatBookDate(h.day)}</td>
                  <td className="px-4 py-2.5">
                    {h.name}
                    {h.notes && <span className="block text-sm text-ink-2">{h.notes}</span>}
                  </td>
                  <td className="px-4 py-2.5 text-sm">
                    {h.legal_reference && <span className="block text-ink-2">{h.legal_reference}</span>}
                    <SourceLink url={h.source_url} />
                  </td>
                  <td className="px-4 py-2.5">
                    <RuleStatusBadge status={h.validation_status} />
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-1">
                      {perms.canVerify && h.validation_status === 'pending' && (
                        <Button variant="ghost" busy={verify.isPending && verify.variables?.id === h.id} onClick={() => verify.mutate(h)}>
                          <ShieldCheck size={15} aria-hidden />
                          Verificar
                        </Button>
                      )}
                      {perms.canManage && (
                        <>
                          <Button variant="ghost" className="px-2" aria-label={`Editar ${h.name}`} onClick={() => setEditing(h)}>
                            <Pencil size={15} aria-hidden />
                          </Button>
                          <Button variant="ghost" className="px-2" aria-label={`Eliminar ${h.name}`} onClick={() => setDeleting(h)}>
                            <Trash2 size={15} aria-hidden />
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Sheet>

      <Modal open={editing !== null} title={editing === 'new' ? 'Agregar feriado' : 'Editar feriado'} onClose={() => setEditing(null)}>
        {editing && (
          <HolidayForm
            initial={
              editing === 'new'
                ? emptyHoliday
                : { day: editing.day, name: editing.name, legal_reference: editing.legal_reference ?? '', source_url: editing.source_url ?? '', notes: editing.notes ?? '' }
            }
            onCancel={() => setEditing(null)}
            onSubmit={async (d) => {
              if (editing === 'new') await post('/tax/holidays', holidayBody(d))
              else await patch(`/tax/holidays/${editing.id}`, holidayBody(d))
              invalidate()
              setEditing(null)
              toast('ok', editing === 'new' ? 'Feriado agregado: queda sin verificar.' : 'Feriado actualizado.')
            }}
          />
        )}
      </Modal>

      <Modal open={deleting !== null} title="Eliminar feriado" onClose={() => setDeleting(null)}>
        {deleting && (
          <div className="flex flex-col gap-4">
            <p className="text-ink-2">
              ¿Eliminar «{deleting.name}» del {formatBookDate(deleting.day)}? Los vencimientos pendientes se recalculan sin él.
            </p>
            <ApiErrorNotice error={remove.error} />
            <div className="flex justify-end gap-2 border-t border-line pt-4">
              <Button variant="ghost" onClick={() => setDeleting(null)}>
                Cancelar
              </Button>
              <Button variant="danger" busy={remove.isPending} onClick={() => remove.mutate(deleting)}>
                Eliminar
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

// --- Excepciones de vencimiento ----------------------------------------------------------

const DETERMINATIVE = '__determinative'

function ExceptionForm({ onSubmit, onCancel }: { onSubmit: (body: Record<string, unknown>) => Promise<unknown>; onCancel: () => void }) {
  const [target, setTarget] = useState('IVA-GENERAL-LIQUIDACION')
  const [dueMonth, setDueMonth] = useState('')
  const [digits, setDigits] = useState<number[]>([])
  const [newDate, setNewDate] = useState('')
  const [reference, setReference] = useState('')
  const [source, setSource] = useState('')
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const run = useMutation({ mutationFn: onSubmit })
  const toggle = (n: number) => setDigits(digits.includes(n) ? digits.filter((x) => x !== n) : [...digits, n].sort())
  const send = (e: FormEvent) => {
    e.preventDefault()
    const next: Record<string, string> = {}
    if (!dueMonth) next.dueMonth = 'Elegí el mes del vencimiento que se mueve.'
    if (!newDate) next.newDate = 'Elegí la nueva fecha.'
    if (reference.trim().length < 3) next.reference = 'La norma es obligatoria (resolución de la DNIT que lo dispone).'
    setErrors(next)
    if (Object.keys(next).length > 0) return
    run.mutate({
      obligation_code: target === DETERMINATIVE ? null : target,
      obligation_group: target === DETERMINATIVE ? 'determinative' : null,
      due_month: `${dueMonth}-01`,
      ruc_digits: digits,
      new_due_date: newDate,
      legal_reference: reference.trim(),
      source_url: source.trim() || null,
      notes: notes.trim() || null,
    })
  }
  return (
    <form onSubmit={send} className="flex flex-col gap-4" noValidate>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Obligación">
          {(p) => (
            <Select {...p} autoFocus value={target} onChange={(e) => setTarget(e.target.value)}>
              {Object.entries(OBLIGATION_LABELS).map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
              <option value={DETERMINATIVE}>Todas las declaraciones determinativas</option>
            </Select>
          )}
        </Field>
        <Field label="Mes del vencimiento" error={errors.dueMonth}>
          {(p) => <Input {...p} type="month" value={dueMonth} onChange={(e) => setDueMonth(e.target.value)} />}
        </Field>
      </div>
      <fieldset>
        <legend className="text-sm font-medium text-ink-2">Terminación del RUC (ninguna marcada: todas)</legend>
        <div className="mt-1.5 flex flex-wrap gap-3">
          {Array.from({ length: 10 }, (_, n) => (
            <Check key={n} label={String(n)} checked={digits.includes(n)} onChange={() => toggle(n)} />
          ))}
        </div>
      </fieldset>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Nueva fecha de vencimiento" error={errors.newDate}>
          {(p) => <Input {...p} type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} />}
        </Field>
        <Field label="Norma" error={errors.reference}>
          {(p) => <Input {...p} maxLength={300} value={reference} onChange={(e) => setReference(e.target.value)} />}
        </Field>
      </div>
      <Field label="Enlace a la fuente">
        {(p) => <Input {...p} type="url" placeholder="https://" value={source} onChange={(e) => setSource(e.target.value)} />}
      </Field>
      <Field label="Notas">
        {(p) => <Textarea {...p} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />}
      </Field>
      <ApiErrorNotice error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          Guardar excepción
        </Button>
      </div>
    </form>
  )
}

function ExceptionsTab({ perms }: { perms: TaxPerms }) {
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const exceptions = useExceptions()
  const [creating, setCreating] = useState(false)
  const toggle = useMutation({
    mutationFn: (x: DueDateException) => patch(`/tax/due-date-exceptions/${x.id}`, { is_active: !x.is_active }),
    onSuccess: (_, x) => {
      invalidate()
      toast('ok', x.is_active ? 'Excepción desactivada: los vencimientos vuelven a la fecha normal.' : 'Excepción activada.')
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar la excepción.')),
  })
  const list = [...(exceptions.data ?? [])].sort((a, b) => b.due_month.localeCompare(a.due_month))

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <p className="max-w-[70ch] text-sm text-ink-2">
          Prórrogas que dispone la DNIT para un mes (por ejemplo, por un corte del sistema). Mueven el vencimiento de las obligaciones elegidas y quedan citadas en el calendario.
        </p>
        <div className="flex flex-col items-end gap-1">
          <Button disabled={!perms.canManage} onClick={() => setCreating(true)}>
            <CalendarPlus size={15} aria-hidden />
            Agregar excepción
          </Button>
          <ReadOnlyHint reason={perms.manageReason} />
        </div>
      </div>
      <Sheet>
        {exceptions.isPending ? (
          <TableSkeleton rows={3} cols={4} />
        ) : exceptions.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={exceptions.error} />
          </div>
        ) : list.length === 0 ? (
          <EmptyState title="Sin excepciones de vencimiento">Las que vienen en las reglas candidatas se crean al cargarlas.</EmptyState>
        ) : (
          <table className="w-full text-base">
            <caption className="sr-only">Excepciones de vencimiento</caption>
            <thead className="text-sm text-ink-2">
              <tr>
                <Th>Obligación</Th>
                <Th>Mes</Th>
                <Th>RUC terminados en</Th>
                <Th>Nueva fecha</Th>
                <Th>Norma</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {list.map((x) => (
                <tr key={x.id} className={cx('border-t border-line align-top', !x.is_active && 'text-ink-3')}>
                  <td className="px-4 py-2.5">
                    {x.obligation_code ? obligationLabel(x.obligation_code) : 'Declaraciones determinativas'}
                    {x.origin === 'candidate' && <span className="block text-sm text-ink-3">De una regla</span>}
                  </td>
                  <td className="px-4 py-2.5">{monthTitle(x.due_month.slice(0, 7))}</td>
                  <td className="px-4 py-2.5 tabular-nums">{x.ruc_digits.length ? x.ruc_digits.join(', ') : 'Todas'}</td>
                  <td className="px-4 py-2.5 tabular-nums">{formatBookDate(x.new_due_date)}</td>
                  <td className="px-4 py-2.5 text-sm">
                    <span className="block text-ink-2">{x.legal_reference}</span>
                    <SourceLink url={x.source_url} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {x.is_active ? <Badge tone="ok">Activa</Badge> : <Badge>Inactiva</Badge>}
                    {perms.canManage && (
                      <Button variant="ghost" className="ml-2" busy={toggle.isPending && toggle.variables?.id === x.id} onClick={() => toggle.mutate(x)}>
                        {x.is_active ? 'Desactivar' : 'Activar'}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Sheet>
      <Modal open={creating} title="Agregar excepción de vencimiento" size="lg" onClose={() => setCreating(false)}>
        {creating && (
          <ExceptionForm
            onCancel={() => setCreating(false)}
            onSubmit={async (body) => {
              await post('/tax/due-date-exceptions', body)
              invalidate()
              setCreating(false)
              toast('ok', 'Excepción agregada: el calendario se recalcula.')
            }}
          />
        )}
      </Modal>
    </>
  )
}

export function RulesPage() {
  const perms = useTaxPerms()
  const [params, setParams] = useSearchParams()
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id ?? 'reglas') as Tab

  return (
    <>
      <PageHeader
        title="Reglas y feriados"
        description="Las normas con las que la app arma el calendario y los cálculos. Todo nace sin verificar: el contador revisa cada una contra su fuente y la verifica con su nombre y matrícula."
      />
      <div role="tablist" aria-label="Secciones" className="mb-5 flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            aria-selected={tab === t.id}
            onClick={() => setParams(new URLSearchParams({ tab: t.id }), { replace: true })}
            className={cx(
              '-mb-px border-b-2 px-3 py-2 font-medium transition-colors',
              tab === t.id ? 'border-ledger text-ledger' : 'border-transparent text-ink-2 hover:text-ink',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label}>
        {tab === 'reglas' && <RulesTab perms={perms} />}
        {tab === 'feriados' && <HolidaysTab perms={perms} />}
        {tab === 'excepciones' && <ExceptionsTab perms={perms} />}
      </div>
    </>
  )
}
