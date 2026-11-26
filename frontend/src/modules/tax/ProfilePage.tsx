/**
 * Perfil fiscal (D-083): un asistente que explica cada dato y dónde está en la constancia de
 * RUC. Lo declara el propietario (o quien tenga `tax.manage`) y lo verifica CONTADOR AI contra
 * la constancia, con la aprobación de quien tiene `tax.verify` (D-118, D-120). Cada cambio es
 * una versión con su fecha de vigencia.
 */
import { useMutation } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, FilePlus2, ShieldCheck } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { Link } from 'react-router'
import { Badge, Button, EmptyState, Field, Input, Modal, Notice, PageHeader, Select, Sheet, Skeleton } from '../../components/ui'
import { useToast } from '../../components/ui/toast'
import { cx } from '../../lib/cx'
import { formatDateTime } from '../../lib/format'
import { ApiError, post, put } from '../../services/api'
import { useSession } from '../../stores/session'
import type { LegalForm } from '../../types/api'
import { ApiErrorNotice, Check as CheckBox, ReadOnlyHint, Th } from '../finance/components'
import { formatBookDate, todayIso } from '../finance/labels'
import { UnverifiedMark, VerifyForm } from './components'
import { useInvalidateTax, useTaxPerms, useTaxProfile } from './data'
import { accountingOptional, dnitName, IRE_REGIME_LABELS, monthName, obligationsFor } from './labels'
import type { IreRegime, Profile, ProfileVersion } from './types'

interface Draft {
  valid_from: string
  ire_regime: IreRegime | ''
  fiscal_close_month: number
  vat_taxpayer: boolean | null
  obligations: Record<string, string>
  notes: string
}

const fromVersion = (v: ProfileVersion | null | undefined): Draft => ({
  valid_from: v ? todayIso() : '',
  ire_regime: v?.ire_regime ?? '',
  fiscal_close_month: v?.fiscal_close_month ?? 12,
  vat_taxpayer: v ? v.vat_taxpayer : null,
  obligations: Object.fromEntries((v?.obligations ?? []).map((o) => [o.code, o.registered_on])),
  notes: '',
})

const IRE_BY_CODE: Record<string, IreRegime> = { '700': 'ire_general', '701': 'ire_simple', '702': 'resimple' }
const IRE_NAMES: Record<string, string> = { '700': 'IRE General', '701': 'IRE SIMPLE', '702': 'IRE RESIMPLE' }
const REGIME_NAMES: Partial<Record<IreRegime, string>> = { ire_general: 'el IRE General', ire_simple: 'el IRE SIMPLE', resimple: 'el RESIMPLE', none: '«sin IRE»' }
const IRP_NAMES: Record<string, string> = { '715': 'IRP-RSP', '716': 'IRP-RGC' }
const COMPANY_FORMS: LegalForm[] = ['EAS', 'SA', 'SRL', 'UNIPERSONAL']
const RESIMPLE_FORMS: LegalForm[] = ['PERSONA_FISICA', 'UNIPERSONAL']

/** Los mismos controles que hace la API (`profile._check_consistency`, D-142), para avisar antes de guardar. */
function consistencyProblems(d: Pick<Draft, 'ire_regime' | 'vat_taxpayer' | 'obligations' | 'fiscal_close_month'>, legalForm: LegalForm | undefined): string[] {
  const codes = Object.keys(d.obligations)
  const regime = d.ire_regime
  const person = legalForm === 'PERSONA_FISICA'
  const out: string[] = []
  if (codes.includes('211') && d.vat_taxpayer === false) out.push('La obligación 211 (IVA General) es de contribuyentes del IVA.')
  const ire = Object.keys(IRE_BY_CODE).filter((c) => codes.includes(c))
  if (ire.length > 1) out.push(`No se puede estar en más de un régimen del IRE a la vez: ${ire.map((c) => `${IRE_NAMES[c]} (${c})`).join(' y ')}.`)
  for (const code of ire) {
    if (code === '702' && regime !== 'resimple') out.push('La obligación 702 es del IRE RESIMPLE: elegí el régimen RESIMPLE para cargarla.')
    else if (code !== '702' && regime && REGIME_NAMES[regime] && regime !== IRE_BY_CODE[code]) out.push(`La obligación ${code} es del ${IRE_NAMES[code]}, pero el régimen es ${REGIME_NAMES[regime]}.`)
  }
  if (regime === 'resimple' && !(legalForm && RESIMPLE_FORMS.includes(legalForm))) out.push('El RESIMPLE es solo para empresas unipersonales de una persona física (Ley 6380/2019, art. 27).')
  if (regime === 'none' && legalForm && COMPANY_FORMS.includes(legalForm)) out.push('Una empresa es contribuyente del IRE (Ley 6380/2019, art. 2°): elegí su régimen o «Todavía no lo sé».')
  if (regime === 'resimple' && codes.includes('211'))
    out.push('Quien liquida por el RESIMPLE no es contribuyente del IVA (Ley 6380/2019, art. 27, último párrafo): no puede tener la obligación 211.')
  const irp = Object.keys(IRP_NAMES).filter((c) => codes.includes(c))
  if (!person) for (const code of irp) out.push(`La obligación ${code} (${IRP_NAMES[code]}) es del impuesto a la renta personal: solo la tiene una persona física, no una empresa.`)
  if (irp.length > 0 && person && d.fiscal_close_month !== 12)
    out.push(`El ejercicio del IRP es el año civil (Ley 6380/2019, art. 52): con la obligación ${irp.join(' o ')} el cierre del ejercicio es en diciembre.`)
  if (codes.includes('956')) {
    if (codes.includes('211')) out.push('Con la 211 (IVA) el registro de comprobantes es el mensual, 955, no el anual 956 (RG 90/2021, art. 7°, texto de la RG DNIT 12/2024).')
    if (!codes.includes('715')) out.push('El registro anual de comprobantes (956) va con la obligación 715 (IRP-RSP) (RG 90/2021, art. 7°, texto de la RG DNIT 12/2024).')
  }
  return out
}

function AccountingOptionalNote() {
  return (
    <Notice tone="neutral" title="La contabilidad es opcional">
      Sin el IRE General, a la persona física no se le exige contabilidad por partida doble: alcanzan el registro de comprobantes y los libros de ingresos y egresos (RG
      69/2020, art. 32; RG 90/2021). El menú Contabilidad sigue disponible si querés llevarla igual. Si la Ley 1034 «Del Comerciante» te obliga a llevarla, sí corresponde
      (sin verificar).
    </Notice>
  )
}

const STEPS = ['Desde cuándo', 'Régimen del IRE', 'Cierre del ejercicio', 'IVA', 'Obligaciones', 'Revisar'] as const

function Where({ children }: { children: ReactNode }) {
  return (
    <aside className="rounded-sm border-l-2 border-ledger bg-ledger-soft/60 px-3.5 py-2.5 text-sm">
      <p className="font-medium text-ledger">Dónde está en la constancia de RUC</p>
      <div className="mt-0.5 text-ink">{children}</div>
    </aside>
  )
}

function Choice({ checked, onSelect, title, children, name }: { checked: boolean; onSelect: () => void; title: string; children: ReactNode; name: string }) {
  return (
    <label
      className={cx(
        'flex cursor-pointer items-start gap-3 rounded-sm border px-3.5 py-3 has-focus-visible:outline-2 has-focus-visible:outline-(--focus)',
        checked ? 'border-ledger bg-ledger-soft/50' : 'border-line-strong hover:bg-sunken',
      )}
    >
      <input type="radio" name={name} className="mt-1 accent-(--ledger)" checked={checked} onChange={onSelect} />
      <span>
        <span className="font-medium">{title}</span>
        <span className="block text-sm text-ink-2">{children}</span>
      </span>
    </label>
  )
}

function Wizard({ profile, legalForm, onDone }: { profile: Profile; legalForm: LegalForm | undefined; onDone: () => void }) {
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const [step, setStep] = useState(0)
  const [d, setD] = useState<Draft>(() => fromVersion(profile.current))
  const [stepError, setStepError] = useState<string>()
  const [otherCode, setOtherCode] = useState('')
  const set = (patch: Partial<Draft>) => {
    setD((x) => ({ ...x, ...patch }))
    setStepError(undefined)
  }
  const sameAsDeclared = profile.history.find((v) => v.valid_from === d.valid_from)
  const person = legalForm === 'PERSONA_FISICA'
  const catalog = obligationsFor(legalForm)

  const save = useMutation({
    mutationFn: () =>
      put<Profile>('/tax/profile', {
        valid_from: d.valid_from,
        ire_regime: d.ire_regime,
        fiscal_close_month: d.fiscal_close_month,
        vat_taxpayer: d.vat_taxpayer,
        obligations: Object.entries(d.obligations).map(([code, registered_on]) => ({ code, registered_on })),
        notes: d.notes.trim() || null,
      }),
    onSuccess: () => {
      invalidate()
      toast('ok', 'Perfil fiscal guardado. El calendario se recalculó con estos datos.')
      onDone()
    },
  })

  const validate = (): string | undefined => {
    if (step === 0 && !d.valid_from) return 'Elegí la fecha desde la que rige.'
    if (step === 1 && !d.ire_regime) return 'Elegí el régimen (o «Todavía no lo sé»).'
    if (step === 3 && d.vat_taxpayer === null) return person ? 'Indicá si sos contribuyente del IVA.' : 'Indicá si la empresa es contribuyente del IVA.'
    if (step === 4) {
      const missing = Object.entries(d.obligations).find(([, date]) => !date)
      if (missing) return `Falta la fecha de alta de la obligación ${missing[0]}.`
    }
    return undefined
  }
  const next = () => {
    const error = validate()
    if (error) {
      setStepError(error)
      return
    }
    // Al llegar a las obligaciones sin ninguna, se sugieren las que corresponden a lo elegido.
    if (step === 3 && Object.keys(d.obligations).length === 0) {
      const suggested: Record<string, string> = {}
      if (d.vat_taxpayer) {
        suggested['211'] = ''
        suggested['955'] = ''
      }
      if (d.ire_regime === 'ire_general') suggested['700'] = ''
      if (d.ire_regime === 'ire_simple') suggested['701'] = ''
      if (d.ire_regime === 'resimple') suggested['702'] = ''
      set({ obligations: suggested })
    }
    setStep((s) => Math.min(STEPS.length - 1, s + 1))
  }
  const toggle = (code: string, on: boolean) => {
    const obligations = { ...d.obligations }
    if (on) obligations[code] = obligations[code] ?? ''
    else delete obligations[code]
    set({ obligations })
  }
  const problems = consistencyProblems(d, legalForm)
  const apiProblems = save.error instanceof ApiError && save.error.code === 'PROFILE_INCONSISTENT' ? ((save.error.details as { problems?: string[] })?.problems ?? []) : []
  const otherCodes = Object.keys(d.obligations).filter((c) => !catalog.some((o) => o.code === c))

  return (
    <div className="grid grid-cols-[12rem_minmax(0,1fr)] gap-6">
      <ol className="flex flex-col gap-1" aria-label="Pasos del perfil fiscal">
        {STEPS.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              disabled={i > step}
              onClick={() => setStep(i)}
              aria-current={i === step ? 'step' : undefined}
              className={cx(
                'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm',
                i === step ? 'bg-ledger-soft font-medium text-ledger' : i < step ? 'text-ink hover:bg-sunken' : 'text-ink-3',
              )}
            >
              <span className={cx('grid size-5 place-items-center rounded-full border text-xs tabular-nums', i < step ? 'border-ledger bg-ledger text-surface' : 'border-current')}>
                {i < step ? <Check size={12} aria-hidden /> : i + 1}
              </span>
              {label}
            </button>
          </li>
        ))}
      </ol>

      <form
        className="flex flex-col gap-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault()
          if (step < STEPS.length - 1) next()
          else save.mutate()
        }}
      >
        <h3 className="text-md font-semibold">
          {step + 1}. {STEPS[step]}
        </h3>

        {step === 0 && (
          <>
            <p className="max-w-[65ch] text-ink-2">
              El perfil se guarda por versiones: cada cambio rige desde una fecha y los meses anteriores conservan el perfil de entonces. Si es la primera vez, poné la
              fecha desde la que querés el calendario (por ejemplo, el alta en el RUC o el 1 de enero).
            </p>
            <Field label="Rige desde" error={stepError}>
              {(p) => <Input {...p} autoFocus type="date" className="w-44" value={d.valid_from} onChange={(e) => set({ valid_from: e.target.value })} />}
            </Field>
            {sameAsDeclared && (
              <Notice tone={sameAsDeclared.origin === 'verified' ? 'bad' : 'neutral'} title={sameAsDeclared.origin === 'verified' ? 'Ya hay una versión verificada con esa fecha' : 'Se corrige la versión de esa fecha'}>
                {sameAsDeclared.origin === 'verified'
                  ? 'Una versión verificada no cambia: elegí otra fecha para cargar el cambio como una versión nueva.'
                  : 'Con la misma fecha no se crea una versión nueva: se reemplaza la declarada.'}
              </Notice>
            )}
          </>
        )}

        {step === 1 && (
          <>
            <Where>
              En el apartado de obligaciones figura <b>700 — IRE General</b>, <b>701 — IRE SIMPLE</b>
              {RESIMPLE_FORMS.includes(legalForm as LegalForm) && (
                <>
                  {' '}
                  o <b>702 — IRE RESIMPLE</b>
                </>
              )}
              .{' '}
              {person
                ? 'Si no figura ninguna (por ejemplo, solo tenés IRP o IVA), elegí «Sin IRE».'
                : 'Si no figura ninguna, revisá tus obligaciones en Marangatu antes de elegir.'}
            </Where>
            <fieldset className="flex flex-col gap-2">
              <legend className="sr-only">Régimen del IRE</legend>
              <Choice name="ire" checked={d.ire_regime === 'ire_general'} onSelect={() => set({ ire_regime: 'ire_general' })} title="IRE General">
                Régimen general del impuesto a la renta empresarial: declaración anual con el Formulario 500.
              </Choice>
              <Choice name="ire" checked={d.ire_regime === 'ire_simple'} onSelect={() => set({ ire_regime: 'ire_simple' })} title="IRE SIMPLE">
                Para ingresos anuales de hasta el tope de la ley: declaración anual con el Formulario 501.
              </Choice>
              {RESIMPLE_FORMS.includes(legalForm as LegalForm) && (
                <Choice name="ire" checked={d.ire_regime === 'resimple'} onSelect={() => set({ ire_regime: 'resimple' })} title="RESIMPLE">
                  Empresa unipersonal con ingresos de hasta 80 millones al año: declaración anual con el Formulario 502 y cuotas fijas. No es contribuyente del IVA.
                </Choice>
              )}
              {person && (
                <Choice name="ire" checked={d.ire_regime === 'none'} onSelect={() => set({ ire_regime: 'none' })} title="Sin IRE">
                  No tenés obligaciones del IRE: por ejemplo, solo el IRP por servicios personales o el IVA.
                </Choice>
              )}
              <Choice name="ire" checked={d.ire_regime === 'unknown'} onSelect={() => set({ ire_regime: 'unknown' })} title="Todavía no lo sé">
                El calendario no genera la declaración anual del IRE hasta que lo indiques.
              </Choice>
            </fieldset>
            {stepError && <p className="text-sm text-debit">{stepError}</p>}
          </>
        )}

        {step === 2 && (
          <>
            <Where>
              Figura como <b>cierre del ejercicio</b> (o mes de cierre). En la mayoría de las empresas es diciembre. Define cuándo vencen las declaraciones anuales.
              {person && ' Con el IRP es siempre diciembre: su ejercicio es el año civil.'}
            </Where>
            <Field label="Mes de cierre del ejercicio fiscal">
              {(p) => (
                <Select {...p} autoFocus className="w-48" value={d.fiscal_close_month} onChange={(e) => set({ fiscal_close_month: Number(e.target.value) })}>
                  {Array.from({ length: 12 }, (_, i) => (
                    <option key={i + 1} value={i + 1}>
                      {monthName(i + 1)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </>
        )}

        {step === 3 && (
          <>
            <Where>
              Si entre las obligaciones figura <b>211 — IVA General</b>, {person ? 'sos' : 'la empresa es'} contribuyente del IVA y presenta el Formulario 120 todos los meses.
            </Where>
            <fieldset className="flex flex-col gap-2">
              <legend className="sr-only">Contribuyente del IVA</legend>
              <Choice name="iva" checked={d.vat_taxpayer === true} onSelect={() => set({ vat_taxpayer: true })} title="Sí, es contribuyente del IVA">
                Tiene la obligación 211.
              </Choice>
              <Choice name="iva" checked={d.vat_taxpayer === false} onSelect={() => set({ vat_taxpayer: false })} title="No">
                No tiene la obligación 211.
              </Choice>
            </fieldset>
            {stepError && <p className="text-sm text-debit">{stepError}</p>}
          </>
        )}

        {step === 4 && (
          <>
            <Where>
              La lista de <b>obligaciones</b> trae cada una con su código, su nombre y la fecha desde la que rige. Copiá exactamente esas: la app no agrega obligaciones
              por su cuenta.
            </Where>
            <ul className="flex flex-col divide-y divide-line rounded-sm border border-line">
              {catalog.map((o) => {
                const on = o.code in d.obligations
                return (
                  <li key={o.code} className="flex items-start gap-4 px-3.5 py-3">
                    <div className="flex-1">
                      <CheckBox label={`${o.code} — ${o.name}`} hint={o.hint} checked={on} onChange={(v) => toggle(o.code, v)} />
                    </div>
                    {on && (
                      <Field label={`Fecha de alta de la ${o.code}`}>
                        {(p) => (
                          <Input
                            {...p}
                            type="date"
                            className="w-44"
                            value={d.obligations[o.code]}
                            onChange={(e) => set({ obligations: { ...d.obligations, [o.code]: e.target.value } })}
                          />
                        )}
                      </Field>
                    )}
                  </li>
                )
              })}
              {otherCodes.map((code) => (
                <li key={code} className="flex items-start gap-4 px-3.5 py-3">
                  <div className="flex-1">
                    <CheckBox label={`${code} — otra obligación`} hint="La app la guarda en el perfil pero todavía no genera sus vencimientos." checked onChange={() => toggle(code, false)} />
                  </div>
                  <Field label={`Fecha de alta de la ${code}`}>
                    {(p) => (
                      <Input {...p} type="date" className="w-44" value={d.obligations[code]} onChange={(e) => set({ obligations: { ...d.obligations, [code]: e.target.value } })} />
                    )}
                  </Field>
                </li>
              ))}
            </ul>
            <div className="flex items-end gap-2">
              <Field label="Otra obligación de la constancia (código)" hint="Por ejemplo 726 o 954. Se guarda, aunque la app no la calcule todavía.">
                {(p) => <Input {...p} className="w-32" inputMode="numeric" maxLength={4} value={otherCode} onChange={(e) => setOtherCode(e.target.value.replace(/\D/g, ''))} />}
              </Field>
              <Button
                type="button"
                variant="secondary"
                className="mb-6"
                disabled={!otherCode || otherCode in d.obligations}
                onClick={() => {
                  toggle(otherCode, true)
                  setOtherCode('')
                }}
              >
                Agregar
              </Button>
            </div>
            {stepError && <p className="text-sm text-debit">{stepError}</p>}
            {problems.length > 0 && (
              <Notice tone="warn" title="Revisá la combinación">
                <ul className="list-disc pl-4">
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </Notice>
            )}
          </>
        )}

        {step === 5 && (
          <>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-sm border border-line px-4 py-3">
              <div>
                <dt className="text-sm text-ink-2">Rige desde</dt>
                <dd>{d.valid_from ? formatBookDate(d.valid_from) : '—'}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-2">Régimen del IRE</dt>
                <dd>{d.ire_regime ? IRE_REGIME_LABELS[d.ire_regime] : '—'}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-2">Cierre del ejercicio</dt>
                <dd className="first-letter:uppercase">{monthName(d.fiscal_close_month)}</dd>
              </div>
              <div>
                <dt className="text-sm text-ink-2">Contribuyente del IVA</dt>
                <dd>{d.vat_taxpayer ? 'Sí' : 'No'}</dd>
              </div>
              <div className="col-span-2">
                <dt className="text-sm text-ink-2">Obligaciones</dt>
                <dd>
                  {Object.keys(d.obligations).length === 0 ? (
                    'Ninguna: no se va a generar ningún vencimiento.'
                  ) : (
                    <ul>
                      {Object.entries(d.obligations).map(([code, date]) => (
                        <li key={code}>
                          <span className="tabular-nums">{code}</span> {dnitName(code)}, desde el {date ? formatBookDate(date) : '—'}
                        </li>
                      ))}
                    </ul>
                  )}
                </dd>
              </div>
            </dl>
            <Field label="Notas (opcional)" hint="Por ejemplo, de dónde sacaste los datos.">
              {(p) => <Input {...p} maxLength={500} value={d.notes} onChange={(e) => set({ notes: e.target.value })} />}
            </Field>
            {problems.length > 0 && <Notice tone="warn" title="La combinación no es coherente">{problems.join(' ')}</Notice>}
            <p className="text-sm text-ink-2">Queda como perfil declarado. Después se verifica comparándolo con la constancia de RUC.</p>
            {apiProblems.length > 0 ? <Notice tone="bad" title={save.error instanceof ApiError ? save.error.message : ''} /> : <ApiErrorNotice error={save.error} />}
          </>
        )}

        <div className="flex justify-between gap-2 border-t border-line pt-4">
          <Button type="button" variant="ghost" onClick={step === 0 ? onDone : () => setStep(step - 1)}>
            {step === 0 ? (
              'Cancelar'
            ) : (
              <>
                <ArrowLeft size={15} aria-hidden />
                Anterior
              </>
            )}
          </Button>
          {step < STEPS.length - 1 ? (
            <Button type="submit">
              Siguiente
              <ArrowRight size={15} aria-hidden />
            </Button>
          ) : (
            <Button type="submit" busy={save.isPending} disabled={problems.length > 0}>
              Guardar el perfil
            </Button>
          )}
        </div>
      </form>
    </div>
  )
}

function VersionCard({ version, legalForm, canVerify, onVerify }: { version: ProfileVersion; legalForm: LegalForm | undefined; canVerify: boolean; onVerify: () => void }) {
  return (
    <div className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-ink-2">Vigente desde el {formatBookDate(version.valid_from)}</p>
          <p className="mt-0.5 text-lg font-semibold">
            {IRE_REGIME_LABELS[version.ire_regime]}
            {version.vat_taxpayer ? ' · contribuyente del IVA' : ' · sin IVA'}
          </p>
          <p className="mt-1">
            {version.origin === 'verified' ? <UnverifiedMark status="verified" /> : <UnverifiedMark status="pending" label="Declarado, sin verificar contra la constancia de RUC" />}
          </p>
        </div>
        {version.origin === 'declared' && canVerify && (
          <Button variant="secondary" onClick={onVerify}>
            <ShieldCheck size={16} aria-hidden />
            Verificar
          </Button>
        )}
      </div>
      {version.origin === 'verified' && (
        <p className="text-sm text-ink-2">
          Verificado por {version.verified_by_name} contra la {version.verified_license}: {version.verified_document_reference}
          {version.verified_at && <>, el {formatDateTime(version.verified_at)}</>}.
        </p>
      )}
      <dl className="grid grid-cols-[10rem_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
        <dt className="text-ink-2">Cierre del ejercicio</dt>
        <dd className="first-letter:uppercase">{monthName(version.fiscal_close_month)}</dd>
        <dt className="text-ink-2">Obligaciones</dt>
        <dd>
          {version.obligations.length === 0 ? (
            <span className="text-ink-3">Ninguna</span>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {version.obligations.map((o) => (
                <li key={o.code}>
                  <span className="font-medium tabular-nums">{o.code}</span> {dnitName(o.code)}, desde el {formatBookDate(o.registered_on)}
                  {!o.supported && (
                    <span className="ml-1.5">
                      <Badge>La app todavía no la calcula</Badge>
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </dd>
        {version.notes && (
          <>
            <dt className="text-ink-2">Notas</dt>
            <dd>{version.notes}</dd>
          </>
        )}
      </dl>
      {accountingOptional(legalForm, version.ire_regime) && <AccountingOptionalNote />}
    </div>
  )
}

export function ProfilePage() {
  const profile = useTaxProfile()
  const perms = useTaxPerms()
  const toast = useToast()
  const invalidate = useInvalidateTax()
  const [editing, setEditing] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const legalForm = useSession().me?.organization.legal_form
  const data = profile.data
  const current = data?.current

  return (
    <>
      <PageHeader
        title="Perfil fiscal"
        description="Régimen, cierre del ejercicio y obligaciones de la empresa, tal como figuran en la constancia de RUC. Con esto se arma el calendario: la app no asume impuestos que no estén acá."
        actions={
          perms.canManage &&
          data?.ruc &&
          current &&
          !editing && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <FilePlus2 size={16} aria-hidden />
              Cargar un cambio
            </Button>
          )
        }
      />
      {profile.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : profile.isError ? (
        <ApiErrorNotice error={profile.error} title="No se pudo cargar el perfil fiscal." />
      ) : !data?.ruc ? (
        <Sheet>
          <EmptyState
            title="Primero, el RUC de la empresa"
            action={
              <Link to="/empresa" className="inline-flex h-9 items-center rounded-sm bg-ledger px-3.5 font-medium text-surface hover:bg-ledger-strong">
                Cargar el RUC en Datos de la organización
              </Link>
            }
          >
            El perfil fiscal se arma sobre el RUC y su dígito verificador: de la terminación del RUC dependen los vencimientos.
          </EmptyState>
        </Sheet>
      ) : editing || !current ? (
        <Sheet className="p-5">
          {!current && !editing ? (
            perms.canManage ? (
              <div className="flex flex-col gap-4">
                <p className="max-w-[65ch] text-ink-2">
                  Tené a mano la <b>constancia de RUC</b> (en Marangatu: «Constancia de RUC»). El asistente te pide cinco datos y te dice dónde está cada uno. RUC de la
                  empresa: <span className="font-medium tabular-nums">{data.ruc}-{data.ruc_check_digit}</span>.
                </p>
                <div>
                  <Button onClick={() => setEditing(true)}>Empezar</Button>
                </div>
              </div>
            ) : (
              <EmptyState title="Todavía no hay perfil fiscal">Lo carga el propietario, el administrador o el contador. {perms.manageReason}</EmptyState>
            )
          ) : (
            <Wizard profile={data} legalForm={legalForm} onDone={() => setEditing(false)} />
          )}
        </Sheet>
      ) : (
        <>
          <Sheet>
            <VersionCard version={current} legalForm={legalForm} canVerify={perms.canVerify} onVerify={() => setVerifying(true)} />
            {current.origin === 'declared' && !perms.canVerify && (
              <div className="border-t border-line px-5 py-3">
                <ReadOnlyHint reason={perms.verifyReason} />
              </div>
            )}
          </Sheet>
          {!perms.canManage && <p className="mt-3 text-sm text-ink-3">{perms.manageReason}</p>}
        </>
      )}

      {data && data.history.length > 0 && (
        <section className="mt-8" aria-labelledby="profile-history">
          <h2 id="profile-history" className="mb-3 font-semibold">
            Historial de versiones
          </h2>
          <Sheet className="overflow-hidden">
            <table className="w-full">
              <thead className="border-b border-line bg-sunken text-sm text-ink-2">
                <tr>
                  <Th>Rige desde</Th>
                  <Th>Régimen</Th>
                  <Th>IVA</Th>
                  <Th>Obligaciones</Th>
                  <Th>Origen</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.history.map((v) => (
                  <tr key={v.id} className={cx(v.id === current?.id && 'bg-ledger-soft/30')}>
                    <td className="px-4 py-2.5 tabular-nums">
                      {formatBookDate(v.valid_from)}
                      {v.id === current?.id && <span className="ml-2 text-xs font-medium text-ledger">vigente</span>}
                    </td>
                    <td className="px-4 py-2.5">{IRE_REGIME_LABELS[v.ire_regime]}</td>
                    <td className="px-4 py-2.5">{v.vat_taxpayer ? 'Sí' : 'No'}</td>
                    <td className="px-4 py-2.5 tabular-nums">{v.obligations.map((o) => o.code).join(', ') || '—'}</td>
                    <td className="px-4 py-2.5">
                      {v.origin === 'verified' ? (
                        <span title={`${v.verified_by_name}, ${v.verified_license}: ${v.verified_document_reference}`}>
                          <Badge tone="ok">Verificado</Badge>
                        </span>
                      ) : (
                        <Badge tone="warn">Declarado</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Sheet>
        </section>
      )}

      <Modal open={verifying} title="Verificar el perfil fiscal" onClose={() => setVerifying(false)}>
        {verifying && current && (
          <VerifyForm
            intro={
              <>
                Confirmás que el perfil vigente desde el {formatBookDate(current.valid_from)} coincide con la constancia de RUC de la empresa. Queda verificado por
                CONTADOR AI con tu aprobación. Una versión verificada ya no cambia: un cambio posterior se carga como versión nueva.
              </>
            }
            thirdLabel="Referencia de la constancia de RUC"
            thirdHint="Número de la constancia o fecha de emisión, para encontrarla después."
            thirdRequired
            submit="Verificar perfil"
            onCancel={() => setVerifying(false)}
            onSubmit={async ({ third }) => {
              await post(`/tax/profile/${current.id}/verify`, { verified_document_reference: third })
              invalidate()
              setVerifying(false)
              toast('ok', 'Perfil fiscal verificado.')
            }}
          />
        )}
      </Modal>
    </>
  )
}
