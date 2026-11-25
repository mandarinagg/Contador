/**
 * Acceso a la API del bot de Marangatu (`/marangatu`, D-127 a D-133): tipos, consultas y
 * permisos. Los textos de los motivos de detención los manda el backend (`stop_text`): acá
 * no se duplican.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get } from '../../services/api'
import { useSession } from '../../stores/session'

export interface BotSettings {
  bot_enabled: boolean
  stages: Record<string, string>
  catalog_provisional: boolean
  catalog_updated: string | null
}

export interface BotCredentials {
  ruc: string | null
  has_password: boolean
  store_available: boolean
}

export interface BotRun {
  id: string
  task_type: string
  period: string | null
  stage: string
  status: string
  stop_code: string | null
  stop_text: string | null
  stop_detail: string | null
  started_by: string | null
  started_at: string
  finished_at: string | null
}

export interface BotStep {
  id: string
  seq: number
  occurred_at: string
  screen_id: string | null
  screen_version: number | null
  action: string
  values: Record<string, unknown>
  result: string
  message: string | null
  capture_path: string | null
  capture_sha256: string | null
}

export interface BotRunDetail extends BotRun {
  steps: BotStep[]
}

export interface BotVerify {
  valid: boolean
  checked: number
  first_broken_seq: number | null
  files_checked: number
  file_problems: { seq: number; path: string; problem: string }[]
}

export const TASK_LABELS: Record<string, string> = {
  general: 'Reconocimiento general',
  consulta: 'Consulta de situación',
  registro_comprobantes: 'Registro de comprobantes',
  f120: 'IVA General (Formulario 120)',
  constancias: 'Constancias',
  ire: 'IRE',
}

export const STAGE_LABELS: Record<string, string> = {
  reconocimiento: 'Reconocimiento (solo mira)',
  ensayo: 'Ensayo (llena, no presenta)',
  habilitada: 'Habilitada',
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  en_curso: 'En curso',
  terminada: 'Terminada',
  detenida: 'Detenida',
}

export const botKeys = {
  all: ['marangatu'] as const,
  settings: () => ['marangatu', 'settings'] as const,
  credentials: () => ['marangatu', 'credentials'] as const,
  runs: () => ['marangatu', 'runs'] as const,
  run: (id: string) => ['marangatu', 'run', id] as const,
}

export function useInvalidateBot() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries({ queryKey: botKeys.all })
}

export const useBotSettings = () => useQuery({ queryKey: botKeys.settings(), queryFn: () => get<BotSettings>('/marangatu/settings') })
export const useBotCredentials = () => useQuery({ queryKey: botKeys.credentials(), queryFn: () => get<BotCredentials>('/marangatu/credentials') })

/** Las últimas corridas; mientras haya una en curso se vuelve a pedir cada 2 segundos. */
export const useBotRuns = () =>
  useQuery({
    queryKey: botKeys.runs(),
    queryFn: () => get<BotRun[]>('/marangatu/runs?limit=20'),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'en_curso') ? 2000 : false),
  })

export const useBotRun = (id: string | null) =>
  useQuery({
    enabled: id !== null,
    queryKey: botKeys.run(id ?? ''),
    queryFn: () => get<BotRunDetail>(`/marangatu/runs/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'en_curso' ? 2000 : false),
  })

/** D-130: leer `tax.read`; apagar `tax.manage`; encender, clave y reconocimiento `tax.verify`. */
export function useBotPerms() {
  const { can } = useSession()
  const canVerify = can('tax.verify')
  return {
    canManage: can('tax.manage'),
    canVerify,
    verifyReason: canVerify ? '' : 'Encender el bot, guardar la clave y hacer un reconocimiento le toca a quien puede verificar los impuestos (el propietario).',
  }
}
