import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Pencil, Plus, Sparkles } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { plural } from '../../lib/format'
import { ApiError, patch, post } from '../../services/api'
import { ApiErrorNotice, Check, TableSkeleton } from './components'
import { errorMessage } from './forms'
import { financeKeys, useCategories, useFinance } from './data'
import { byName } from './labels'
import type { Category, CategoryKind } from './types'
import { type LedgerMapping, useLedgerMapping } from '../accounting/entryRefs'
import { LedgerAccountField, LedgerAccountTag } from '../accounting/financeBridge'


function CategoryForm({
  category,
  all,
  initialKind,
  mapping,
  onDone,
}: {
  category?: Category
  all: Category[]
  initialKind: CategoryKind
  mapping: LedgerMapping
  onDone: () => void
}) {
  const { cid } = useFinance()
  const [ledgerId, setLedgerId] = useState(category?.ledger_account_id ?? '')
  const ledgerChanged = mapping.canEdit && ledgerId !== (category?.ledger_account_id ?? '')
  const qc = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState(category?.name ?? '')
  const [kind, setKind] = useState<CategoryKind>(category?.kind ?? initialKind)
  const [parentId, setParentId] = useState(category?.parent_id ?? '')
  const hasChildren = Boolean(category && all.some((c) => c.parent_id === category.id))
  // Un solo nivel: los padres posibles son categorías de primer nivel del mismo tipo.
  const parents = all.filter((c) => c.kind === kind && c.parent_id === null && !c.archived_at && c.id !== category?.id).sort(byName)

  const save = useMutation({
    mutationFn: async () => {
      const ledger = ledgerChanged ? { ledger_account_id: ledgerId || null } : {}
      if (category) return patch<Category>(`/finance/contexts/${cid}/categories/${category.id}`, { name, parent_id: parentId || null, ...ledger })
      const created = await post<Category>(`/finance/contexts/${cid}/categories`, { name, kind, parent_id: parentId || null })
      // La cuenta contable solo se asigna al editar (la API no la recibe al crear).
      return ledgerChanged ? patch<Category>(`/finance/contexts/${cid}/categories/${created.id}`, ledger) : created
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: financeKeys.categories(cid) })
      toast('ok', category ? `Categoría «${c.name}» guardada.` : `Categoría «${c.name}» creada.`)
      onDone()
    },
  })
  const error = save.error instanceof ApiError ? save.error : null
  const fe = error?.fieldErrors() ?? {}

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      {error && error.status !== 422 && <Notice tone="bad" title={error.message} />}
      {error?.status === 422 && !fe.name && <Notice tone="bad" title={error.message} />}
      <Field label="Nombre" error={fe.name}>
        {(p) => <Input {...p} autoFocus value={name} onChange={(e) => setName(e.target.value)} />}
      </Field>
      <Field label="Tipo" hint={category ? 'El tipo no cambia después de crearla.' : undefined}>
        {(p) => (
          <Select
            {...p}
            disabled={Boolean(category)}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as CategoryKind)
              setParentId('')
            }}
          >
            <option value="expense">Gasto</option>
            <option value="income">Ingreso</option>
          </Select>
        )}
      </Field>
      <Field
        label="Dentro de"
        hint={hasChildren ? 'Tiene subcategorías: queda en el primer nivel (solo hay un nivel).' : 'Opcional. Las subcategorías tienen un solo nivel.'}
      >
        {(p) => (
          <Select {...p} disabled={hasChildren} value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">— Primer nivel —</option>
            {parents.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <LedgerAccountField
        mapping={mapping}
        kinds={[kind]}
        value={ledgerId}
        onChange={setLedgerId}
        hint={
          parentId
            ? 'Opcional en una subcategoría: si queda vacía, usa la cuenta contable de su categoría.'
            : `Una cuenta de ${kind === 'income' ? 'ingreso' : 'gasto'}: a ella va el movimiento al proponer el asiento.`
        }
      />
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {category ? 'Guardar cambios' : 'Crear categoría'}
        </Button>
      </div>
    </form>
  )
}

function KindSection({
  kind,
  all,
  showArchived,
  canWrite,
  onEdit,
  onArchive,
  busy,
  mapping,
}: {
  mapping: LedgerMapping
  kind: CategoryKind
  all: Category[]
  showArchived: boolean
  canWrite: boolean
  onEdit: (c: Category) => void
  onArchive: (c: Category) => void
  busy: boolean
}) {
  const visible = all.filter((c) => c.kind === kind && (showArchived || !c.archived_at))
  const top = visible.filter((c) => c.parent_id === null || !visible.some((p) => p.id === c.parent_id)).sort(byName)
  const children = (id: string) => visible.filter((c) => c.parent_id === id).sort(byName)
  const row = (c: Category, child: boolean) => (
    <li key={c.id} className={cx('flex items-center gap-3 py-2 pr-4', child ? 'pl-10' : 'pl-4', c.archived_at && 'text-ink-3')}>
      <span className={cx('min-w-0 flex-1', !child && 'font-medium')}>
        {child && <span aria-hidden className="mr-2 text-ink-3">└</span>}
        {c.name}
        {c.archived_at && (
          <span className="ml-2">
            <Badge>Archivada</Badge>
          </span>
        )}
        {mapping.show && (
          <span className="block font-normal">
            <LedgerAccountTag
              mapping={mapping}
              id={c.ledger_account_id}
              inherited={(() => {
                const p = c.parent_id ? all.find((x) => x.id === c.parent_id) : undefined
                return p?.ledger_account_id ? { id: p.ledger_account_id, from: p.name } : null
              })()}
            />
          </span>
        )}
      </span>
      {canWrite && (
        <span className="flex gap-1">
          <Button variant="ghost" className="h-7 px-2" aria-label={`Editar ${c.name}`} onClick={() => onEdit(c)}>
            <Pencil size={14} />
          </Button>
          <Button
            variant="ghost"
            className="h-7 px-2"
            disabled={busy}
            aria-label={c.archived_at ? `Desarchivar ${c.name}` : `Archivar ${c.name}`}
            onClick={() => onArchive(c)}
          >
            {c.archived_at ? <ArchiveRestore size={14} /> : <Archive size={14} />}
          </Button>
        </span>
      )}
    </li>
  )
  return (
    <Sheet>
      <h2 className="flex items-baseline justify-between border-b border-line px-4 py-3 font-semibold">
        {kind === 'income' ? 'Ingresos' : 'Gastos'}
        <span className="text-sm font-normal text-ink-3">{plural(visible.length, 'categoría', 'categorías')}</span>
      </h2>
      {top.length === 0 ? (
        <p className="px-4 py-6 text-ink-2">Sin categorías de {kind === 'income' ? 'ingreso' : 'gasto'}.</p>
      ) : (
        <ul className="divide-y divide-line">
          {top.map((c) => [row(c, false), ...children(c.id).map((ch) => row(ch, true))])}
        </ul>
      )}
    </Sheet>
  )
}

export function CategoriesPage() {
  const { cid, context, canWrite, readOnlyReason } = useFinance()
  const mapping = useLedgerMapping(context.kind === 'business')
  const qc = useQueryClient()
  const toast = useToast()
  const categories = useCategories(cid)
  const [editing, setEditing] = useState<{ category?: Category; kind: CategoryKind } | null>(null)
  const [showArchived, setShowArchived] = useState(false)

  const suggested = useMutation({
    mutationFn: () => post<Category[]>(`/finance/contexts/${cid}/categories/suggested`),
    onSuccess: (list) => {
      qc.invalidateQueries({ queryKey: financeKeys.categories(cid) })
      toast('ok', `Se crearon ${plural(list.length, 'categoría sugerida', 'categorías sugeridas')}.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudieron crear las categorías sugeridas.')),
  })
  const archive = useMutation({
    mutationFn: (c: Category) => patch<Category>(`/finance/contexts/${cid}/categories/${c.id}`, { archived: c.archived_at === null }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: financeKeys.categories(cid) })
      toast('ok', c.archived_at ? `Categoría «${c.name}» archivada.` : `Categoría «${c.name}» desarchivada.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar el estado de la categoría.')),
  })

  const all = categories.data ?? []
  const archivedCount = all.filter((c) => c.archived_at).length

  return (
    <>
      <PageHeader
        title="Categorías"
        description="Para saber en qué entra y en qué se va la plata. Un nivel de subcategorías; las que ya no uses, archivalas."
        actions={
          canWrite &&
          all.length > 0 && (
            <Button onClick={() => setEditing({ kind: 'expense' })}>
              <Plus size={16} />
              Nueva categoría
            </Button>
          )
        }
      />
      {!canWrite && <p className="-mt-3 mb-4 text-sm text-ink-3">{readOnlyReason}</p>}
      {categories.isPending ? (
        <Sheet>
          <TableSkeleton cols={2} />
        </Sheet>
      ) : categories.isError ? (
        <ApiErrorNotice error={categories.error} title="No se pudieron cargar las categorías." />
      ) : all.length === 0 ? (
        <Sheet>
          <EmptyState
            title="Todavía no hay categorías"
            action={
              canWrite && (
                <div className="flex gap-2">
                  <Button busy={suggested.isPending} onClick={() => suggested.mutate()}>
                    <Sparkles size={16} />
                    Crear categorías sugeridas
                  </Button>
                  <Button variant="secondary" onClick={() => setEditing({ kind: 'expense' })}>
                    <Plus size={16} />
                    Crear una a mano
                  </Button>
                </div>
              )
            }
          >
            {context.kind === 'business'
              ? 'Las sugeridas cubren lo típico de una empresa paraguaya: ventas, sueldos y cargas sociales, honorarios, ANDE y ESSAP, impuestos y tasas, comisiones bancarias. Después podés renombrarlas o archivarlas.'
              : 'Las sugeridas cubren lo típico de un hogar: sueldo, supermercado, vivienda, ANDE y ESSAP, salud, educación, aportes a la empresa. Después podés renombrarlas o archivarlas.'}
          </EmptyState>
        </Sheet>
      ) : (
        <>
          <div className="grid grid-cols-2 items-start gap-6">
            {(['expense', 'income'] as const).map((k) => (
              <KindSection
                key={k}
                kind={k}
                all={all}
                showArchived={showArchived}
                canWrite={canWrite}
                onEdit={(c) => setEditing({ category: c, kind: c.kind })}
                onArchive={(c) => archive.mutate(c)}
                busy={archive.isPending}
                mapping={mapping}
              />
            ))}
          </div>
          {archivedCount > 0 && (
            <div className="mt-4">
              <Check label={`Mostrar archivadas (${archivedCount})`} checked={showArchived} onChange={setShowArchived} />
            </div>
          )}
        </>
      )}
      <Modal open={editing !== null} title={editing?.category ? 'Editar categoría' : 'Nueva categoría'} onClose={() => setEditing(null)}>
        {editing && (
          <CategoryForm
            key={editing.category?.id ?? 'new'}
            category={editing.category}
            initialKind={editing.kind}
            all={all}
            mapping={mapping}
            onDone={() => setEditing(null)}
          />
        )}
      </Modal>
    </>
  )
}

