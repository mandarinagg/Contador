/**
 * Centros de costos (D-060): código, nombre y archivo, un solo nivel. Se usan en las líneas de
 * ingreso y gasto de los asientos; la configuración puede exigirlos al contabilizar.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Pencil, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, PageHeader, Sheet } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { patch, post, put, qs } from '../../services/api'
import { ApiErrorNotice, Check, TableSkeleton, Th } from '../finance/components'
import { todayIso } from '../finance/labels'
import { accountingKeys, useAccountingPerms, useAccountingSettings, useCostCenters, useInvalidateAccounting } from './data'
import type { AccountingSettings } from './types'
import type { CostCenter } from './types3b'
import { centerFormErrors } from './costCenters'

function CenterForm({ center, onDone }: { center?: CostCenter; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [code, setCode] = useState(center?.code ?? '')
  const [name, setName] = useState(center?.name ?? '')
  const [touched, setTouched] = useState(false)
  const errors = centerFormErrors(code, name)
  const save = useMutation({
    mutationFn: () =>
      center
        ? patch<CostCenter>(`/accounting/cost-centers/${center.id}`, { code: code.trim(), name: name.trim() })
        : post<CostCenter>('/accounting/cost-centers', { code: code.trim(), name: name.trim() }),
    onSuccess: (c) => {
      invalidate()
      toast('ok', center ? `Centro ${c.code} guardado.` : `Centro ${c.code} ${c.name} creado.`)
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
        if (!errors.code && !errors.name) save.mutate()
      }}
    >
      {save.error ? <ApiErrorNotice error={save.error} /> : null}
      <div className="grid grid-cols-[10rem_1fr] gap-4">
        <Field label="Código" error={touched ? errors.code : undefined} hint="Corto, sin espacios.">
          {(p) => <Input {...p} autoFocus maxLength={20} value={code} onChange={(e) => setCode(e.target.value)} />}
        </Field>
        <Field label="Nombre" error={touched ? errors.name : undefined}>
          {(p) => <Input {...p} maxLength={150} placeholder="Administración, Ventas, Sucursal Luque…" value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
      </div>
      <div className="flex justify-end gap-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancelar
        </Button>
        <Button type="submit" busy={save.isPending}>
          {center ? 'Guardar' : 'Crear centro'}
        </Button>
      </div>
    </form>
  )
}

function RequiredSetting() {
  const perms = useAccountingPerms()
  const settings = useAccountingSettings()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const queryClient = useQueryClient()
  // Valor elegido mientras se guarda: la casilla no vuelve al anterior hasta que responde la API.
  const [choice, setChoice] = useState<boolean | null>(null)
  const save = useMutation({
    mutationFn: (value: boolean) => put<AccountingSettings>('/accounting/settings', { cost_centers_required: value }),
    onSettled: () => setChoice(null),
    onSuccess: (s) => {
      queryClient.setQueryData(accountingKeys.settings(), s)
      invalidate()
      toast('ok', s.cost_centers_required ? 'Desde ahora, el centro es obligatorio en ingresos y gastos al contabilizar.' : 'El centro de costos vuelve a ser opcional.')
    },
  })
  const required = Boolean(settings.data?.cost_centers_required)
  return (
    <Sheet className="flex flex-col gap-3 p-5">
      <div>
        <h2 className="font-semibold">Centro obligatorio</h2>
        <p className="mt-1 text-sm text-ink-2">
          Si se exige, un asiento manual, desde finanzas o recurrente no se contabiliza mientras tenga una línea de ingreso o gasto sin centro. Los
          generados (depreciación, baja, refundición y reversiones) quedan exentos.
        </p>
      </div>
      {settings.isPending ? null : perms.canPost ? (
        <>
          <Check
            label="Exigir centro de costos en ingresos y gastos"
            checked={choice ?? required}
            disabled={save.isPending}
            onChange={(v) => {
              setChoice(v)
              save.mutate(v)
            }}
          />
          {save.error ? <ApiErrorNotice error={save.error} /> : null}
        </>
      ) : (
        <p className="text-sm">
          {required ? 'Exigido al contabilizar.' : 'Opcional.'} <span className="text-ink-3">Lo cambia el propietario o el contador.</span>
        </p>
      )}
    </Sheet>
  )
}

export function CostCentersPage() {
  const perms = useAccountingPerms()
  const centers = useCostCenters()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const [dialog, setDialog] = useState<{ kind: 'new' } | { kind: 'edit'; center: CostCenter } | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const archive = useMutation({
    mutationFn: (c: CostCenter) => patch<CostCenter>(`/accounting/cost-centers/${c.id}`, { archived: !c.archived_at }),
    onSuccess: (c) => {
      invalidate()
      toast('ok', c.archived_at ? `Centro ${c.code} archivado: ya no se ofrece en líneas nuevas.` : `Centro ${c.code} desarchivado.`)
    },
    onError: (e) => toast('bad', e instanceof Error ? e.message : 'No se pudo cambiar el centro.'),
  })
  const all = [...(centers.data ?? [])].sort((a, b) => a.code.localeCompare(b.code, 'es'))
  const rows = all.filter((c) => showArchived || !c.archived_at)
  const archivedCount = all.filter((c) => c.archived_at).length
  const year = todayIso().slice(0, 4)

  return (
    <>
      <PageHeader
        title="Centros de costos"
        description="Para ver ingresos y gastos por área, sucursal o proyecto. Solo van en líneas de cuentas de ingreso o de gasto y no cambian los saldos contables."
        actions={
          perms.canManage &&
          all.length > 0 && (
            <Button onClick={() => setDialog({ kind: 'new' })}>
              <Plus size={16} />
              Nuevo centro
            </Button>
          )
        }
      />
      {!perms.canManage && <p className="-mt-3 mb-4 text-sm text-ink-3">{perms.manageReason}</p>}

      <div className="grid grid-cols-[minmax(0,1fr)_20rem] items-start gap-6">
        <Sheet>
          {centers.isPending ? (
            <TableSkeleton rows={4} cols={3} />
          ) : centers.isError ? (
            <div className="p-5">
              <ApiErrorNotice error={centers.error} title="No se pudieron cargar los centros de costos." />
            </div>
          ) : all.length === 0 ? (
            <EmptyState
              title="Todavía no hay centros de costos"
              action={
                perms.canManage && (
                  <Button onClick={() => setDialog({ kind: 'new' })}>
                    <Plus size={16} />
                    Crear el primero
                  </Button>
                )
              }
            >
              Creá uno por área que quieras medir (Administración, Ventas, una sucursal). Después elegilo en las líneas de ingreso o gasto de cada
              asiento y mirá el estado de resultados por centro.
            </EmptyState>
          ) : (
            <>
              <table className="w-full">
                <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                  <tr>
                    <Th className="w-32">Código</Th>
                    <Th>Nombre</Th>
                    <Th className="w-28">Estado</Th>
                    {perms.canManage && (
                      <Th className="w-24">
                        <span className="sr-only">Acciones</span>
                      </Th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((c) => (
                    <tr key={c.id} className={cx(c.archived_at && 'text-ink-3')}>
                      <td className="px-4 py-2.5 font-medium tabular-nums">{c.code}</td>
                      <td className="px-4 py-2.5">{c.name}</td>
                      <td className="px-4 py-2.5">{c.archived_at ? <Badge>Archivado</Badge> : <Badge tone="ok">En uso</Badge>}</td>
                      {perms.canManage && (
                        <td className="px-3 py-1.5">
                          <div className="flex justify-end gap-1">
                            <Button variant="ghost" className="h-8 px-2" aria-label={`Editar ${c.code}`} title="Editar" onClick={() => setDialog({ kind: 'edit', center: c })}>
                              <Pencil size={15} />
                            </Button>
                            <Button
                              variant="ghost"
                              className="h-8 px-2"
                              aria-label={`${c.archived_at ? 'Desarchivar' : 'Archivar'} ${c.code}`}
                              title={c.archived_at ? 'Desarchivar' : 'Archivar'}
                              busy={archive.isPending && archive.variables?.id === c.id}
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
              <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm text-ink-2">
                <span>
                  {all.length - archivedCount} en uso{archivedCount > 0 ? `, ${archivedCount} archivados` : ''}.
                </span>
                {archivedCount > 0 && <Check label="Mostrar archivados" checked={showArchived} onChange={setShowArchived} />}
              </div>
            </>
          )}
        </Sheet>
        <div className="flex flex-col gap-6">
          <RequiredSetting />
          <Sheet className="p-5">
            <h2 className="font-semibold">Resultados por centro</h2>
            <p className="mt-1 text-sm text-ink-2">El estado de resultados muestra una columna por centro y otra para las líneas sin centro.</p>
            <Link
              to={`/contabilidad/reportes/resultados${qs({ from: `${year}-01-01`, to: todayIso(), por_centro: '1' })}`}
              className="mt-3 inline-block text-sm font-medium text-ledger hover:underline"
            >
              Ver el estado de resultados por centro
            </Link>
          </Sheet>
        </div>
      </div>

      <Modal open={dialog !== null} title={dialog?.kind === 'edit' ? `Editar centro ${dialog.center.code}` : 'Nuevo centro de costos'} onClose={() => setDialog(null)}>
        {dialog && <CenterForm key={dialog.kind === 'edit' ? dialog.center.id : 'new'} center={dialog.kind === 'edit' ? dialog.center : undefined} onDone={() => setDialog(null)} />}
      </Modal>
    </>
  )
}
