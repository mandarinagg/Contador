/**
 * Marco de todas las pantallas de finanzas: el selector de contexto (Empresa / Personal /
 * Consolidado) siempre visible y la franja que dice en qué contexto se está operando
 * (BR-FIN-01). El contexto va en la URL; acá solo se recuerda cuál abrir la próxima vez.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Building2, Layers, LockKeyhole, Plus } from 'lucide-react'
import { type ReactNode, useEffect } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router'
import { Button, EmptyState, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { businessContextLabel } from '../../lib/format'
import { post } from '../../services/api'
import { useSession } from '../../stores/session'
import { errorMessage } from './forms'
import { financeKeys, preferredContext, rememberContext, useActiveContext, useContexts } from './data'
import type { FinanceContext } from './types'

/** Sección actual dentro de `/finanzas/:cid/<sección>` para conservarla al cambiar de contexto. */
function useSection(): string {
  const { pathname } = useLocation()
  const match = /^\/finanzas\/[^/]+\/([^/]+)/.exec(pathname)
  return match ? match[1] : ''
}

function useCreatePersonal() {
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: () => post<FinanceContext>('/finance/contexts/personal'),
    onSuccess: (ctx) => {
      qc.setQueryData<FinanceContext[]>(financeKeys.contexts(), (old) => [...(old ?? []), ctx])
      qc.invalidateQueries({ queryKey: financeKeys.consolidated() })
      toast('ok', 'Tu espacio personal está listo. Solo vos podés verlo.')
      navigate(`/finanzas/${ctx.id}/cuentas`)
    },
    onError: (e) => toast('bad', errorMessage(e, 'No se pudo crear el espacio personal.')),
  })
}

function TabLink({ to, active, tone, children }: { to: string; active: boolean; tone: 'business' | 'personal' | 'neutral'; children: ReactNode }) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      className={cx(
        'relative -mb-px flex items-center gap-2 rounded-t-md border border-b-0 px-4 py-2 text-base transition-colors',
        active
          ? cx(
              'bg-surface font-semibold text-ink',
              tone === 'business' && 'border-line border-t-ledger shadow-[inset_0_3px_0_var(--ledger)]',
              tone === 'personal' && 'border-line shadow-[inset_0_3px_0_var(--personal)]',
              tone === 'neutral' && 'border-line shadow-[inset_0_3px_0_var(--ink-3)]',
            )
          : 'border-transparent text-ink-2 hover:bg-surface/60 hover:text-ink',
      )}
    >
      {children}
    </Link>
  )
}

/** Selector permanente de contexto. `current` = id del contexto activo o "consolidado". */
export function ContextSwitcher({ current }: { current: string }) {
  const contexts = useContexts()
  const { me } = useSession()
  const section = useSection()
  const createPersonal = useCreatePersonal()
  if (!contexts.data || !me) return <Skeleton className="h-10 w-96" />
  const business = contexts.data.find((c) => c.kind === 'business')
  const personal = contexts.data.find((c) => c.kind === 'personal')
  const target = (c: FinanceContext) => `/finanzas/${c.id}${section ? `/${section}` : ''}`

  return (
    <nav aria-label="Contexto financiero" className="flex items-end gap-1 border-b border-line">
      {business && (
        <TabLink to={target(business)} active={current === business.id} tone="business">
          <Building2 size={15} className={current === business.id ? 'text-ledger' : ''} aria-hidden />
          {businessContextLabel(me.organization.legal_form)}
        </TabLink>
      )}
      {personal ? (
        <TabLink to={target(personal)} active={current === personal.id} tone="personal">
          <LockKeyhole size={15} className={current === personal.id ? 'text-personal' : ''} aria-hidden />
          Personal
          <span className="text-sm font-normal text-ink-3">solo vos</span>
        </TabLink>
      ) : (
        <button
          type="button"
          onClick={() => createPersonal.mutate()}
          disabled={createPersonal.isPending}
          className="mb-1 flex items-center gap-1.5 rounded-sm px-3 py-1.5 text-sm font-medium text-personal hover:bg-personal-soft disabled:opacity-60"
        >
          <Plus size={14} aria-hidden />
          Crear mi espacio personal
        </button>
      )}
      <TabLink to="/finanzas/consolidado" active={current === 'consolidado'} tone="neutral">
        <Layers size={15} aria-hidden />
        Consolidado
      </TabLink>
    </nav>
  )
}

/** Franja que dice dónde se está operando. Visible en todas las pantallas del contexto. */
function ContextBanner({ context, canWrite }: { context: FinanceContext; canWrite: boolean }) {
  const { me } = useSession()
  const personal = context.kind === 'personal'
  return (
    <div
      role="note"
      aria-label="Contexto activo"
      className={cx(
        'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-b-md border border-t-0 border-line px-4 py-2.5 text-sm',
        personal ? 'bg-personal-soft' : 'bg-ledger-soft',
      )}
    >
      <span className={cx('font-semibold', personal ? 'text-personal' : 'text-ledger')}>
        {personal ? 'Finanzas personales' : `Finanzas de ${me?.organization.trade_name ?? me?.organization.legal_name}`}
      </span>
      <span className="text-ink-2">
        {personal
          ? 'Privadas: nadie más las ve, tampoco administradores ni el contador.'
          : 'Lo que cargues acá es de la empresa y lo ven quienes tienen acceso a sus finanzas.'}
      </span>
      {!canWrite && <span className="ml-auto font-medium text-ink-2">Solo lectura</span>}
    </div>
  )
}

export function FinanceLayout() {
  const { active, loading, missing } = useActiveContext()
  const { me } = useSession()

  useEffect(() => {
    if (active && me) rememberContext(me.user.id, active.cid)
  }, [active, me])

  if (loading) return <Skeleton className="h-24 w-full" />
  if (missing || !active) {
    // 404 a propósito: un contexto personal ajeno no existe para este usuario (D-024).
    return (
      <EmptyState title="Ese contexto financiero no existe" action={<Link className="font-medium text-ledger hover:underline" to="/finanzas">Ir a mis finanzas</Link>}>
        La dirección no corresponde a ningún contexto al que tengas acceso.
      </EmptyState>
    )
  }
  return (
    <>
      <div className="mb-7">
        <ContextSwitcher current={active.cid} />
        <ContextBanner context={active.context} canWrite={active.canWrite} />
      </div>
      <Outlet context={active} />
    </>
  )
}

/** `/finanzas`: abre el contexto preferido o invita a crear el personal si no hay ninguno. */
export function FinanceIndex() {
  const contexts = useContexts()
  const { me } = useSession()
  const createPersonal = useCreatePersonal()
  if (contexts.isPending || !me) return <Skeleton className="h-24 w-full" />
  if (contexts.isError) return <EmptyState title="No se pudieron cargar tus finanzas">{errorMessage(contexts.error)}</EmptyState>
  const target = preferredContext(me.user.id, contexts.data)
  if (target) return <Navigate to={`/finanzas/${target.id}`} replace />
  return (
    <EmptyState
      title="Todavía no tenés un espacio de finanzas"
      action={
        <Button busy={createPersonal.isPending} onClick={() => createPersonal.mutate()}>
          <LockKeyhole size={16} />
          Crear mi espacio personal
        </Button>
      }
    >
      Tu rol no incluye las finanzas de la empresa. Podés llevar tus finanzas personales en un espacio privado: solo vos lo
      vas a ver.
    </EmptyState>
  )
}
