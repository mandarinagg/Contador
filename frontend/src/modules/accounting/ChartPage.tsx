/**
 * Plan de cuentas: árbol por código, alta de subcuentas, edición, archivo, validación por un
 * CONTADOR AI (D-038, D-046, D-120) y la cuenta de resultados para la refundición (D-050).
 */
import { useMutation } from '@tanstack/react-query'
import { Archive, ArchiveRestore, ChevronDown, ChevronRight, ListTree, Pencil, Plus, Search, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react'
import { type FormEvent, useDeferredValue, useMemo, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime, plural } from '../../lib/format'
import { ApiError, patch, post, put } from '../../services/api'
import { ApiErrorNotice, Check, ReadOnlyHint, TableSkeleton, Th } from '../finance/components'
import { errorMessage } from '../finance/forms'
import { buildTree, flatten, idsToDepth, suggestChildSegment, type TreeNode, visibleRows } from './chartTree'
import { LedgerAccountSelect } from './components'
import { type AccountingPerms, useAccountingPerms, useChart, useInvalidateAccounting } from './data'
import { BALANCE_KINDS, DEFAULT_SIDE, KIND_LABELS, ORIGIN_HINTS, ORIGIN_LABELS, RESULT_KINDS, SIDE_LABELS } from './labels'
import type { AccountingSettings, Chart, LedgerAccount, LedgerKind, NormalSide } from './types'

type Dialog =
  | { kind: 'new'; parent: LedgerAccount | null }
  | { kind: 'edit'; account: LedgerAccount }
  | { kind: 'archive'; account: LedgerAccount }
  | { kind: 'validate' }
  | { kind: 'invalidate' }

// --- Estado del plan ----------------------------------------------------------------------

function StatusPanel({ chart, perms, onValidate, onInvalidate }: { chart: Chart; perms: AccountingPerms; onValidate: () => void; onInvalidate: () => void }) {
  const validated = chart.chart_status === 'validated'
  return (
    <Sheet className={cx('flex flex-col gap-3 border-l-4 p-5', validated ? 'border-l-ledger' : 'border-l-amber')}>
      <div className="flex items-start gap-3">
        {validated ? <ShieldCheck size={22} className="mt-0.5 shrink-0 text-ledger" aria-hidden /> : <ShieldAlert size={22} className="mt-0.5 shrink-0 text-amber" aria-hidden />}
        <div className="min-w-0">
          <h2 className="text-md font-semibold">{validated ? 'Plan de cuentas validado' : 'Plan de cuentas sin verificar contra la fuente oficial'}</h2>
          {validated ? (
            <p className="mt-1 text-ink-2">
              Lo validó <span className="font-medium text-ink">{chart.chart_validated_by_name}</span> contra{' '}
              <span className="font-medium text-ink">{chart.chart_validated_reference}</span>, el {formatDateTime(chart.chart_validated_at as string)}. Si
              se agrega una cuenta o se cambia un código, un tipo o una naturaleza, vuelve a quedar sin validar.
            </p>
          ) : (
            <p className="mt-1 max-w-[68ch] text-ink-2">
              Es una propuesta basada en el modelo de la RG N° 49/2014 de la DNIT. Hasta que la valides (la verifica CONTADOR AI contra ese modelo), todos
              los reportes lo advierten.
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 pl-8.5">
        {perms.canPost ? (
          validated ? (
            <Button variant="secondary" onClick={onInvalidate}>
              Volver a «sin validar»
            </Button>
          ) : (
            <Button onClick={onValidate}>
              <ShieldCheck size={16} />
              Marcar como validado
            </Button>
          )
        ) : (
          <ReadOnlyHint reason={validated ? '' : 'Lo marca como validado un usuario con permiso para contabilizar, como el propietario.'} />
        )}
      </div>
    </Sheet>
  )
}

function RetainedEarnings({ chart, perms }: { chart: Chart; perms: AccountingPerms }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [value, setValue] = useState(chart.retained_earnings_account_id ?? '')
  const save = useMutation({
    mutationFn: () => put<AccountingSettings>('/accounting/settings', { retained_earnings_account_id: value || null }),
    onSuccess: () => {
      invalidate()
      toast('ok', value ? 'Cuenta de resultados del ejercicio guardada.' : 'Cuenta de resultados del ejercicio quitada.')
    },
  })
  const current = chart.accounts.find((a) => a.id === chart.retained_earnings_account_id)
  return (
    <Sheet className="flex flex-col gap-3 p-5">
      <div>
        <h2 className="font-semibold">Cuenta de resultados del ejercicio</h2>
        <p className="mt-1 text-sm text-ink-2">Al cerrar el ejercicio, la refundición lleva el resultado a esta cuenta de patrimonio.</p>
      </div>
      {perms.canPost ? (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <LedgerAccountSelect aria-label="Cuenta de resultados del ejercicio" accounts={chart.accounts} kinds={['equity']} value={value} onChange={setValue} empty="Sin configurar" />
          {save.error ? <ApiErrorNotice error={save.error} /> : null}
          <div>
            <Button type="submit" variant="secondary" busy={save.isPending} disabled={value === (chart.retained_earnings_account_id ?? '')}>
              Guardar
            </Button>
          </div>
        </form>
      ) : (
        <p className={cx('text-sm', current ? 'text-ink' : 'text-ink-3')}>
          {current ? `${current.code} ${current.name}` : 'Sin configurar. La configura el propietario o el contador.'}
        </p>
      )}
    </Sheet>
  )
}

// --- Formulario de cuenta -------------------------------------------------------------------

function AccountForm({ chart, parent, account, onDone }: { chart: Chart; parent: LedgerAccount | null; account?: LedgerAccount; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const parentAccount = account ? chart.accounts.find((a) => a.id === account.parent_id) ?? null : parent
  const prefix = parentAccount ? `${parentAccount.code}.` : ''
  const siblings = chart.accounts.filter((a) => a.parent_id === (parentAccount?.id ?? null))
  const [segment, setSegment] = useState(account ? (account.code.split('.').at(-1) ?? '') : suggestChildSegment(parentAccount?.code ?? null, siblings.map((s) => s.code)))
  const [name, setName] = useState(account?.name ?? '')
  const [note, setNote] = useState(account?.note ?? '')
  const [postable, setPostable] = useState(account?.is_postable ?? true)
  const [kind, setKind] = useState<LedgerKind>(account?.kind ?? parentAccount?.kind ?? 'asset')
  const [side, setSide] = useState<NormalSide>(account?.normal_side ?? (parentAccount ? parentAccount.normal_side : DEFAULT_SIDE[kind]))
  const locked = Boolean(account?.in_use)
  // El tipo de una subcuenta no cruza de estado: patrimonial con patrimonial, resultados con resultados.
  const kinds: LedgerKind[] = parentAccount ? (BALANCE_KINDS.includes(parentAccount.kind) ? BALANCE_KINDS : RESULT_KINDS) : [...BALANCE_KINDS, ...RESULT_KINDS]
  const code = `${prefix}${segment.trim()}`
  const segmentInvalid = !/^\d+$/.test(segment.trim())

  const save = useMutation({
    mutationFn: () => {
      if (!account) {
        return post<LedgerAccount>('/accounting/chart/accounts', {
          parent_id: parentAccount?.id ?? null,
          code,
          name: name.trim(),
          is_postable: postable,
          kind,
          normal_side: side,
          note: note.trim() || null,
        })
      }
      const body: Record<string, unknown> = {}
      if (name.trim() !== account.name) body.name = name.trim()
      if ((note.trim() || null) !== account.note) body.note = note.trim() || null
      if (!locked) {
        if (code !== account.code) body.code = code
        if (kind !== account.kind) body.kind = kind
        if (side !== account.normal_side) body.normal_side = side
        if (postable !== account.is_postable) body.is_postable = postable
      }
      return patch<LedgerAccount>(`/accounting/chart/accounts/${account.id}`, body)
    },
    onSuccess: (a) => {
      invalidate()
      toast('ok', account ? `Cuenta ${a.code} guardada.` : `Cuenta ${a.code} ${a.name} creada.`)
      onDone()
    },
  })
  const error = save.error instanceof ApiError ? save.error : null
  const fe = error?.fieldErrors() ?? {}
  const [touched, setTouched] = useState(false)

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (segmentInvalid || name.trim().length < 2) return
    save.mutate()
  }
  const structural = !account || (!locked && (code !== account.code || kind !== account.kind || side !== account.normal_side || postable !== account.is_postable))

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-2 gap-x-4 gap-y-4" noValidate>
      {error && (
        <div className="col-span-2">
          <Notice tone="bad" title={error.message}>
            {Object.values(fe).length > 0 ? Object.values(fe).join(' ') : null}
          </Notice>
        </div>
      )}
      <div className="col-span-2 rounded-sm bg-sunken px-3 py-2 text-sm text-ink-2">
        {parentAccount ? (
          <>
            Dentro de <span className="font-medium text-ink tabular-nums">{parentAccount.code}</span> <span className="font-medium text-ink">{parentAccount.name}</span>
          </>
        ) : (
          'Cuenta de primer nivel (sin cuenta superior).'
        )}
      </div>
      <Field label="Código" error={touched && segmentInvalid ? 'El último segmento lleva solo números.' : fe.code} hint={locked ? 'Fijo: la cuenta ya tiene asientos.' : 'El de la cuenta superior más un segmento.'}>
        {(p) => (
          <div className="flex items-center rounded-sm border border-line-strong bg-surface focus-within:outline-2 focus-within:outline-(--focus)">
            {prefix && <span className="pl-3 text-ink-2 tabular-nums">{prefix}</span>}
            <input
              {...p}
              inputMode="numeric"
              disabled={locked}
              value={segment}
              onChange={(e) => setSegment(e.target.value.replace(/[^\d]/g, ''))}
              className={cx('h-9 min-w-0 flex-1 bg-transparent pr-3 tabular-nums outline-none disabled:text-ink-3', prefix ? 'pl-0.5' : 'pl-3')}
            />
          </div>
        )}
      </Field>
      <fieldset className="flex flex-col gap-1.5" disabled={locked}>
        <legend className="mb-1.5 text-sm font-medium text-ink-2">Clase</legend>
        <div className="flex flex-col gap-1.5">
          {(
            [
              [true, 'Imputable', 'recibe asientos'],
              [false, 'Agrupadora', 'suma sus subcuentas'],
            ] as const
          ).map(([v, label, hint]) => (
            <label key={label} className={cx('flex items-center gap-2', locked ? 'text-ink-3' : 'cursor-pointer')}>
              <input type="radio" name="postable" className="accent-(--ledger)" checked={postable === v} onChange={() => setPostable(v)} />
              {label} <span className="text-sm text-ink-3">({hint})</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="col-span-2">
        <Field label="Nombre" error={touched && name.trim().length < 2 ? 'Escribí el nombre (al menos 2 caracteres).' : fe.name}>
          {(p) => <Input {...p} autoFocus maxLength={150} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
      </div>
      <Field label="Tipo" hint={parentAccount && !locked ? 'Del mismo estado que la cuenta superior.' : undefined}>
        {(p) => (
          <Select
            {...p}
            disabled={locked}
            value={kind}
            onChange={(e) => {
              const k = e.target.value as LedgerKind
              setKind(k)
              setSide(DEFAULT_SIDE[k])
            }}
          >
            {kinds.map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Naturaleza" hint="Una regularizadora, como «(-) Depreciación acumulada», lleva la contraria a su tipo.">
        {(p) => (
          <Select {...p} disabled={locked} value={side} onChange={(e) => setSide(e.target.value as NormalSide)}>
            <option value="debit">Deudora</option>
            <option value="credit">Acreedora</option>
          </Select>
        )}
      </Field>
      <div className="col-span-2">
        <Field label="Nota" hint="Opcional: para qué se usa, qué incluye." error={fe.note}>
          {(p) => <Textarea {...p} maxLength={500} className="min-h-16" value={note} onChange={(e) => setNote(e.target.value)} />}
        </Field>
      </div>
      {locked && (
        <p className="col-span-2 rounded-sm bg-sunken px-3 py-2 text-sm text-ink-2">
          La cuenta ya tiene asientos: el código, el tipo, la naturaleza y la clase no se cambian (BR-ACC-09). Podés corregir el nombre y la nota, o
          archivarla y crear otra.
        </p>
      )}
      {structural && chart.chart_status === 'validated' && (
        <div className="col-span-2">
          <Notice tone="warn" title="El plan va a volver a «sin validar»">
            Un cambio en la estructura del plan necesita validarlo de nuevo.
          </Notice>
        </div>
      )}
      <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {account ? 'Guardar cambios' : 'Crear cuenta'}
        </Button>
      </div>
    </form>
  )
}

function ArchiveForm({ account, chart, onDone }: { account: LedgerAccount; chart: Chart; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const archiving = !account.archived_at
  const run = useMutation({
    mutationFn: () => patch<LedgerAccount>(`/accounting/chart/accounts/${account.id}`, { archived: archiving }),
    onSuccess: (a) => {
      invalidate()
      toast('ok', archiving ? `Cuenta ${a.code} archivada.` : `Cuenta ${a.code} desarchivada.`)
      onDone()
    },
  })
  return (
    <div className="flex flex-col gap-4">
      <p className="font-medium">
        <span className="mr-2 text-ink-2 tabular-nums">{account.code}</span>
        {account.name}
      </p>
      <p className="text-ink-2">
        {archiving
          ? 'Una cuenta archivada deja de ofrecerse para nuevos asientos, pero conserva su historia en los libros. No se archiva si tiene saldo, subcuentas sin archivar, borradores que la usan o si está configurada en finanzas o como cuenta de resultados.'
          : 'Vuelve a ofrecerse para nuevos asientos.'}
        {chart.chart_status === 'validated' && ' El plan va a volver a «sin validar».'}
      </p>
      {run.error ? <ApiErrorNotice error={run.error} title={archiving ? 'No se puede archivar' : 'No se puede desarchivar'} /> : null}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button variant={archiving ? 'danger' : 'primary'} busy={run.isPending} onClick={() => run.mutate()}>
          {archiving ? 'Archivar cuenta' : 'Desarchivar cuenta'}
        </Button>
      </div>
    </div>
  )
}

/** D-124: qué cuentas no respetan el modelo de la RG 49/2014, si CONTADOR AI rechazó la validación. */
function ChartProblems({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || error.code !== 'CHART_NOT_VERIFIABLE') return null
  const details = error.details as { problems?: string[]; count?: number } | undefined
  const problems = details?.problems ?? []
  if (problems.length === 0) return null
  return (
    <div className="text-sm">
      <ul className="list-disc pl-5 text-ink-2" aria-label="Cuentas que no respetan el modelo">
        {problems.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
      {details?.count !== undefined && details.count > problems.length && <p className="mt-1 text-ink-3">Y {details.count - problems.length} más.</p>}
    </div>
  )
}

function ValidateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const run = useMutation({
    mutationFn: () => post<AccountingSettings>('/accounting/chart/validate'),
    onSuccess: () => {
      invalidate()
      toast('ok', 'Plan de cuentas marcado como validado.')
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        run.mutate()
      }}
    >
      <p className="text-ink-2">
        CONTADOR AI lo valida contra el modelo de estados financieros de la RG N° 49/2014 de la DNIT: cada código del modelo con su nombre oficial y cada cuenta
        propia colgando de una del modelo. Tu aprobación queda en la auditoría, y los reportes dejan de mostrar el aviso de «sin validar».
      </p>
      <ApiErrorNotice error={run.error} />
      <ChartProblems error={run.error} />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          Marcar como validado
        </Button>
      </div>
    </form>
  )
}

function InvalidateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const run = useMutation({
    mutationFn: () => post<AccountingSettings>('/accounting/chart/invalidate'),
    onSuccess: () => {
      invalidate()
      toast('ok', 'El plan de cuentas volvió a «sin validar».')
      onDone()
    },
  })
  return (
    <div className="flex flex-col gap-4">
      <p className="text-ink-2">Se borra la constancia de validación y los reportes vuelven a mostrar el aviso. Usalo si el plan cambió o si la validación se cargó por error.</p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button variant="danger" busy={run.isPending} onClick={() => run.mutate()}>
          Volver a «sin validar»
        </Button>
      </div>
    </div>
  )
}

// --- Árbol --------------------------------------------------------------------------------

function TreeRow({
  node,
  expanded,
  hasChildren,
  match,
  canManage,
  onToggle,
  onDialog,
}: {
  node: TreeNode
  expanded: boolean
  hasChildren: boolean
  match: boolean
  canManage: boolean
  onToggle: () => void
  onDialog: (d: Dialog) => void
}) {
  const a = node.account
  const archived = Boolean(a.archived_at)
  return (
    <tr className={cx('group align-top', archived && 'text-ink-3', match && 'bg-ledger-soft/60')}>
      <td className={cx('py-1.5 pr-2 pl-4 align-top tabular-nums', archived ? 'text-ink-3' : 'text-ink-2', !a.is_postable && 'font-medium')}>
        <span className="block leading-6">{a.code}</span>
      </td>
      <td className="py-1.5 pr-3">
        <div className="flex items-start gap-1" style={{ paddingLeft: `${node.depth * 1.25}rem` }}>
          {hasChildren ? (
            <button
              type="button"
              onClick={onToggle}
              aria-expanded={expanded}
              aria-label={`${expanded ? 'Contraer' : 'Expandir'} ${a.code} ${a.name}`}
              className="grid size-6 shrink-0 place-items-center rounded-sm text-ink-2 hover:bg-sunken hover:text-ink"
            >
              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
          ) : (
            <span className="size-6 shrink-0" aria-hidden />
          )}
          <div className="min-w-0 leading-6">
            <span className={cx(!a.is_postable && 'font-semibold', archived && 'line-through decoration-1')}>{a.name}</span>
            {archived && (
              <span className="ml-2">
                <Badge>Archivada</Badge>
              </span>
            )}
            {a.note && <p className="mt-0.5 text-sm text-ink-2">{a.note}</p>}
          </div>
        </div>
      </td>
      <td className="px-3 py-1.5 text-sm leading-6 text-ink-2">
        {KIND_LABELS[a.kind]}, <span className={cx(a.normal_side !== DEFAULT_SIDE[a.kind] && 'font-medium text-ink')}>{SIDE_LABELS[a.normal_side].toLowerCase()}</span>
      </td>
      <td className="px-3 py-1.5 text-sm leading-6">{a.is_postable ? <span className="text-ink">Imputable</span> : <span className="text-ink-2">Agrupadora</span>}</td>
      <td className="px-3 py-1.5 text-sm leading-6 text-ink-2" title={ORIGIN_HINTS[a.origin]}>
        {ORIGIN_LABELS[a.origin]}
      </td>
      {canManage && (
        <td className="py-1 pr-2">
          <div className="flex justify-end gap-0.5 opacity-70 group-focus-within:opacity-100 group-hover:opacity-100">
            {!a.is_postable && !archived && (
              <Button variant="ghost" className="h-7 px-1.5" aria-label={`Agregar subcuenta a ${a.code} ${a.name}`} title="Agregar subcuenta" onClick={() => onDialog({ kind: 'new', parent: a })}>
                <Plus size={15} />
              </Button>
            )}
            <Button variant="ghost" className="h-7 px-1.5" aria-label={`Editar ${a.code} ${a.name}`} title="Editar" onClick={() => onDialog({ kind: 'edit', account: a })}>
              <Pencil size={14} />
            </Button>
            <Button
              variant="ghost"
              className="h-7 px-1.5"
              aria-label={`${archived ? 'Desarchivar' : 'Archivar'} ${a.code} ${a.name}`}
              title={archived ? 'Desarchivar' : 'Archivar'}
              onClick={() => onDialog({ kind: 'archive', account: a })}
            >
              {archived ? <ArchiveRestore size={14} /> : <Archive size={14} />}
            </Button>
          </div>
        </td>
      )}
    </tr>
  )
}

export function ChartPage() {
  const chart = useChart()
  const perms = useAccountingPerms()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [search, setSearch] = useState('')
  const query = useDeferredValue(search)
  const [hideArchived, setHideArchived] = useState(false)
  const [expandedState, setExpanded] = useState<Set<string> | null>(null)
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const roots = useMemo(() => buildTree(chart.data?.accounts ?? []), [chart.data])
  const expanded = useMemo(() => expandedState ?? idsToDepth(roots, 2), [expandedState, roots])
  const rows = visibleRows(roots, expanded, { query, hideArchived })

  const load = useMutation({
    mutationFn: () => post<LedgerAccount[]>('/accounting/chart/load-proposed'),
    onSuccess: (list) => {
      invalidate()
      toast('ok', `Plan propuesto cargado: ${plural(list.length, 'cuenta', 'cuentas')}, sin validar.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cargar el plan propuesto.')),
  })

  const toggle = (id: string) => {
    const next = new Set(expanded)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setExpanded(next)
  }
  const close = () => setDialog(null)
  const data = chart.data
  const accounts = data?.accounts ?? []
  const archivedCount = accounts.filter((a) => a.archived_at).length
  const postableCount = accounts.filter((a) => a.is_postable && !a.archived_at).length

  return (
    <>
      <PageHeader
        title="Plan de cuentas"
        description="Las cuentas de la contabilidad, por código. Solo las imputables reciben asientos; las agrupadoras suman sus subcuentas en los balances."
        actions={
          perms.canManage &&
          accounts.length > 0 && (
            <Button variant="secondary" onClick={() => setDialog({ kind: 'new', parent: null })}>
              <Plus size={16} />
              Cuenta de primer nivel
            </Button>
          )
        }
      />

      {chart.isPending ? (
        <Sheet>
          <TableSkeleton rows={8} cols={4} />
        </Sheet>
      ) : chart.isError || !data ? (
        <ApiErrorNotice error={chart.error} title="No se pudo cargar el plan de cuentas." />
      ) : accounts.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay plan de cuentas"
            action={
              perms.canManage ? (
                <div className="flex flex-wrap gap-2">
                  <Button busy={load.isPending} onClick={() => load.mutate()}>
                    <Sparkles size={16} />
                    Cargar el plan propuesto
                  </Button>
                  <Button variant="secondary" onClick={() => setDialog({ kind: 'new', parent: null })}>
                    <Plus size={16} />
                    Empezar uno a mano
                  </Button>
                </div>
              ) : (
                <ReadOnlyHint reason={perms.manageReason} />
              )
            }
          >
            El plan propuesto tiene 173 cuentas con los códigos y nombres del modelo de estados financieros de la RG N° 49/2014 de la DNIT, más
            algunas subcuentas habituales. Es una propuesta: queda «sin validar» hasta que la valides. Después podés agregar, renombrar o
            archivar cuentas.
          </EmptyState>
        </Sheet>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] items-start gap-5">
            <StatusPanel chart={data} perms={perms} onValidate={() => setDialog({ kind: 'validate' })} onInvalidate={() => setDialog({ kind: 'invalidate' })} />
            <RetainedEarnings key={data.retained_earnings_account_id ?? 'none'} chart={data} perms={perms} />
          </div>
          {!perms.canManage && <p className="mb-3 text-sm text-ink-3">{perms.manageReason}</p>}

          <Sheet>
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
              <div className="relative w-80">
                <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
                <Input type="search" aria-label="Buscar cuenta" placeholder="Buscar por código o nombre" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <Button variant="ghost" disabled={query !== ''} onClick={() => setExpanded(new Set(flatten(roots).filter((n) => n.children.length).map((n) => n.account.id)))}>
                <ListTree size={15} />
                Expandir todo
              </Button>
              <Button variant="ghost" disabled={query !== ''} onClick={() => setExpanded(new Set())}>
                Contraer todo
              </Button>
              {archivedCount > 0 && <Check label={`Ocultar archivadas (${archivedCount})`} checked={hideArchived} onChange={setHideArchived} />}
              <span className="ml-auto text-sm text-ink-3">
                {plural(accounts.length, 'cuenta', 'cuentas')}, {postableCount} imputables
              </span>
            </div>
            {rows.length === 0 ? (
              <EmptyState title="Ninguna cuenta coincide">Probá con el comienzo del código (1.01) o con parte del nombre, sin importar tildes.</EmptyState>
            ) : (
              <table className="w-full">
                <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                  <tr>
                    <Th className="w-36">Código</Th>
                    <Th className="pl-10">Cuenta</Th>
                    <Th className="w-40 px-3">Tipo y naturaleza</Th>
                    <Th className="w-28 px-3">Clase</Th>
                    <Th className="w-28 px-3">Origen</Th>
                    {perms.canManage && (
                      <Th className="w-28">
                        <span className="sr-only">Acciones</span>
                      </Th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((r) => (
                    <TreeRow
                      key={r.node.account.id}
                      {...r}
                      canManage={perms.canManage}
                      onToggle={() => toggle(r.node.account.id)}
                      onDialog={setDialog}
                    />
                  ))}
                </tbody>
              </table>
            )}
          </Sheet>
        </>
      )}

      <Modal
        open={dialog?.kind === 'new' || dialog?.kind === 'edit'}
        size="lg"
        title={dialog?.kind === 'edit' ? `Editar cuenta ${dialog.account.code}` : dialog?.kind === 'new' && dialog.parent ? 'Nueva subcuenta' : 'Nueva cuenta'}
        onClose={close}
      >
        {data && dialog?.kind === 'new' && <AccountForm chart={data} parent={dialog.parent} onDone={close} />}
        {data && dialog?.kind === 'edit' && <AccountForm key={dialog.account.id} chart={data} parent={null} account={dialog.account} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'archive'} title={dialog?.kind === 'archive' && dialog.account.archived_at ? 'Desarchivar cuenta' : 'Archivar cuenta'} onClose={close}>
        {data && dialog?.kind === 'archive' && <ArchiveForm account={dialog.account} chart={data} onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'validate'} title="Marcar el plan como validado" onClose={close}>
        {dialog?.kind === 'validate' && <ValidateForm onDone={close} />}
      </Modal>
      <Modal open={dialog?.kind === 'invalidate'} title="Volver el plan a «sin validar»" onClose={close}>
        {dialog?.kind === 'invalidate' && <InvalidateForm onDone={close} />}
      </Modal>
    </>
  )
}
