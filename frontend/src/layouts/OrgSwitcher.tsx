import { useQuery } from '@tanstack/react-query'
import { Check, ChevronsUpDown, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Modal } from '../components/ui'
import { useToast } from '../components/ui/toast'
import { cx } from '../lib/cx'
import { ROLE_LABELS } from '../lib/format'
import { NewOrganizationForm } from '../modules/organization/NewOrganizationForm'
import { ApiError, get } from '../services/api'
import { useSession } from '../stores/session'
import type { Membership } from '../types/api'

const displayName = (m: { legal_name: string; trade_name: string | null }) => m.trade_name ?? m.legal_name

/**
 * Organización actual y selector. Con una sola organización no hay nada que elegir: el selector solo
 * aparece si el usuario puede dar de alta otra (es propietario de alguna), y entonces ofrece solo eso.
 */
export function OrgSwitcher() {
  const { me, switchOrg } = useSession()
  const navigate = useNavigate()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const memberships = useQuery({ queryKey: ['organizations'], queryFn: () => get<Membership[]>('/auth/organizations'), enabled: me !== null })

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!me) return null
  const list = memberships.data ?? []
  const canCreate = list.some((m) => m.role === 'owner')
  const name = displayName(me.organization)

  if (list.length <= 1 && !canCreate) {
    return (
      <p className="truncate text-sm text-ink-2" title={me.organization.legal_name}>
        {name}
      </p>
    )
  }

  const go = async (id: string) => {
    setOpen(false)
    if (id === me.organization.id) return
    try {
      await switchOrg(id)
      navigate('/')
    } catch (e) {
      toast('bad', e instanceof ApiError ? e.message : 'No se pudo cambiar de organización.')
    }
  }

  return (
    <div ref={root} className="relative min-w-0">
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`Organización: ${name}. Cambiar de organización`}
        title={me.organization.legal_name}
        onClick={() => setOpen((v) => !v)}
        className="-ml-1 flex w-full items-center gap-1 rounded-sm px-1 py-0.5 text-sm text-ink-2 hover:bg-surface/60 hover:text-ink"
      >
        <span className="truncate">{name}</span>
        <ChevronsUpDown size={14} className="shrink-0" aria-hidden />
      </button>
      {open && (
        <div role="menu" aria-label="Organizaciones" className="absolute left-0 z-20 mt-1 w-60 rounded-sm border border-line-strong bg-surface p-1 shadow-(--shadow-sheet)">
          {list.length > 1 && list.map((m) => (
            <button
              key={m.id}
              type="button"
              role="menuitemradio"
              aria-checked={m.id === me.organization.id}
              onClick={() => void go(m.id)}
              className={cx('flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-sunken', m.id === me.organization.id && 'font-medium')}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{displayName(m)}</span>
                <span className="block text-xs text-ink-3">{ROLE_LABELS[m.role] ?? m.role}</span>
              </span>
              {m.id === me.organization.id && <Check size={14} aria-hidden />}
            </button>
          ))}
          {canCreate && (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false)
                setCreating(true)
              }}
              className={cx('flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm text-ledger hover:bg-sunken', list.length > 1 && 'mt-1 border-t border-line pt-2')}
            >
              <Plus size={14} aria-hidden />
              Nueva organización
            </button>
          )}
        </div>
      )}
      <Modal open={creating} title="Nueva organización" onClose={() => setCreating(false)}>
        {creating && (
          <NewOrganizationForm
            onDone={() => setCreating(false)}
            onSwitch={async (org) => {
              await switchOrg(org.id)
              setCreating(false)
              navigate('/')
            }}
          />
        )}
      </Modal>
    </div>
  )
}
