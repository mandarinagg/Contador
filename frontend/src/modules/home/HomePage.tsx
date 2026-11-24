import { useQuery } from '@tanstack/react-query'
import { CircleCheck, CircleDashed } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Badge, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { LEGAL_FORM_LABELS, plural } from '../../lib/format'
import { get } from '../../services/api'
import { useSession } from '../../stores/session'
import type { ChainVerification, Member, Organization } from '../../types/api'
import { RecurringDueBanner } from '../accounting/recurring/RecurringDueBanner'

function ChecklistItem({ done, title, children, action }: { done: boolean; title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <li className="flex items-start gap-3 px-5 py-4">
      {done ? (
        <CircleCheck size={18} className="mt-0.5 shrink-0 text-ledger" aria-label="Hecho" />
      ) : (
        <CircleDashed size={18} className="mt-0.5 shrink-0 text-ink-3" aria-label="Pendiente" />
      )}
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 max-w-[65ch] text-sm text-ink-2">{children}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </li>
  )
}

export function HomePage() {
  const { me, can } = useSession()
  const org = useQuery({ queryKey: ['organization'], queryFn: () => get<Organization>('/organization') })
  const members = useQuery({
    queryKey: ['users'],
    queryFn: () => get<Member[]>('/users'),
    enabled: can('users.read'),
  })
  const chain = useQuery({
    queryKey: ['audit', 'verify'],
    queryFn: () => get<ChainVerification>('/audit/verify'),
    enabled: can('audit.read'),
  })
  if (!me) return null
  const firstName = me.user.full_name.split(' ')[0]

  return (
    <>
      <PageHeader
        title={`Hola, ${firstName}`}
        description="Este es el estado de la configuración de tu empresa en Contador AI. Los indicadores financieros aparecen cuando cargues cuentas y movimientos (fase 2)."
      />
      <RecurringDueBanner className="mb-6" />

      <div className="grid grid-cols-[1fr_18rem] gap-6">
        <Sheet>
          <h2 className="border-b border-line px-5 py-3.5 font-semibold">Puesta en marcha</h2>
          {org.isPending ? (
            <div className="flex flex-col gap-3 p-5">
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : (
            <ol className="divide-y divide-line">
              <ChecklistItem done title="Empresa registrada">
                {org.data?.legal_name} — {LEGAL_FORM_LABELS[org.data?.legal_form ?? 'OTRA']}.
              </ChecklistItem>
              <ChecklistItem
                done={Boolean(org.data?.ruc)}
                title="RUC de la empresa"
                action={
                  !org.data?.ruc && can('organization.manage') ? (
                    <Link to="/empresa" className="text-sm font-medium text-ledger hover:underline">
                      Cargar RUC
                    </Link>
                  ) : undefined
                }
              >
                {org.data?.ruc
                  ? `${org.data.ruc}-${org.data.ruc_check_digit}`
                  : 'Cargalo tal como figura en la constancia de RUC de la DNIT. Se valida el dígito verificador.'}
              </ChecklistItem>
              {can('users.read') && (
                <ChecklistItem
                  done={(members.data?.length ?? 0) > 1}
                  title="Equipo"
                  action={
                    can('users.manage') ? (
                      <Link to="/usuarios" className="text-sm font-medium text-ledger hover:underline">
                        Gestionar usuarios
                      </Link>
                    ) : undefined
                  }
                >
                  {(members.data?.length ?? 0) > 1
                    ? `${members.data?.length} usuarios con acceso.`
                    : 'Por ahora solo vos tenés acceso. Podés sumar a tu contador con el rol Contador.'}
                </ChecklistItem>
              )}
              <ChecklistItem done={false} title="Régimen tributario">
                Pendiente de verificación documental. Se configura en el módulo de tributación (fase 4); el sistema no asume
                impuestos ni vencimientos hasta entonces.
              </ChecklistItem>
            </ol>
          )}
        </Sheet>

        <div className="flex flex-col gap-6">
          {can('audit.read') && (
            <Sheet className="p-5">
              <h2 className="font-semibold">Integridad de la auditoría</h2>
              {chain.isPending ? (
                <Skeleton className="mt-3 h-5 w-24" />
              ) : chain.data ? (
                <>
                  <p className="mt-2">
                    <Badge tone={chain.data.valid ? 'ok' : 'bad'}>{chain.data.valid ? 'Íntegra' : 'Alterada'}</Badge>
                  </p>
                  <p className="mt-2 text-sm text-ink-2">
                    {chain.data.valid
                      ? `${plural(chain.data.checked, 'registro verificado', 'registros verificados')} con su cadena de hashes.`
                      : `El registro ${chain.data.first_broken_seq} no coincide con su hash. Revisá la auditoría.`}
                  </p>
                </>
              ) : (
                <p className="mt-2 text-sm text-debit">No se pudo verificar.</p>
              )}
            </Sheet>
          )}
          <Sheet className="p-5">
            <h2 className="font-semibold">Tu acceso</h2>
            <p className="mt-2 text-sm text-ink-2">
              {plural(me.permissions.length, 'permiso', 'permisos')} en {me.organization.trade_name ?? me.organization.legal_name}.
            </p>
            <Link to="/cuenta" className="mt-3 inline-block text-sm font-medium text-ledger hover:underline">
              Ver mi cuenta
            </Link>
          </Sheet>
        </div>
      </div>
    </>
  )
}
