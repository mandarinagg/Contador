import { keepPreviousData, useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Pencil, Plus, Search } from 'lucide-react'
import { type FormEvent, useDeferredValue, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Textarea } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { rucStatus } from '../../lib/ruc'
import { ApiError, get, patch, post, qs } from '../../services/api'
import { ApiErrorNotice, Check, TableSkeleton, Th } from './components'
import { errorMessage } from './forms'
import { financeKeys, useFinance } from './data'
import { COUNTERPARTY_KIND_LABELS } from './labels'
import type { Counterparty, CounterpartyKind } from './types'

const PAGE = 50

function CounterpartyForm({ counterparty, onDone }: { counterparty?: Counterparty; onDone: () => void }) {
  const { cid } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({
    name: counterparty?.name ?? '',
    kind: counterparty?.kind ?? ('supplier' as CounterpartyKind),
    ruc: counterparty?.ruc ?? '',
    ruc_check_digit: counterparty?.ruc_check_digit ?? '',
    notes: counterparty?.notes ?? '',
  })
  const [touched, setTouched] = useState(false)
  const ruc = rucStatus(form.ruc, form.ruc_check_digit)
  const showRucError = !ruc.ok && (touched || form.ruc_check_digit !== '')

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        kind: form.kind,
        ruc: form.ruc || null,
        ruc_check_digit: form.ruc ? form.ruc_check_digit : null,
        notes: form.notes.trim() || null,
      }
      return counterparty
        ? patch<Counterparty>(`/finance/contexts/${cid}/counterparties/${counterparty.id}`, body)
        : post<Counterparty>(`/finance/contexts/${cid}/counterparties`, body)
    },
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: financeKeys.counterparties(cid) })
      toast('ok', counterparty ? `Contraparte «${c.name}» guardada.` : `Contraparte «${c.name}» creada.`)
      onDone()
    },
  })
  const error = save.error instanceof ApiError ? save.error : null
  const fe = error?.fieldErrors() ?? {}

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (ruc.ok) save.mutate()
  }

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-4" noValidate>
      {error && (error.status !== 422 || Object.keys(fe).length === 0 || fe['']) && (
        <div className="col-span-2">
          <Notice tone="bad" title={error.message}>
            {Object.values(fe).join(' ')}
          </Notice>
        </div>
      )}
      <div className="col-span-2">
        <Field label="Nombre o razón social" error={fe.name}>
          {(p) => <Input {...p} autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
        </Field>
      </div>
      <div className="col-span-2">
        <Field label="Tipo">
          {(p) => (
            <Select {...p} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as CounterpartyKind })}>
              {Object.entries(COUNTERPARTY_KIND_LABELS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Field label="RUC" hint="Opcional. Sin puntos ni dígito verificador.">
        {(p) => (
          <Input
            {...p}
            inputMode="numeric"
            maxLength={8}
            value={form.ruc}
            onChange={(e) => setForm({ ...form, ruc: e.target.value.replace(/\D/g, '') })}
          />
        )}
      </Field>
      <Field label="DV">
        {(p) => (
          <Input
            {...p}
            aria-invalid={showRucError || undefined}
            aria-describedby="ruc-status"
            inputMode="numeric"
            maxLength={1}
            className="w-16"
            value={form.ruc_check_digit}
            onChange={(e) => setForm({ ...form, ruc_check_digit: e.target.value.replace(/\D/g, '') })}
          />
        )}
      </Field>
      <p id="ruc-status" aria-live="polite" className={cx('col-span-2 -mt-2 text-sm', showRucError ? 'text-debit' : 'text-ledger')}>
        {showRucError ? ruc.message : form.ruc && ruc.ok ? `RUC ${form.ruc}-${form.ruc_check_digit} válido.` : ''}
      </p>
      <div className="col-span-2">
        <Field label="Notas" hint="Opcional." error={fe.notes}>
          {(p) => <Textarea {...p} maxLength={500} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />}
        </Field>
      </div>
      <div className="col-span-2 flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {counterparty ? 'Guardar cambios' : 'Crear contraparte'}
        </Button>
      </div>
    </form>
  )
}

export function CounterpartiesPage() {
  const { cid, canWrite, readOnlyReason } = useFinance()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const q = useDeferredValue(search.trim())
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<Counterparty | 'new' | null>(null)

  const list = useInfiniteQuery({
    queryKey: [...financeKeys.counterparties(cid), 'list', q, showArchived],
    queryFn: ({ pageParam }) =>
      get<Counterparty[]>(
        `/finance/contexts/${cid}/counterparties${qs({ q, include_archived: showArchived, limit: PAGE, before: pageParam })}`,
      ),
    initialPageParam: '' as string,
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].id : undefined),
    placeholderData: keepPreviousData,
  })
  const archive = useMutation({
    mutationFn: (c: Counterparty) => patch<Counterparty>(`/finance/contexts/${cid}/counterparties/${c.id}`, { archived: c.archived_at === null }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: financeKeys.counterparties(cid) })
      toast('ok', c.archived_at ? `Contraparte «${c.name}» archivada.` : `Contraparte «${c.name}» desarchivada.`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo cambiar el estado de la contraparte.')),
  })
  const rows = list.data?.pages.flat() ?? []

  return (
    <>
      <PageHeader
        title="Contrapartes"
        description="Clientes, proveedores, empleados, bancos y el Estado: con quién entra o sale la plata."
        actions={
          canWrite && (
            <Button onClick={() => setEditing('new')}>
              <Plus size={16} />
              Nueva contraparte
            </Button>
          )
        }
      />
      {!canWrite && <p className="-mt-3 mb-4 text-sm text-ink-3">{readOnlyReason}</p>}
      <div className="mb-3 flex items-center gap-4">
        <div className="relative w-80">
          <Search size={15} aria-hidden className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
          <Input
            type="search"
            aria-label="Buscar por nombre o RUC"
            placeholder="Buscar por nombre o RUC"
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Check label="Incluir archivadas" checked={showArchived} onChange={setShowArchived} />
      </div>
      <Sheet>
        {list.isPending ? (
          <TableSkeleton cols={4} />
        ) : list.isError ? (
          <div className="p-5">
            <ApiErrorNotice error={list.error} title="No se pudieron cargar las contrapartes." />
          </div>
        ) : rows.length === 0 ? (
          q ? (
            <EmptyState title={`Nada coincide con «${q}»`}>Probá con parte del nombre o con los primeros dígitos del RUC.</EmptyState>
          ) : (
            <EmptyState
              title="Todavía no hay contrapartes. Creá la primera"
              action={
                canWrite && (
                  <Button onClick={() => setEditing('new')}>
                    <Plus size={16} />
                    Nueva contraparte
                  </Button>
                )
              }
            >
              Con contrapartes vas a poder ver cuánto le pagaste a cada proveedor o cuánto te pagó cada cliente.
            </EmptyState>
          )
        ) : (
          <>
            <table className={cx('w-full', list.isPlaceholderData && 'opacity-60')}>
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Nombre</Th>
                  <Th>Tipo</Th>
                  <Th>RUC</Th>
                  {canWrite && (
                    <Th>
                      <span className="sr-only">Acciones</span>
                    </Th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((c) => (
                  <tr key={c.id} className={cx(c.archived_at && 'text-ink-3')}>
                    <td className="px-4 py-3">
                      <p className="font-medium">
                        {c.name}
                        {c.archived_at && (
                          <span className="ml-2">
                            <Badge>Archivada</Badge>
                          </span>
                        )}
                      </p>
                      {c.notes && <p className="max-w-[50ch] truncate text-sm text-ink-2">{c.notes}</p>}
                    </td>
                    <td className="px-4 py-3 text-sm text-ink-2">{COUNTERPARTY_KIND_LABELS[c.kind]}</td>
                    <td className="px-4 py-3 tabular-nums">{c.ruc ? `${c.ruc}-${c.ruc_check_digit}` : <span className="text-ink-3">—</span>}</td>
                    {canWrite && (
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-1">
                          <Button variant="ghost" className="h-8 px-2" aria-label={`Editar ${c.name}`} onClick={() => setEditing(c)}>
                            <Pencil size={15} />
                          </Button>
                          <Button
                            variant="ghost"
                            className="h-8 px-2"
                            disabled={archive.isPending}
                            aria-label={c.archived_at ? `Desarchivar ${c.name}` : `Archivar ${c.name}`}
                            onClick={() => archive.mutate(c)}
                          >
                            {c.archived_at ? <ArchiveRestore size={15} /> : <Archive size={15} />}
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {list.hasNextPage && (
              <div className="border-t border-line p-4">
                <Button variant="secondary" busy={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>
                  Cargar más
                </Button>
              </div>
            )}
          </>
        )}
      </Sheet>
      <Modal open={editing !== null} title={editing === 'new' ? 'Nueva contraparte' : 'Editar contraparte'} onClose={() => setEditing(null)}>
        {editing !== null && (
          <CounterpartyForm key={editing === 'new' ? 'new' : editing.id} counterparty={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />
        )}
      </Modal>
    </>
  )
}
