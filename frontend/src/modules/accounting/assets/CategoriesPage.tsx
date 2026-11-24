/**
 * Categorías de activo fijo (D-056, D-068): las 34 candidatas del Decreto 3182/2019, art. 31
 * (redacción del Decreto 6105/2021), sin validar; completarlas, validarlas (accounting.post) y
 * archivarlas. Más la configuración de los bienes: inicio por defecto y cuenta de bajas.
 */
import { useMutation } from '@tanstack/react-query'
import { Archive, ArchiveRestore, BadgeCheck, ChevronDown, ChevronRight, ExternalLink, Pencil, Plus, Search, Sparkles } from 'lucide-react'
import { Fragment, useDeferredValue, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, Sheet, Textarea } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { cx } from '../../../lib/cx'
import { formatDateTime } from '../../../lib/format'
import { patch, post, put } from '../../../services/api'
import { ApiErrorNotice, Check, TableSkeleton, Th } from '../../finance/components'
import { errorMessage } from '../../finance/forms'
import { fold } from '../chartTree'
import { LedgerAccountSelect } from '../components'
import { useAccountingPerms, useAccountingSettings, useAccountsById, useAssetCategories, useChart, useInvalidateAccounting } from '../data'
import { monthsText, percentText, START_RULE_LABELS } from '../labels'
import type { AccountingSettings, LedgerAccount, StartRule } from '../types'
import type { AssetCategory, AssetCategoryIn } from '../types3b'
import { parseMonths, parseRate } from './assetForm'

/** Cuentas que admite cada rol de la categoría (las mismas reglas que la API, INVALID_CATEGORY_ACCOUNT). */
const accountsFor = (accounts: LedgerAccount[], role: 'asset' | 'accumulated' | 'expense') =>
  accounts.filter((a) =>
    role === 'asset' ? a.kind === 'asset' && a.normal_side === 'debit' : role === 'accumulated' ? a.kind === 'asset' && a.normal_side === 'credit' : a.kind === 'expense',
  )

function CategoryForm({ category, onDone }: { category?: AssetCategory; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const chart = useChart()
  const accounts = chart.data?.accounts ?? []
  const [name, setName] = useState(category?.name ?? '')
  const [life, setLife] = useState(category?.useful_life_months ? String(category.useful_life_months) : '')
  const [rate, setRate] = useState((category?.residual_rate ?? '').replace('.', ','))
  const [assetAcc, setAssetAcc] = useState(category?.asset_account_id ?? '')
  const [accum, setAccum] = useState(category?.accumulated_account_id ?? '')
  const [expense, setExpense] = useState(category?.expense_account_id ?? '')
  const [note, setNote] = useState(category?.note ?? '')
  const [touched, setTouched] = useState(false)
  // Vida útil y residual pueden quedar vacíos (la categoría queda incompleta, no se usa).
  const lifeP = life.trim() ? parseMonths(life) : null
  const rateP = rate.trim() ? parseRate(rate) : null
  const errors = {
    name: name.trim().length < 2 ? 'Escribí el nombre (al menos 2 caracteres).' : undefined,
    life: lifeP && !lifeP.ok ? lifeP.error : undefined,
    rate: rateP && !rateP.ok ? rateP.error : undefined,
  }
  const structural =
    category &&
    (String(category.useful_life_months ?? '') !== life.trim() ||
      (category.residual_rate ?? '') !== (rateP?.ok ? rateP.value : rate.trim() ? '?' : '') ||
      (category.asset_account_id ?? '') !== assetAcc ||
      (category.accumulated_account_id ?? '') !== accum ||
      (category.expense_account_id ?? '') !== expense)
  const save = useMutation({
    mutationFn: () => {
      const body: AssetCategoryIn = {
        name: name.trim(),
        useful_life_months: lifeP?.ok ? lifeP.value : null,
        residual_rate: rateP?.ok ? rateP.value : null,
        asset_account_id: assetAcc || null,
        accumulated_account_id: accum || null,
        expense_account_id: expense || null,
        note: note.trim() || null,
      }
      return category ? patch<AssetCategory>(`/accounting/asset-categories/${category.id}`, body) : post<AssetCategory>('/accounting/asset-categories', body)
    },
    onSuccess: (c) => {
      invalidate()
      toast('ok', c.complete ? `Categoría «${c.name}» guardada: lista para usar.` : `Categoría «${c.name}» guardada. Todavía le falta: ${c.missing.join(', ')}.`)
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        setTouched(true)
        if (!errors.name && !errors.life && !errors.rate) save.mutate()
      }}
    >
      {category?.citation && (
        <blockquote className="border-l-2 border-line-strong pl-3 text-sm text-ink-2">
          «{category.citation}»<span className="mt-0.5 block text-ink-3">{category.legal_reference}</span>
        </blockquote>
      )}
      {save.error ? <ApiErrorNotice error={save.error} /> : null}
      <Field label="Nombre" error={touched ? errors.name : undefined}>
        {(p) => <Input {...p} maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Vida útil (meses)" error={touched ? errors.life : undefined} hint={lifeP?.ok ? monthsText(lifeP.value) : 'Vacía: la categoría no se usa (por ejemplo, terrenos).'}>
          {(p) => <Input {...p} inputMode="numeric" className="tabular-nums" value={life} onChange={(e) => setLife(e.target.value)} />}
        </Field>
        <Field label="Valor residual (% del costo)" error={touched ? errors.rate : undefined} hint="De 0 a 20 % (Ley 6380, art. 11). 0 si no tiene.">
          {(p) => <Input {...p} inputMode="decimal" className="tabular-nums" value={rate} onChange={(e) => setRate(e.target.value)} />}
        </Field>
      </div>
      <Field label="Cuenta del bien" hint="De activo, deudora (por ejemplo 1.02.04.05.01).">
        {(p) => <LedgerAccountSelect {...p} accounts={accountsFor(accounts, 'asset')} kinds={['asset']} value={assetAcc} onChange={setAssetAcc} empty="Sin cuenta" />}
      </Field>
      <Field label="Cuenta de depreciación acumulada" hint="De activo, acreedora (regularizadora, «(-) Depreciación acumulada…»).">
        {(p) => <LedgerAccountSelect {...p} accounts={accountsFor(accounts, 'accumulated')} kinds={['asset']} value={accum} onChange={setAccum} empty="Sin cuenta" />}
      </Field>
      <Field label="Cuenta de gasto" hint="De gasto (por ejemplo 15.01 Depreciaciones del ejercicio).">
        {(p) => <LedgerAccountSelect {...p} accounts={accountsFor(accounts, 'expense')} kinds={['expense']} value={expense} onChange={setExpense} empty="Sin cuenta" />}
      </Field>
      <Field label="Nota" hint="Opcional: qué bienes incluye o qué decidió el contador.">
        {(p) => <Textarea {...p} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />}
      </Field>
      {category?.validation_status === 'validated' && structural && (
        <Notice tone="warn" title="La categoría va a volver a «sin validar»">
          Cambiar la vida útil, el residual o las cuentas de una categoría validada la devuelve a pendiente: la tiene que validar de nuevo un contador.
        </Notice>
      )}
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {category ? 'Guardar' : 'Crear categoría'}
        </Button>
      </div>
    </form>
  )
}

function ValidateForm({ category, onDone }: { category: AssetCategory; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [name, setName] = useState('')
  const [ref, setRef] = useState('')
  const [touched, setTouched] = useState(false)
  const nameBad = name.trim().length < 3
  const refBad = ref.trim().length < 2
  const run = useMutation({
    mutationFn: () => post<AssetCategory>(`/accounting/asset-categories/${category.id}/validate`, { validated_by_name: name.trim(), validated_reference: ref.trim() }),
    onSuccess: (c) => {
      invalidate()
      toast('ok', `Categoría «${c.name}» validada.`)
      onDone()
    },
  })
  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault()
        setTouched(true)
        if (!nameBad && !refBad) run.mutate()
      }}
    >
      <p className="text-ink-2">
        Validar dice que un contador revisó la vida útil ({category.useful_life_months ? monthsText(category.useful_life_months) : '—'}), el residual (
        {percentText(category.residual_rate)}) y las cuentas de «{category.name}» para esta empresa. Queda registrado con su nombre y matrícula.
      </p>
      {run.error ? <ApiErrorNotice error={run.error} /> : null}
      <Field label="Nombre del contador" error={touched && nameBad ? 'Escribí nombre y apellido.' : undefined}>
        {(p) => <Input {...p} autoFocus maxLength={150} value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Matrícula profesional" error={touched && refBad ? 'Escribí la matrícula.' : undefined}>
        {(p) => <Input {...p} maxLength={100} value={ref} onChange={(e) => setRef(e.target.value)} />}
      </Field>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={run.isPending}>
          <BadgeCheck size={15} />
          Validar la categoría
        </Button>
      </div>
    </form>
  )
}

function AssetSettings() {
  const perms = useAccountingPerms()
  const settings = useAccountingSettings()
  const chart = useChart()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [rule, setRule] = useState<StartRule | null>(null)
  const [account, setAccount] = useState<string | null>(null)
  const current = settings.data
  const ruleValue = rule ?? current?.default_asset_start_rule ?? 'next_month'
  const accountValue = account ?? current?.asset_disposal_account_id ?? ''
  const dirty = current && (ruleValue !== current.default_asset_start_rule || accountValue !== (current.asset_disposal_account_id ?? ''))
  const save = useMutation({
    mutationFn: () => put<AccountingSettings>('/accounting/settings', { default_asset_start_rule: ruleValue, asset_disposal_account_id: accountValue || null }),
    onSuccess: () => {
      invalidate()
      setRule(null)
      setAccount(null)
      toast('ok', 'Configuración de activos fijos guardada.')
    },
  })
  const byId = useAccountsById(chart.data?.accounts)
  const disposal = current?.asset_disposal_account_id ? byId.get(current.asset_disposal_account_id) : undefined
  return (
    <Sheet className="mt-6 p-5">
      <h2 className="font-semibold">Configuración de los bienes</h2>
      {!current ? null : perms.canPost ? (
        <form
          className="mt-3 grid grid-cols-2 gap-6"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-sm font-medium text-ink-2">Inicio de la depreciación por defecto</legend>
            {(Object.keys(START_RULE_LABELS) as StartRule[]).map((r) => (
              <label key={r} className="flex cursor-pointer items-center gap-2">
                <input type="radio" name="default-rule" className="accent-(--ledger)" checked={ruleValue === r} onChange={() => setRule(r)} />
                {START_RULE_LABELS[r]}
              </label>
            ))}
            <p className="text-sm text-ink-3">Es opción del contribuyente por cada bien (Decreto 3182, art. 30); esto es lo que propone el alta.</p>
          </fieldset>
          <div className="flex flex-col gap-2">
            <Field label="Cuenta de resultado por bajas" hint="Donde va el valor neto de un bien dado de baja. Sin elegir, la 17.01 del plan propuesto.">
              {(p) => (
                <LedgerAccountSelect {...p} accounts={chart.data?.accounts ?? []} kinds={['expense', 'income']} value={accountValue} onChange={setAccount} empty="La 17.01 del plan propuesto" />
              )}
            </Field>
          </div>
          {save.error ? (
            <div className="col-span-2">
              <ApiErrorNotice error={save.error} />
            </div>
          ) : null}
          <div className="col-span-2">
            <Button type="submit" variant="secondary" busy={save.isPending} disabled={!dirty}>
              Guardar configuración
            </Button>
          </div>
        </form>
      ) : (
        <dl className="mt-3 grid grid-cols-2 gap-6 text-sm">
          <div>
            <dt className="text-ink-3">Inicio por defecto</dt>
            <dd>{START_RULE_LABELS[current.default_asset_start_rule]}</dd>
          </div>
          <div>
            <dt className="text-ink-3">Cuenta de resultado por bajas</dt>
            <dd>{disposal ? `${disposal.code} ${disposal.name}` : 'La 17.01 del plan propuesto'}</dd>
          </div>
          <p className="col-span-2 text-ink-3">La cambia el propietario o el contador.</p>
        </dl>
      )}
    </Sheet>
  )
}

function AccountCodes({ category, byId }: { category: AssetCategory; byId: Map<string, LedgerAccount> }) {
  const item = (label: string, id: string | null) => {
    const a = id ? byId.get(id) : undefined
    return (
      <span className="flex gap-2">
        <span className="w-12 shrink-0 text-ink-3">{label}</span>
        {a ? (
          <span className="tabular-nums" title={`${a.code} ${a.name}`}>
            {a.code}
          </span>
        ) : (
          <span className="text-amber">falta</span>
        )}
      </span>
    )
  }
  return (
    <span className="flex flex-col text-sm">
      {item('Bien', category.asset_account_id)}
      {item('Acum.', category.accumulated_account_id)}
      {item('Gasto', category.expense_account_id)}
    </span>
  )
}

export function AssetCategoriesPage() {
  const perms = useAccountingPerms()
  const categories = useAssetCategories()
  const chart = useChart()
  const byId = useAccountsById(chart.data?.accounts)
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [params, setParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const q = fold(useDeferredValue(search.trim()))
  const [onlyIncomplete, setOnlyIncomplete] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [dialog, setDialog] = useState<{ kind: 'new' } | { kind: 'validate'; category: AssetCategory } | null>(null)
  const editingId = params.get('editar')
  const all = categories.data ?? []
  const editing = all.find((c) => c.id === editingId)

  const load = useMutation({
    mutationFn: () => post<AssetCategory[]>('/accounting/asset-categories/load-proposed'),
    onSuccess: (list) => {
      invalidate()
      toast('ok', `Se cargaron las ${list.length} categorías propuestas, sin validar.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudieron cargar las categorías propuestas.')),
  })
  const archive = useMutation({
    mutationFn: (c: AssetCategory) => patch<AssetCategory>(`/accounting/asset-categories/${c.id}`, { archived: !c.archived_at }),
    onSuccess: (c) => {
      invalidate()
      toast('ok', c.archived_at ? `Categoría «${c.name}» archivada: ya no se ofrece para bienes nuevos.` : `Categoría «${c.name}» desarchivada.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar la categoría.')),
  })
  const setEditing = (id: string | null) => {
    const next = new URLSearchParams(params)
    if (id) next.set('editar', id)
    else next.delete('editar')
    setParams(next, { replace: true })
  }
  const toggle = (id: string) => {
    const next = new Set(open)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setOpen(next)
  }

  const live = all.filter((c) => !c.archived_at)
  const incomplete = live.filter((c) => !c.complete).length
  const validated = live.filter((c) => c.validation_status === 'validated').length
  const archivedCount = all.length - live.length
  const rows = all
    .filter((c) => showArchived || !c.archived_at)
    .filter((c) => !onlyIncomplete || !c.complete)
    .filter((c) => !q || fold(c.name).includes(q) || fold(c.legal_reference ?? '').includes(q))
  const cols = perms.canManage || perms.canPost ? 6 : 5

  return (
    <>
      {categories.isPending ? (
        <Sheet>
          <TableSkeleton rows={8} cols={5} />
        </Sheet>
      ) : categories.isError ? (
        <ApiErrorNotice error={categories.error} title="No se pudieron cargar las categorías." />
      ) : all.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay categorías de activo fijo"
            action={
              perms.canManage ? (
                <div className="flex flex-wrap gap-2">
                  <Button busy={load.isPending} onClick={() => load.mutate()}>
                    <Sparkles size={16} />
                    Cargar las 34 categorías propuestas
                  </Button>
                  <Button variant="secondary" onClick={() => setDialog({ kind: 'new' })}>
                    <Plus size={16} />
                    Crear una a mano
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-ink-3">{perms.manageReason}</p>
              )
            }
          >
            Cada bien se deprecia según su categoría: vida útil, valor residual y las tres cuentas (bien, depreciación acumulada y gasto). Las propuestas
            salen de la tabla del Decreto 3182/2019, art. 31, con la redacción del Decreto 6105/2021 (vigente desde el 14-10-2021), y se cargan{' '}
            <strong className="font-semibold">sin validar</strong>: un contador tiene que revisarlas antes de que la depreciación sea un dato firme.
          </EmptyState>
        </Sheet>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-md border border-line bg-surface p-3.5">
            <div className="relative w-80">
              <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
              <Input type="search" aria-label="Buscar categoría" placeholder="Buscar por nombre o norma" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <Check label={`Solo incompletas (${incomplete})`} checked={onlyIncomplete} onChange={setOnlyIncomplete} />
            {archivedCount > 0 && <Check label={`Mostrar archivadas (${archivedCount})`} checked={showArchived} onChange={setShowArchived} />}
            <p className="ml-auto text-sm text-ink-2">
              {live.length} en uso, {validated} validadas, {incomplete} incompletas.
            </p>
            {perms.canManage && (
              <Button variant="secondary" onClick={() => setDialog({ kind: 'new' })}>
                <Plus size={16} />
                Nueva categoría
              </Button>
            )}
          </div>
          <Sheet>
            <table className="w-full table-fixed" aria-label="Categorías de activo fijo">
              <colgroup>
                <col />
                <col className="w-32" />
                <col className="w-24" />
                <col className="w-40" />
                <col className="w-36" />
                {cols === 6 && <col className="w-32" />}
              </colgroup>
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Categoría y fuente</Th>
                  <Th>Vida útil</Th>
                  <Th align="right">Residual</Th>
                  <Th>Cuentas</Th>
                  <Th>Estado</Th>
                  {cols === 6 && (
                    <Th>
                      <span className="sr-only">Acciones</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={cols} className="px-4 py-6 text-center text-ink-2">
                      Ninguna categoría coincide.
                    </td>
                  </tr>
                )}
                {rows.map((c) => {
                  const expanded = open.has(c.id)
                  return (
                    <Fragment key={c.id}>
                      <tr className={cx('align-top', c.archived_at && 'text-ink-3')}>
                        <td className="px-4 py-2.5">
                          <button
                            type="button"
                            className="flex items-start gap-1.5 text-left font-medium hover:text-ledger"
                            aria-expanded={expanded}
                            aria-label={`${c.name}: ${expanded ? 'ocultar' : 'ver'} la fuente`}
                            onClick={() => toggle(c.id)}
                          >
                            {expanded ? <ChevronDown size={15} className="mt-0.5 shrink-0" aria-hidden /> : <ChevronRight size={15} className="mt-0.5 shrink-0" aria-hidden />}
                            {c.name}
                          </button>
                          <span className="block pl-5 text-sm text-ink-3">{c.legal_reference ?? 'Creada en esta empresa'}</span>
                        </td>
                        <td className="px-4 py-2.5 tabular-nums">
                          {c.useful_life_months ? (
                            <>
                              {monthsText(c.useful_life_months)}
                              <span className="block text-sm text-ink-3">{c.useful_life_months} meses</span>
                            </>
                          ) : (
                            <span className="text-amber">sin vida útil</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{c.residual_rate === null ? <span className="text-amber">falta</span> : percentText(c.residual_rate)}</td>
                        <td className="px-4 py-2.5">
                          <AccountCodes category={c} byId={byId} />
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="flex flex-col items-start gap-1">
                            {c.validation_status === 'validated' ? <Badge tone="ok">Validada</Badge> : <Badge tone="warn">Sin validar</Badge>}
                            {!c.complete && <Badge tone="bad">Incompleta</Badge>}
                            {c.archived_at && <Badge>Archivada</Badge>}
                          </span>
                        </td>
                        {cols === 6 && (
                          <td className="px-2 py-1.5">
                            <div className="flex justify-end gap-0.5">
                              {perms.canManage && (
                                <Button variant="ghost" className="h-8 px-2" aria-label={`${c.complete ? 'Editar' : 'Completar'} ${c.name}`} title={c.complete ? 'Editar' : 'Completar'} onClick={() => setEditing(c.id)}>
                                  <Pencil size={15} />
                                </Button>
                              )}
                              {perms.canPost && c.validation_status !== 'validated' && !c.archived_at && (
                                <Button
                                  variant="ghost"
                                  className="h-8 px-2 text-ledger"
                                  aria-label={`Validar ${c.name}`}
                                  title={c.complete ? 'Validar' : 'Completala antes de validarla'}
                                  disabled={!c.complete}
                                  onClick={() => setDialog({ kind: 'validate', category: c })}
                                >
                                  <BadgeCheck size={15} />
                                </Button>
                              )}
                              {perms.canManage && (
                                <Button
                                  variant="ghost"
                                  className="h-8 px-2"
                                  aria-label={`${c.archived_at ? 'Desarchivar' : 'Archivar'} ${c.name}`}
                                  title={c.archived_at ? 'Desarchivar' : 'Archivar'}
                                  busy={archive.isPending && archive.variables?.id === c.id}
                                  onClick={() => archive.mutate(c)}
                                >
                                  {c.archived_at ? <ArchiveRestore size={15} /> : <Archive size={15} />}
                                </Button>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                      {!c.complete && !c.archived_at && (
                        <tr>
                          <td colSpan={cols} className="px-4 pb-2.5 pl-9 text-sm text-debit">
                            Falta: {c.missing.join(', ')}. Hasta completarla no se usa para bienes nuevos ni en la depreciación.
                          </td>
                        </tr>
                      )}
                      {expanded && (
                        <tr className="bg-sunken/40">
                          <td colSpan={cols} className="px-4 py-3 pl-9 text-sm">
                            {c.citation && <p className="max-w-[75ch] text-ink">«{c.citation}»</p>}
                            <p className="mt-1 text-ink-2">{c.legal_reference ?? 'Sin referencia legal: categoría creada en esta empresa.'}</p>
                            {c.note && <p className="mt-1 max-w-[75ch] text-ink-2">Nota: {c.note}</p>}
                            {c.source_url && (
                              <a href={c.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 font-medium text-ledger hover:underline">
                                Ver el texto oficial en la DNIT
                                <ExternalLink size={13} aria-hidden />
                              </a>
                            )}
                            {c.validation_status === 'validated' && (
                              <p className="mt-1 text-ink-2">
                                Validada por {c.validated_by_name} (matrícula {c.validated_reference}){c.validated_at ? `, el ${formatDateTime(c.validated_at)}` : ''}.
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
            <p className="border-t border-line px-4 py-2.5 text-sm text-ink-3">
              Propuestas de la tabla del Decreto 3182/2019, art. 31, con la redacción del Decreto 6105/2021 (vigente desde el 14-10-2021): un bien
              comprado antes puede regirse por otra versión (art. 30). Cambiar la vida útil, el residual o las cuentas vuelve la categoría a «sin
              validar».
            </p>
          </Sheet>
        </>
      )}
      <AssetSettings />

      <Modal open={Boolean(editing) || dialog?.kind === 'new'} size="lg" title={editing ? (editing.complete ? `Editar «${editing.name}»` : `Completar «${editing.name}»`) : 'Nueva categoría'} onClose={() => (editing ? setEditing(null) : setDialog(null))}>
        {editing ? <CategoryForm key={editing.id} category={editing} onDone={() => setEditing(null)} /> : dialog?.kind === 'new' ? <CategoryForm onDone={() => setDialog(null)} /> : null}
      </Modal>
      <Modal open={dialog?.kind === 'validate'} title="Validar la categoría" onClose={() => setDialog(null)}>
        {dialog?.kind === 'validate' && <ValidateForm category={dialog.category} onDone={() => setDialog(null)} />}
      </Modal>
    </>
  )
}
