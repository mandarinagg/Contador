/**
 * Acceso a la API de finanzas: claves de caché, consultas y el contexto activo.
 *
 * El contexto activo vive en la URL (`/finanzas/:cid/...`): recargar no lo pierde y no
 * hace falta guardarlo. Lo único que se recuerda en el navegador es la **preferencia**
 * de qué contexto abrir al entrar a Finanzas (un id, no datos de negocio).
 */
import { useQuery } from '@tanstack/react-query'
import { useOutletContext, useParams } from 'react-router'
import { get, qs } from '../../services/api'
import { useSession } from '../../stores/session'
import type { Account, Category, Counterparty, FinanceContext } from './types'

const PAGE = 200

/** Secciones de `/finanzas/:cid/<slug>`, en el orden del menú. */
export const FINANCE_SECTIONS = [
  { slug: '', label: 'Resumen' },
  { slug: 'movimientos', label: 'Movimientos' },
  { slug: 'cuentas', label: 'Cuentas' },
  { slug: 'importar', label: 'Importar extracto' },
  { slug: 'categorias', label: 'Categorías' },
  { slug: 'contrapartes', label: 'Contrapartes' },
] as const

export const financeKeys = {
  all: ['finance'] as const,
  contexts: () => ['finance', 'contexts'] as const,
  context: (cid: string) => ['finance', cid] as const,
  accounts: (cid: string) => ['finance', cid, 'accounts'] as const,
  categories: (cid: string) => ['finance', cid, 'categories'] as const,
  counterparties: (cid: string) => ['finance', cid, 'counterparties'] as const,
  transactions: (cid: string) => ['finance', cid, 'transactions'] as const,
  summary: (cid: string) => ['finance', cid, 'summary'] as const,
  imports: (cid: string) => ['finance', cid, 'imports'] as const,
  consolidated: () => ['finance', 'consolidated'] as const,
}

/** Recorre todas las páginas de un listado por cursor (`before` = id del último). */
export async function fetchAll<T extends { id: string }>(path: string, params: Record<string, string | boolean> = {}): Promise<T[]> {
  const out: T[] = []
  let before: string | undefined
  for (;;) {
    const page = await get<T[]>(`${path}${qs({ ...params, limit: PAGE, before })}`)
    out.push(...page)
    if (page.length < PAGE) return out
    before = page[page.length - 1].id
  }
}

export function useContexts() {
  return useQuery({ queryKey: financeKeys.contexts(), queryFn: () => get<FinanceContext[]>('/finance/contexts'), staleTime: 60_000 })
}

/** Incluye las archivadas: los movimientos viejos las siguen nombrando. */
export function useAccounts(cid: string) {
  return useQuery({
    queryKey: financeKeys.accounts(cid),
    queryFn: () => fetchAll<Account>(`/finance/contexts/${cid}/accounts`, { include_archived: true }),
  })
}

export function useCategories(cid: string) {
  return useQuery({
    queryKey: financeKeys.categories(cid),
    queryFn: () => fetchAll<Category>(`/finance/contexts/${cid}/categories`, { include_archived: true }),
  })
}

export function useCounterparties(cid: string) {
  return useQuery({
    enabled: Boolean(cid),
    queryKey: [...financeKeys.counterparties(cid), 'all'],
    queryFn: () => fetchAll<Counterparty>(`/finance/contexts/${cid}/counterparties`, { include_archived: true }),
  })
}

const PREF_KEY = (userId: string) => `contador.finanzas.contexto.${userId}`

export function rememberContext(userId: string, cid: string) {
  try {
    localStorage.setItem(PREF_KEY(userId), cid)
  } catch {
    // Sin almacenamiento local la preferencia simplemente no se recuerda.
  }
}

export function preferredContext(userId: string, contexts: FinanceContext[]): FinanceContext | undefined {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(PREF_KEY(userId))
  } catch {
    saved = null
  }
  return contexts.find((c) => c.id === saved) ?? contexts.find((c) => c.kind === 'business') ?? contexts[0]
}

export interface ActiveContext {
  context: FinanceContext
  cid: string
  /** Puede cargar, editar, anular, importar. Personal: solo su dueño (y nadie más lo ve). */
  canWrite: boolean
  /** Texto que explica por qué no puede escribir (para botones deshabilitados). */
  readOnlyReason: string
}

/** Resuelve el contexto de la URL contra los visibles. `undefined` mientras carga o si no existe. */
export function useActiveContext(): { active: ActiveContext | undefined; loading: boolean; missing: boolean } {
  const { cid } = useParams()
  const { me, can } = useSession()
  const contexts = useContexts()
  const context = contexts.data?.find((c) => c.id === cid)
  if (!context || !me) return { active: undefined, loading: contexts.isPending, missing: contexts.isSuccess && !context }
  const canWrite = context.kind === 'personal' ? context.owner_user_id === me.user.id : can('finance.manage')
  return {
    active: {
      context,
      cid: context.id,
      canWrite,
      readOnlyReason: canWrite ? '' : 'Tu rol puede consultar las finanzas de la empresa, pero no modificarlas.',
    },
    loading: false,
    missing: false,
  }
}

/** Contexto ya resuelto por `FinanceLayout` (que solo muestra las pantallas cuando existe). */
export function useFinance(): ActiveContext {
  return useOutletContext<ActiveContext>()
}
