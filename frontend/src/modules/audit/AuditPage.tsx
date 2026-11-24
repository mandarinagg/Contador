import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Badge, Button, EmptyState, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { cx } from '../../lib/cx'
import { AUDIT_ACTION_LABELS, FIELD_LABELS, formatDateTime, formatFieldValue, plural, SECURITY_EVENT_LABELS } from '../../lib/format'
import { get } from '../../services/api'
import type { AuditLog, ChainVerification, Member, SecurityEvent } from '../../types/api'

const PAGE = 50

function Diff({ before, after }: { before: AuditLog['before']; after: AuditLog['after'] }) {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])]
  if (keys.length === 0) return null
  return (
    <table className="mt-2 text-sm">
      <tbody>
        {keys.map((k) => (
          <tr key={k}>
            <td className="py-0.5 pr-4 text-ink-3">{FIELD_LABELS[k] ?? k}</td>
            {before && (
              <td className="py-0.5 pr-3 text-debit line-through decoration-1">{formatFieldValue(k, before[k])}</td>
            )}
            <td className="py-0.5 text-ink">{formatFieldValue(k, after?.[k])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ChangesTab({ names }: { names: Map<string, string> }) {
  const logs = useInfiniteQuery({
    queryKey: ['audit', 'logs'],
    queryFn: ({ pageParam }) => get<AuditLog[]>(`/audit/logs?limit=${PAGE}${pageParam ? `&before_seq=${pageParam}` : ''}`),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1].seq : undefined),
  })
  if (logs.isPending) return <Skeleton className="m-5 h-24" />
  const rows = logs.data?.pages.flat() ?? []
  if (rows.length === 0) return <EmptyState title="Sin cambios registrados todavía" />
  return (
    <>
      <ol className="divide-y divide-line">
        {rows.map((log) => (
          <li key={log.id} className="grid grid-cols-[4rem_11rem_1fr] gap-4 px-5 py-3">
            <span className="text-sm text-ink-3">#{log.seq}</span>
            <span className="text-sm text-ink-2">{formatDateTime(log.occurred_at)}</span>
            <div className="min-w-0">
              <p>
                <span className="font-medium">{AUDIT_ACTION_LABELS[log.action] ?? log.action}</span>
                <span className="text-ink-2"> por {log.actor_user_id ? (names.get(log.actor_user_id) ?? 'usuario eliminado') : 'el sistema'}</span>
              </p>
              <Diff before={log.before} after={log.after} />
            </div>
          </li>
        ))}
      </ol>
      {logs.hasNextPage && (
        <div className="border-t border-line p-4">
          <Button variant="secondary" busy={logs.isFetchingNextPage} onClick={() => logs.fetchNextPage()}>
            Cargar registros anteriores
          </Button>
        </div>
      )}
    </>
  )
}

function SecurityTab({ names }: { names: Map<string, string> }) {
  const events = useQuery({ queryKey: ['audit', 'security'], queryFn: () => get<SecurityEvent[]>('/audit/security-events?limit=200') })
  if (events.isPending) return <Skeleton className="m-5 h-24" />
  if (!events.data?.length) return <EmptyState title="Sin eventos de seguridad" />
  return (
    <table className="w-full text-left">
      <thead className="border-b border-line bg-sunken text-sm text-ink-2">
        <tr>
          <th className="px-5 py-2.5 font-medium">Fecha</th>
          <th className="px-5 py-2.5 font-medium">Evento</th>
          <th className="px-5 py-2.5 font-medium">Usuario</th>
          <th className="px-5 py-2.5 font-medium">Origen</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {events.data.map((e) => (
          <tr key={e.id}>
            <td className="px-5 py-2.5 text-sm text-ink-2">{formatDateTime(e.occurred_at)}</td>
            <td className="px-5 py-2.5">
              <Badge tone={/failed|locked|blocked/.test(e.event_type) ? 'bad' : 'neutral'}>
                {SECURITY_EVENT_LABELS[e.event_type] ?? e.event_type}
              </Badge>
            </td>
            <td className="px-5 py-2.5 text-sm">{(e.user_id && names.get(e.user_id)) ?? e.email_attempted ?? '—'}</td>
            <td className="px-5 py-2.5 text-sm text-ink-2">{e.ip_address ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function AuditPage() {
  const [tab, setTab] = useState<'changes' | 'security'>('changes')
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['users'], queryFn: () => get<Member[]>('/users') })
  const chain = useQuery({ queryKey: ['audit', 'verify'], queryFn: () => get<ChainVerification>('/audit/verify') })
  const names = new Map((users.data ?? []).map((m) => [m.user.id, m.user.full_name]))

  return (
    <>
      <PageHeader
        title="Auditoría"
        description="Registro inalterable de cada cambio y de cada evento de seguridad. Nadie puede editarlo ni borrarlo desde la aplicación."
        actions={
          <Button variant="secondary" busy={chain.isFetching} onClick={() => qc.invalidateQueries({ queryKey: ['audit'] })}>
            <ShieldCheck size={16} />
            Verificar integridad
          </Button>
        }
      />
      {chain.data && (
        <p className="mb-4 flex items-center gap-2 text-sm text-ink-2">
          <Badge tone={chain.data.valid ? 'ok' : 'bad'}>{chain.data.valid ? 'Cadena íntegra' : 'Cadena alterada'}</Badge>
          {chain.data.valid
            ? `${plural(chain.data.checked, 'registro verificado', 'registros verificados')}.`
            : `Primer registro alterado: #${chain.data.first_broken_seq}.`}
        </p>
      )}
      <div role="tablist" className="mb-px flex gap-1">
        {(
          [
            ['changes', 'Cambios'],
            ['security', 'Seguridad'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            type="button"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cx(
              'rounded-t-sm border border-b-0 px-4 py-2 text-sm font-medium',
              tab === key ? 'border-line bg-surface text-ink' : 'border-transparent text-ink-2 hover:text-ink',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <Sheet className="rounded-tl-none">{tab === 'changes' ? <ChangesTab names={names} /> : <SecurityTab names={names} />}</Sheet>
    </>
  )
}
