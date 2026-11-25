/**
 * Impuestos → Marangatu (BOT_MARANGATU.md §7, D-127 a D-133): el interruptor general del bot, la
 * clave de Marangatu del RUC de la empresa, la etapa de cada tipo de tarea, el reconocimiento
 * y las últimas corridas con sus pasos. En B1 el bot solo mira: nunca llena ni presenta nada.
 * La clave se lee del campo al enviar, va al servicio y se borra del campo: no queda en el
 * estado de la pantalla ni en la caché de consultas.
 */
import { useMutation } from '@tanstack/react-query'
import { type FormEvent, useRef, useState } from 'react'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { formatDateTime } from '../../lib/format'
import { api, ApiError, getBlob, post, put } from '../../services/api'
import { ApiErrorNotice, ReadOnlyHint } from '../finance/components'
import {
  type BotRun,
  type BotStep,
  type BotVerify,
  RUN_STATUS_LABELS,
  STAGE_LABELS,
  TASK_LABELS,
  type BotCredentials,
  type BotSettings,
  useBotCredentials,
  useBotPerms,
  useBotRun,
  useBotRuns,
  useBotSettings,
  useInvalidateBot,
} from './marangatuData'

export function MarangatuPage() {
  const settings = useBotSettings()
  const perms = useBotPerms()
  return (
    <>
      <PageHeader
        title="Marangatu"
        description="El bot que entra a Marangatu por vos. Por ahora solo reconoce el portal: navega y captura pantallas, pero no llena ni presenta nada."
      />
      {settings.isError ? (
        <ApiErrorNotice error={settings.error} title="No se pudo leer el estado del bot." />
      ) : !settings.data ? (
        <Skeleton className="h-80" />
      ) : (
        <div className="flex max-w-4xl flex-col gap-6">
          <SwitchSection settings={settings.data} canManage={perms.canManage} canVerify={perms.canVerify} reason={perms.verifyReason} />
          <PasswordSection canVerify={perms.canVerify} reason={perms.verifyReason} />
          <StagesSection settings={settings.data} />
          <ReconnaissanceSection canVerify={perms.canVerify} reason={perms.verifyReason} />
          <RunsSection />
        </div>
      )}
    </>
  )
}

// --- Interruptor -------------------------------------------------------------------------

function SwitchSection({ settings, canManage, canVerify, reason }: { settings: BotSettings; canManage: boolean; canVerify: boolean; reason: string }) {
  const toast = useToast()
  const invalidate = useInvalidateBot()
  const [confirming, setConfirming] = useState(false)
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => put<BotSettings>('/marangatu/settings', { bot_enabled: enabled }),
    onSuccess: (s) => {
      invalidate()
      setConfirming(false)
      toast('ok', s.bot_enabled ? 'Bot encendido.' : 'Bot apagado.')
    },
  })
  const on = settings.bot_enabled
  // Apagar pide `tax.manage` (frenar siempre es seguro); encender, `tax.verify`.
  const allowed = on ? canManage : canVerify

  return (
    <Sheet className="p-5">
      <div className="flex items-start justify-between gap-6">
        <div>
          <h2 className="font-semibold">
            Bot {on ? 'encendido' : 'apagado'} <Badge tone={on ? 'ok' : 'neutral'}>{on ? 'Encendido' : 'Apagado'}</Badge>
          </h2>
          <p className="mt-1 max-w-[62ch] text-ink-2">
            {on
              ? 'El bot puede trabajar en Marangatu con la clave guardada. Apagalo cuando quieras: frena todo de inmediato.'
              : 'Mientras esté apagado, el bot no entra a Marangatu ni hace nada. Encendelo solo si querés que trabaje con la clave guardada.'}
          </p>
          {!allowed && <ReadOnlyHint reason={on ? 'Tu rol no puede apagar el bot.' : reason} />}
        </div>
        <Button
          variant={on ? 'secondary' : 'primary'}
          disabled={!allowed}
          busy={toggle.isPending && !confirming}
          onClick={() => (on ? toggle.mutate(false) : setConfirming(true))}
        >
          {on ? 'Apagar el bot' : 'Encender el bot'}
        </Button>
      </div>
      {toggle.isError && !confirming && (
        <div className="mt-3">
          <ApiErrorNotice error={toggle.error} />
        </div>
      )}
      <Modal open={confirming} title="Encender el bot" onClose={() => setConfirming(false)}>
        <div className="flex flex-col gap-4 p-5">
          <p>El bot va a poder entrar a Marangatu con la clave guardada de tu RUC. En esta etapa solo navega y captura pantallas: no llena ni presenta nada. ¿Encenderlo?</p>
          {toggle.isError && <ApiErrorNotice error={toggle.error} />}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Cancelar
            </Button>
            <Button busy={toggle.isPending} onClick={() => toggle.mutate(true)}>
              Sí, encender
            </Button>
          </div>
        </div>
      </Modal>
    </Sheet>
  )
}

// --- Clave -------------------------------------------------------------------------------

function PasswordSection({ canVerify, reason }: { canVerify: boolean; reason: string }) {
  const credentials = useBotCredentials()
  const toast = useToast()
  const invalidate = useInvalidateBot()
  const input = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const [deleting, setDeleting] = useState(false)

  const remove = useMutation({
    mutationFn: () => api<void>('DELETE', '/marangatu/credentials'),
    onSuccess: () => {
      invalidate()
      setDeleting(false)
      toast('ok', 'Clave borrada.')
    },
  })

  // La clave vive solo en el campo y en esta variable local: se vacía el campo antes de esperar
  // la respuesta. No pasa por `useState` ni por `useMutation` (que guardaría las variables).
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const field = input.current
    if (!field || field.value === '') return
    let password: string | null = field.value
    field.value = ''
    setSaving(true)
    setError(undefined)
    try {
      await put<BotCredentials>('/marangatu/credentials', { password })
      invalidate()
      toast('ok', 'Clave guardada.')
    } catch (err) {
      setError(err)
    } finally {
      password = null
      setSaving(false)
    }
  }

  const data = credentials.data
  return (
    <Sheet className="p-5">
      <h2 className="font-semibold">Clave de Marangatu</h2>
      {credentials.isError ? (
        <ApiErrorNotice error={credentials.error} title="No se pudo leer el estado de la clave." />
      ) : !data ? (
        <Skeleton className="mt-3 h-20" />
      ) : (
        <div className="mt-2 flex flex-col gap-3">
          <p data-testid="password-status">
            {data.ruc === null ? (
              'La empresa todavía no tiene RUC cargado: cargalo en el perfil fiscal para poder guardar la clave.'
            ) : data.has_password ? (
              <>
                Clave guardada para el RUC <span className="tabular-nums">{data.ruc}</span>.
              </>
            ) : (
              <>
                No hay clave guardada para el RUC <span className="tabular-nums">{data.ruc}</span>.
              </>
            )}
          </p>
          {!data.store_available && (
            <Notice tone="bad" title="No se puede usar el almacén de credenciales del sistema">
              La clave no se puede guardar ni leer hasta que el sistema operativo lo permita.
            </Notice>
          )}
          <p className="max-w-[62ch] text-sm text-ink-3">La clave se guarda en el almacén de credenciales de tu sistema, no en la base de datos. CONTADOR AI nunca la muestra.</p>
          <form onSubmit={submit} noValidate className="flex max-w-md flex-col gap-3">
            <Field label="Clave de Marangatu" hint="Al guardarla se reemplaza la anterior.">
              {(p) => <Input {...p} ref={input} type="password" autoComplete="off" disabled={!canVerify || data.ruc === null} />}
            </Field>
            {error != null && <ApiErrorNotice error={error} title="No se pudo guardar la clave." />}
            <div className="flex gap-2">
              <Button type="submit" busy={saving} disabled={!canVerify || data.ruc === null}>
                Guardar la clave
              </Button>
              <Button type="button" variant="danger" disabled={!canVerify || !data.has_password} onClick={() => setDeleting(true)}>
                Borrar la clave
              </Button>
            </div>
            {!canVerify && <ReadOnlyHint reason={reason} />}
          </form>
        </div>
      )}
      <Modal open={deleting} title="Borrar la clave" onClose={() => setDeleting(false)}>
        <div className="flex flex-col gap-4 p-5">
          <p>Se borra la clave de Marangatu del almacén del sistema. El bot no va a poder entrar hasta que guardes otra. ¿Borrarla?</p>
          {remove.isError && <ApiErrorNotice error={remove.error} />}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleting(false)}>
              Cancelar
            </Button>
            <Button variant="danger" busy={remove.isPending} onClick={() => remove.mutate()}>
              Sí, borrar
            </Button>
          </div>
        </div>
      </Modal>
    </Sheet>
  )
}

// --- Etapas ------------------------------------------------------------------------------

function StagesSection({ settings }: { settings: BotSettings }) {
  return (
    <Sheet>
      <h2 className="border-b border-line px-5 py-3.5 font-semibold">Etapa de cada tarea</h2>
      <ul className="divide-y divide-line">
        {Object.entries(settings.stages).map(([task, stage]) => (
          <li key={task} className="flex items-center justify-between gap-4 px-5 py-2.5">
            <span>{TASK_LABELS[task] ?? task}</span>
            <Badge tone={stage === 'habilitada' ? 'ok' : 'neutral'}>{STAGE_LABELS[stage] ?? stage}</Badge>
          </li>
        ))}
      </ul>
      <p className="border-t border-line px-5 py-3 text-sm text-ink-3">
        Las etapas se muestran, todavía no se cambian desde acá.
        {settings.catalog_provisional && ' El catálogo de pantallas es provisorio: falta un reconocimiento real.'}
      </p>
    </Sheet>
  )
}

// --- Reconocimiento ----------------------------------------------------------------------

function ReconnaissanceSection({ canVerify, reason }: { canVerify: boolean; reason: string }) {
  const toast = useToast()
  const invalidate = useInvalidateBot()
  const runs = useBotRuns()
  const running = runs.data?.find((r) => r.status === 'en_curso')
  const start = useMutation({
    mutationFn: () => post<BotRun>('/marangatu/runs/reconnaissance'),
    onSuccess: (run) => {
      invalidate()
      if (run.status === 'detenida') toast('bad', 'El reconocimiento quedó detenido: mirá el motivo en las corridas.')
      else toast('ok', 'Reconocimiento en marcha.')
    },
  })
  return (
    <Sheet className="p-5">
      <h2 className="font-semibold">Hacer un reconocimiento</h2>
      <p className="mt-1 max-w-[62ch] text-ink-2">Solo navega por Marangatu y captura las pantallas para aprender cómo son. Nunca llena ni presenta nada.</p>
      <div className="mt-3 flex items-center gap-3">
        <Button onClick={() => start.mutate()} busy={start.isPending} disabled={!canVerify || !!running}>
          Hacer un reconocimiento
        </Button>
        {running && (
          <span role="status" className="text-sm text-ink-2">
            Reconocimiento en curso desde {formatDateTime(running.started_at)}…
          </span>
        )}
      </div>
      {!canVerify && <ReadOnlyHint reason={reason} />}
      {start.isError && (
        <div className="mt-3">
          <ApiErrorNotice error={start.error} title="No se pudo iniciar el reconocimiento." />
        </div>
      )}
    </Sheet>
  )
}

// --- Corridas ----------------------------------------------------------------------------

export function StopReason({ run }: { run: Pick<BotRun, 'stop_code' | 'stop_text' | 'stop_detail'> }) {
  if (!run.stop_code) return null
  return (
    <div>
      <p>{run.stop_text ?? run.stop_code}</p>
      {run.stop_detail && <p className="text-sm text-ink-3">{run.stop_detail}</p>}
    </div>
  )
}

const statusTone = (status: string) => (status === 'terminada' ? 'ok' : status === 'detenida' ? 'warn' : 'neutral')

function RunsSection() {
  const runs = useBotRuns()
  const [selected, setSelected] = useState<string | null>(null)
  return (
    <Sheet>
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <h2 className="font-semibold">Últimas corridas</h2>
        <VerifyChain />
      </div>
      {runs.isError ? (
        <div className="p-5">
          <ApiErrorNotice error={runs.error} title="No se pudieron leer las corridas." />
        </div>
      ) : !runs.data ? (
        <Skeleton className="m-5 h-24" />
      ) : runs.data.length === 0 ? (
        <EmptyState title="Todavía no hubo corridas">Cuando hagas un reconocimiento, queda registrado acá con todos sus pasos.</EmptyState>
      ) : (
        <table className="w-full text-left">
          <thead className="text-sm text-ink-3">
            <tr>
              <th className="px-5 py-2 font-medium">Cuándo</th>
              <th className="px-3 py-2 font-medium">Tipo</th>
              <th className="px-3 py-2 font-medium">Período</th>
              <th className="px-3 py-2 font-medium">Etapa</th>
              <th className="px-3 py-2 font-medium">Resultado</th>
              <th className="px-5 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {runs.data.map((r) => (
              <tr key={r.id} data-testid={`run-${r.id}`} className="align-top">
                <td className="px-5 py-2.5 tabular-nums">{formatDateTime(r.started_at)}</td>
                <td className="px-3 py-2.5">{TASK_LABELS[r.task_type] ?? r.task_type}</td>
                <td className="px-3 py-2.5 tabular-nums">{r.period ?? '—'}</td>
                <td className="px-3 py-2.5">{STAGE_LABELS[r.stage] ?? r.stage}</td>
                <td className="px-3 py-2.5">
                  <Badge tone={statusTone(r.status)}>{RUN_STATUS_LABELS[r.status] ?? r.status}</Badge>
                  {r.stop_code && (
                    <div className="mt-1 max-w-[46ch]">
                      <StopReason run={r} />
                    </div>
                  )}
                </td>
                <td className="px-5 py-2.5 text-right">
                  <Button variant="ghost" onClick={() => setSelected(r.id)}>
                    Ver pasos
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <Modal open={selected !== null} title="Detalle de la corrida" size="lg" onClose={() => setSelected(null)}>
        {selected && <RunDetail id={selected} />}
      </Modal>
    </Sheet>
  )
}

function RunDetail({ id }: { id: string }) {
  const run = useBotRun(id)
  if (run.isError) return <div className="p-5"><ApiErrorNotice error={run.error} title="No se pudo leer la corrida." /></div>
  if (!run.data) return <Skeleton className="m-5 h-40" />
  return (
    <div className="flex flex-col gap-4 p-5">
      <p>
        {TASK_LABELS[run.data.task_type] ?? run.data.task_type} · <Badge tone={statusTone(run.data.status)}>{RUN_STATUS_LABELS[run.data.status] ?? run.data.status}</Badge>
      </p>
      <StopReason run={run.data} />
      {run.data.steps.length === 0 ? (
        <p className="text-ink-3">Esta corrida no registró pasos.</p>
      ) : (
        <div className="max-h-[50vh] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-ink-3">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Hora</th>
                <th className="py-1.5 pr-3 font-medium">Pantalla</th>
                <th className="py-1.5 pr-3 font-medium">Acción</th>
                <th className="py-1.5 pr-3 font-medium">Valores</th>
                <th className="py-1.5 pr-3 font-medium">Resultado</th>
                <th className="py-1.5 font-medium">Captura</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {run.data.steps.map((s) => (
                <StepRow key={s.id} step={s} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function StepRow({ step }: { step: BotStep }) {
  const [error, setError] = useState<string>()
  const open = async () => {
    setError(undefined)
    try {
      const { blob } = await getBlob(`/marangatu/steps/${step.id}/capture`)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener')
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'No se pudo abrir la captura.')
    }
  }
  const values = Object.keys(step.values).length === 0 ? '—' : JSON.stringify(step.values)
  return (
    <tr className="align-top">
      <td className="py-1.5 pr-3 tabular-nums">{formatDateTime(step.occurred_at)}</td>
      <td className="py-1.5 pr-3">{step.screen_id ? `${step.screen_id}${step.screen_version ? ` v${step.screen_version}` : ''}` : '—'}</td>
      <td className="py-1.5 pr-3">{step.action}</td>
      <td className="max-w-[22ch] break-words py-1.5 pr-3 text-ink-2">{values}</td>
      <td className="py-1.5 pr-3">
        {step.result}
        {step.message && <span className="block text-ink-3">{step.message}</span>}
      </td>
      <td className="py-1.5">
        {step.capture_path ? (
          <>
            <button type="button" onClick={open} className="text-ledger hover:underline">
              Ver captura
            </button>
            {error && <span className="block text-debit">{error}</span>}
          </>
        ) : (
          '—'
        )}
      </td>
    </tr>
  )
}

function VerifyChain() {
  const verify = useMutation({ mutationFn: () => api<BotVerify>('GET', '/marangatu/verify') })
  const r = verify.data
  return (
    <div className="flex items-center gap-3">
      {verify.isError && <span className="text-sm text-debit">No se pudo verificar.</span>}
      {r && (
        <span role="status" className={r.valid ? 'text-sm text-ledger' : 'text-sm text-debit'}>
          {r.valid
            ? `Registro íntegro: ${r.checked} pasos y ${r.files_checked} archivos revisados.`
            : `Registro alterado${r.first_broken_seq !== null ? ` desde el paso ${r.first_broken_seq}` : ''}${r.file_problems.length > 0 ? `; ${r.file_problems.length} archivos con problemas` : ''}.`}
        </span>
      )}
      <Button variant="secondary" busy={verify.isPending} onClick={() => verify.mutate()}>
        Verificar el registro
      </Button>
    </div>
  )
}
