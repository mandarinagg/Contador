/**
 * Árbol del plan de cuentas (sin componentes): armado desde la lista plana, orden por código
 * segmento a segmento ("2" antes que "10"), filas visibles según lo expandido y la búsqueda,
 * y el código sugerido para una subcuenta nueva.
 */
import type { LedgerAccount } from './types'

export interface TreeNode {
  account: LedgerAccount
  depth: number
  children: TreeNode[]
  parent: TreeNode | null
}

/** Compara códigos jerárquicos por segmentos numéricos: 1.01.02 < 1.01.10 < 2 < 10. */
export function compareCodes(a: string, b: string): number {
  const x = a.split('.').map(Number)
  const y = b.split('.').map(Number)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if (x[i] === undefined) return -1
    if (y[i] === undefined) return 1
    if (x[i] !== y[i]) return x[i] - y[i]
  }
  return 0
}

/** Arma el árbol desde la lista plana (`?flat=true`). Una cuenta con padre desconocido queda en la raíz. */
export function buildTree(accounts: LedgerAccount[]): TreeNode[] {
  const nodes = new Map<string, TreeNode>()
  for (const a of accounts) nodes.set(a.id, { account: a, depth: 0, children: [], parent: null })
  const roots: TreeNode[] = []
  for (const node of nodes.values()) {
    const parent = node.account.parent_id ? nodes.get(node.account.parent_id) : undefined
    if (parent) {
      node.parent = parent
      parent.children.push(node)
    } else roots.push(node)
  }
  const sort = (list: TreeNode[], depth: number) => {
    list.sort((p, q) => compareCodes(p.account.code, q.account.code))
    for (const n of list) {
      n.depth = depth
      sort(n.children, depth + 1)
    }
  }
  sort(roots, 0)
  return roots
}

/** Recorrido en orden (preorden) de todo el árbol. */
export function flatten(roots: TreeNode[]): TreeNode[] {
  const out: TreeNode[] = []
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      out.push(n)
      walk(n.children)
    }
  }
  walk(roots)
  return out
}

/** Texto sin tildes ni mayúsculas, para buscar "credito" y encontrar "CRÉDITOS". */
export const fold = (text: string) =>
  text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

/** Coincide si el código empieza con la búsqueda o el nombre la contiene (sin tildes). */
export function matchesAccount(account: Pick<LedgerAccount, 'code' | 'name'>, query: string): boolean {
  const q = fold(query.trim())
  if (!q) return true
  return account.code.startsWith(q) || fold(account.name).includes(q) || fold(`${account.code} ${account.name}`).startsWith(q)
}

export interface VisibleRow {
  node: TreeNode
  expanded: boolean
  hasChildren: boolean
  /** La fila coincide con la búsqueda (las demás son sus ancestros). */
  match: boolean
}

/**
 * Filas a mostrar. Sin búsqueda: las raíces y los hijos de lo expandido. Con búsqueda: las
 * cuentas que coinciden y sus ancestros, todo expandido para que se vean.
 */
export function visibleRows(
  roots: TreeNode[],
  expanded: ReadonlySet<string>,
  { query = '', hideArchived = false }: { query?: string; hideArchived?: boolean } = {},
): VisibleRow[] {
  const out: VisibleRow[] = []
  const searching = query.trim() !== ''
  const keep = (n: TreeNode) => !hideArchived || !n.account.archived_at
  if (!searching) {
    const walk = (list: TreeNode[]) => {
      for (const n of list) {
        if (!keep(n)) continue
        const kids = n.children.filter(keep)
        const isOpen = expanded.has(n.account.id)
        out.push({ node: n, expanded: isOpen, hasChildren: kids.length > 0, match: false })
        if (isOpen) walk(kids)
      }
    }
    walk(roots)
    return out
  }
  const include = new Set<string>()
  const matched = new Set<string>()
  for (const n of flatten(roots)) {
    if (!keep(n) || !matchesAccount(n.account, query)) continue
    matched.add(n.account.id)
    for (let p: TreeNode | null = n; p; p = p.parent) include.add(p.account.id)
  }
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (!include.has(n.account.id)) continue
      const kids = n.children.filter((c) => include.has(c.account.id))
      out.push({ node: n, expanded: kids.length > 0, hasChildren: n.children.some(keep), match: matched.has(n.account.id) })
      walk(kids)
    }
  }
  walk(roots)
  return out
}

/** Ids de las cuentas hasta cierta profundidad (para "expandir dos niveles"). */
export function idsToDepth(roots: TreeNode[], depth: number): Set<string> {
  return new Set(
    flatten(roots)
      .filter((n) => n.depth < depth && n.children.length > 0)
      .map((n) => n.account.id),
  )
}

/**
 * Segmento sugerido para una subcuenta nueva: el siguiente al mayor de sus hermanas, con el
 * mismo ancho (01, 02… → 03). Sin hermanas, "01" bajo un padre y "1" en la raíz.
 */
export function suggestChildSegment(parentCode: string | null, siblingCodes: string[]): string {
  const segments = siblingCodes.map((c) => c.split('.').at(-1) ?? '')
  if (segments.length === 0) return parentCode ? '01' : '1'
  const width = Math.max(...segments.map((s) => s.length))
  const next = Math.max(...segments.map(Number)) + 1
  return String(next).padStart(width, '0')
}

/** Cuentas imputables y no archivadas en orden de código (las que reciben líneas). */
export function postableAccounts(accounts: LedgerAccount[]): LedgerAccount[] {
  return accounts.filter((a) => a.is_postable && !a.archived_at).sort((a, b) => compareCodes(a.code, b.code))
}
