import { Building2, Home, LogOut, ScrollText, UserRound, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router'
import { cx } from '../lib/cx'
import { ROLE_LABELS } from '../lib/format'
import { useSession } from '../stores/session'

interface NavItem {
  to: string
  label: string
  icon: ReactNode
  permission?: string
}

const NAV: { group: string; items: NavItem[] }[] = [
  { group: 'General', items: [{ to: '/', label: 'Inicio', icon: <Home size={16} /> }] },
  {
    group: 'Empresa',
    items: [
      { to: '/empresa', label: 'Datos de la empresa', icon: <Building2 size={16} />, permission: 'organization.read' },
    ],
  },
  {
    group: 'Administración',
    items: [
      { to: '/usuarios', label: 'Usuarios y roles', icon: <Users size={16} />, permission: 'users.read' },
      { to: '/auditoria', label: 'Auditoría', icon: <ScrollText size={16} />, permission: 'audit.read' },
    ],
  },
]

function BrandMark() {
  // Cinco pétalos: la flor del lapacho, reducida a una marca geométrica.
  return (
    <svg viewBox="0 0 24 24" className="size-6 text-lapacho" aria-hidden>
      {[0, 72, 144, 216, 288].map((deg) => (
        <ellipse key={deg} cx="12" cy="6.5" rx="3.2" ry="5" fill="currentColor" opacity="0.88" transform={`rotate(${deg} 12 12)`} />
      ))}
      <circle cx="12" cy="12" r="2.2" fill="var(--surface)" />
    </svg>
  )
}

export function AppLayout() {
  const { me, can, logout } = useSession()
  if (!me) return null

  return (
    <div className="flex h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-sunken">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
          <BrandMark />
          <div className="min-w-0">
            <p className="font-semibold tracking-tight">Contador AI</p>
            <p className="truncate text-sm text-ink-2" title={me.organization.legal_name}>
              {me.organization.trade_name ?? me.organization.legal_name}
            </p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-2" aria-label="Principal">
          {NAV.map(({ group, items }) => {
            const visible = items.filter((i) => !i.permission || can(i.permission))
            if (visible.length === 0) return null
            return (
              <div key={group} className="mb-4">
                <p className="px-2 pb-1 text-xs font-medium text-ink-3">{group}</p>
                <ul>
                  {visible.map((item) => (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.to === '/'}
                        className={({ isActive }) =>
                          cx(
                            'relative flex items-center gap-2.5 rounded-sm px-2 py-1.5 transition-colors',
                            isActive
                              ? 'bg-surface font-medium text-ink shadow-(--shadow-sheet) before:absolute before:inset-y-1.5 before:-left-3 before:w-0.75 before:rounded-r-sm before:bg-lapacho'
                              : 'text-ink-2 hover:bg-surface/60 hover:text-ink',
                          )
                        }
                      >
                        {item.icon}
                        {item.label}
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </nav>

        <div className="border-t border-line px-3 py-3">
          <NavLink
            to="/cuenta"
            className={({ isActive }) =>
              cx('flex items-center gap-2.5 rounded-sm px-2 py-1.5', isActive ? 'bg-surface' : 'hover:bg-surface/60')
            }
          >
            <span className="grid size-7 place-items-center rounded-full bg-ledger-soft text-ledger">
              <UserRound size={15} />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{me.user.full_name}</span>
              <span className="block text-xs text-ink-3">{ROLE_LABELS[me.role] ?? me.role}</span>
            </span>
          </NavLink>
          <button
            type="button"
            onClick={() => void logout()}
            className="mt-1 flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-ink-2 hover:bg-surface/60 hover:text-ink"
          >
            <LogOut size={16} />
            Cerrar sesión
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-10 py-9">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
