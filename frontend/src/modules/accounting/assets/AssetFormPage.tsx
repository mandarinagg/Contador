/**
 * Alta y edición de un bien de uso (D-057, D-064, D-065, D-070). Muestra en vivo la cuota
 * mensual, el inicio de la depreciación y, si los parámetros contables difieren de los fiscales,
 * la cuota no deducible. Con depreciaciones vivas solo cambian los datos descriptivos (D-071).
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Info } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Button, EmptyState, Field, Input, Notice, PageHeader, Select, Sheet, Skeleton, Textarea } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { formatMoney, toInputText } from '../../../lib/money'
import { ApiError, get, patch, post, qs } from '../../../services/api'
import { AmountInput, ApiErrorNotice, Check, ReadOnlyHint } from '../../finance/components'
import { formatBookDate } from '../../finance/labels'
import { Pyg } from '../components'
import { accountingKeys, useAccountingPerms, useAccountingSettings, useAssetCategories, useEntry, useFiscalYears, useInvalidateAccounting } from '../data'
import { monthsText, monthYear, percentText, START_RULE_LABELS } from '../labels'
import type { Entry, FiscalYear, StartRule } from '../types'
import type { FixedAsset, FixedAssetIn } from '../types3b'
import { acquiredBeforeNorm, type AssetDraft, categoryDefaults, checkAsset, depreciationStart, draftFromAsset, emptyDraft, hasLiveDepreciation, type Plan } from './assetForm'

function PlanSummary({ title, plan, residual }: { title: string; plan: Plan | null; residual?: string }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-ink-2">{title}</h3>
      {plan ? (
        <dl className="mt-1 grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5 text-sm">
          {residual !== undefined && (
            <>
              <dt className="text-ink-2">Valor residual</dt>
              <dd className="text-right">
                <Pyg value={residual} />
              </dd>
            </>
          )}
          <dt className="text-ink-2">Importe depreciable</dt>
          <dd className="text-right">
            <Pyg value={plan.depreciable} />
          </dd>
          <dt className="text-ink-2">Cuota mensual</dt>
          <dd className="text-right">
            <Pyg value={plan.regular} strong />
          </dd>
          {plan.last !== plan.regular && (
            <>
              <dt className="text-ink-2">Última cuota (absorbe el redondeo)</dt>
              <dd className="text-right">
                <Pyg value={plan.last} />
              </dd>
            </>
          )}
          <dt className="text-ink-2">Cuotas</dt>
          <dd className="text-right tabular-nums">{plan.months}</dd>
        </dl>
      ) : (
        <p className="mt-1 text-sm text-ink-3">Completá costo, vida útil y residual para ver la cuota.</p>
      )}
    </div>
  )
}

/** Asiento de compra por número, dentro del ejercicio de la fecha de adquisición. */
function useAcquisitionEntry(number: string, acquiredOn: string, years: FiscalYear[] | undefined) {
  const n = number.trim()
  const year = years?.find((y) => y.start_date <= acquiredOn && acquiredOn <= y.end_date)
  return useQuery({
    enabled: /^\d{1,9}$/.test(n),
    queryKey: [...accountingKeys.entries(), 'by-number', n, year?.id ?? ''],
    queryFn: async () => {
      const list = await get<Entry[]>(`/accounting/entries${qs({ q: n, fiscal_year_id: year?.id, limit: 50 })}`)
      return list.find((e) => e.number === Number(n)) ?? null
    },
    staleTime: 30_000,
  })
}

function AssetForm({ asset, acquisitionNumber, onSaved }: { asset?: FixedAsset; acquisitionNumber: number | null; onSaved: (a: FixedAsset) => void }) {
  const settings = useAccountingSettings()
  const categories = useAssetCategories()
  const years = useFiscalYears()
  const invalidate = useInvalidateAccounting()
  const [draft, setDraft] = useState<AssetDraft>(() => (asset ? draftFromAsset(asset, acquisitionNumber) : emptyDraft(settings.data?.default_asset_start_rule ?? 'next_month')))
  const [touched, setTouched] = useState(false)
  const set = (patchDraft: Partial<AssetDraft>) => setDraft((d) => ({ ...d, ...patchDraft }))
  const locked = asset ? hasLiveDepreciation(asset) || asset.status === 'disposed' || Boolean(asset.disposal_entry_id) : false
  const all = categories.data ?? []
  const usable = all.filter((c) => (c.complete && !c.archived_at) || c.id === asset?.category_id)
  const category = all.find((c) => c.id === draft.category_id)
  const check = checkAsset(draft, category)
  const acquisition = useAcquisitionEntry(draft.acquisition_number, draft.acquired_on, years.data)
  const acquisitionError =
    draft.acquisition_number.trim() && acquisition.isSuccess && !acquisition.data
      ? `No hay un asiento N° ${draft.acquisition_number.trim()} en el ejercicio de la fecha de adquisición.`
      : undefined
  const start = draft.acquired_on ? depreciationStart(draft.acquired_on, draft.start_rule, years.data ?? []) : null
  const errors = locked ? { name: check.errors.name, acquisition_number: check.errors.acquisition_number } : check.errors
  const shown = (k: keyof AssetDraft) => (touched ? errors[k] : undefined)
  const blocked = Object.values(errors).some(Boolean) || Boolean(acquisitionError) || (Boolean(draft.acquisition_number.trim()) && acquisition.isFetching)

  const save = useMutation({
    mutationFn: () => {
      const entryId = draft.acquisition_number.trim() ? (acquisition.data?.id ?? null) : null
      if (asset && locked) {
        const body: FixedAssetIn = { name: draft.name.trim(), description: draft.description.trim() || null, serial_or_reference: draft.serial_or_reference.trim() || null }
        if (entryId !== asset.acquisition_entry_id) body.acquisition_entry_id = entryId
        return patch<FixedAsset>(`/accounting/fixed-assets/${asset.id}`, body)
      }
      const body: FixedAssetIn = { ...(check.body as FixedAssetIn) }
      if (!asset || entryId !== asset.acquisition_entry_id) body.acquisition_entry_id = entryId
      return asset ? patch<FixedAsset>(`/accounting/fixed-assets/${asset.id}`, body) : post<FixedAsset>('/accounting/fixed-assets', body)
    },
    onSuccess: (a) => {
      invalidate()
      onSaved(a)
    },
  })
  const apiCode = save.error instanceof ApiError ? save.error.code : ''

  return (
    <form
      noValidate
      className="grid grid-cols-[minmax(0,1fr)_22rem] items-start gap-6"
      onSubmit={(e) => {
        e.preventDefault()
        setTouched(true)
        if (!blocked) save.mutate()
      }}
    >
      <div className="flex flex-col gap-6">
        {locked && asset && (
          <Notice tone="neutral" title="Solo cambian los datos descriptivos">
            {asset.disposal_entry_id
              ? 'El bien tiene una baja: el costo, la vida útil, el residual, el inicio y la categoría ya no cambian.'
              : 'El bien ya tiene depreciaciones (en borrador o contabilizadas): el costo, la vida útil, el residual, el inicio y la categoría no cambian. Para corregirlos, revertí o descartá esas corridas.'}
          </Notice>
        )}
        <Sheet className="flex flex-col gap-4 p-5">
          <h2 className="font-semibold">El bien</h2>
          <Field label="Categoría" error={shown('category_id')} hint={category ? `${category.legal_reference ?? 'Categoría de la empresa'}${category.validation_status === 'validated' ? ', validada' : ', sin validar'}.` : undefined}>
            {(p) => (
              <Select
                {...p}
                disabled={locked}
                value={draft.category_id}
                onChange={(e) => {
                  const c = all.find((x) => x.id === e.target.value)
                  set({ category_id: e.target.value, ...(c ? categoryDefaults(c) : {}) })
                }}
              >
                <option value="">Elegí la categoría</option>
                {usable.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.useful_life_months ? monthsText(c.useful_life_months) : 'sin vida útil'}, residual {percentText(c.residual_rate)})
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Nombre" error={shown('name')}>
              {(p) => <Input {...p} maxLength={200} placeholder="Notebook Lenovo ThinkPad" value={draft.name} onChange={(e) => set({ name: e.target.value })} />}
            </Field>
            <Field label="N° de serie o referencia" hint="Opcional.">
              {(p) => <Input {...p} maxLength={100} value={draft.serial_or_reference} onChange={(e) => set({ serial_or_reference: e.target.value })} />}
            </Field>
          </div>
          <Field label="Descripción" hint="Opcional: marca, ubicación, quién lo usa.">
            {(p) => <Textarea {...p} rows={2} maxLength={1000} value={draft.description} onChange={(e) => set({ description: e.target.value })} />}
          </Field>
        </Sheet>

        <Sheet className="flex flex-col gap-4 p-5">
          <h2 className="font-semibold">Compra</h2>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Fecha de adquisición" error={shown('acquired_on')} hint="La del comprobante de compra.">
              {(p) => <Input {...p} type="date" disabled={locked} value={draft.acquired_on} onChange={(e) => set({ acquired_on: e.target.value })} />}
            </Field>
            <Field label="Costo de adquisición" error={shown('cost')} hint="Sin IVA crédito fiscal, con fletes e instalación.">
              {(p) => <AmountInput {...p} currency="PYG" disabled={locked} value={draft.cost} onChange={(t) => set({ cost: t })} />}
            </Field>
          </div>
          <p className="flex gap-2 text-sm text-ink-2">
            <Info size={15} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
            El costo no incluye los intereses de la financiación ni las diferencias de cambio: esos van a resultados cuando se devengan (Decreto 3182, art.
            30).
          </p>
          {acquiredBeforeNorm(draft.acquired_on) && (
            <Notice tone="warn" title="Comprado antes del 14-10-2021">
              Las vidas útiles propuestas son las de la redacción del Decreto 6105/2021. Para un bien adquirido antes puede regir otra versión del art.
              31 (art. 30: la norma vigente al adquirirlo). La vida útil y el residual salen de la categoría.
            </Notice>
          )}
          <fieldset className="flex flex-col gap-2" disabled={locked}>
            <legend className="mb-1 text-sm font-medium text-ink-2">Inicio de la depreciación</legend>
            {(Object.keys(START_RULE_LABELS) as StartRule[]).map((r) => (
              <label key={r} className="flex cursor-pointer items-center gap-2">
                <input type="radio" name="start-rule" className="accent-(--ledger)" checked={draft.start_rule === r} onChange={() => set({ start_rule: r })} />
                {START_RULE_LABELS[r]}
                {settings.data?.default_asset_start_rule === r && <span className="text-sm text-ink-3">(la opción por defecto de la empresa)</span>}
              </label>
            ))}
            <p className="text-sm text-ink-3">
              Es opción del contribuyente por cada bien (Decreto 3182, art. 30).
              {start && <> La primera cuota es la de {monthYear(start)}.</>}
            </p>
          </fieldset>
          <Field
            label="N° del asiento de compra"
            error={touched ? (errors.acquisition_number ?? acquisitionError) : acquisitionError}
            hint={acquisition.data ? `Asiento N° ${acquisition.data.number} del ${formatBookDate(acquisition.data.entry_date)}: ${acquisition.data.description}.` : 'Opcional: el asiento donde se registró la compra, para vincularlo.'}
          >
            {(p) => <Input {...p} inputMode="numeric" className="w-40 tabular-nums" value={draft.acquisition_number} onChange={(e) => set({ acquisition_number: e.target.value })} />}
          </Field>
        </Sheet>

        <Sheet className="flex flex-col gap-4 p-5">
          <div>
            <h2 className="font-semibold">Parámetros de depreciación</h2>
            <p className="mt-1 text-sm text-ink-2">Lineal mensual. Los propone la categoría; podés ajustarlos para este bien.</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Vida útil fiscal (meses)" error={shown('fiscal_life')} hint={/^\d+$/.test(draft.fiscal_life) ? monthsText(Number(draft.fiscal_life)) : undefined}>
              {(p) => <Input {...p} inputMode="numeric" className="tabular-nums" disabled={locked} value={draft.fiscal_life} onChange={(e) => set({ fiscal_life: e.target.value })} />}
            </Field>
            <Field label="Residual fiscal (% del costo)" error={shown('fiscal_rate')} hint="De 0 a 20 % (Ley 6380, art. 11).">
              {(p) => <Input {...p} inputMode="decimal" className="tabular-nums" disabled={locked} value={draft.fiscal_rate} onChange={(e) => set({ fiscal_rate: e.target.value })} />}
            </Field>
          </div>
          <Check
            label="Los parámetros contables son iguales a los fiscales"
            hint="Lo habitual. Desmarcalo solo si este bien lleva en los libros otra vida útil u otro residual."
            checked={draft.same_params}
            disabled={locked}
            onChange={(v) => set(v ? { same_params: true } : { same_params: false, life: draft.life || draft.fiscal_life, residual: draft.residual || (check.body ? toInputText(check.body.residual_value as string, 'PYG') : '') })}
          />
          {!draft.same_params && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Vida útil contable (meses)" error={shown('life')} hint={/^\d+$/.test(draft.life) ? monthsText(Number(draft.life)) : undefined}>
                  {(p) => <Input {...p} inputMode="numeric" className="tabular-nums" disabled={locked} value={draft.life} onChange={(e) => set({ life: e.target.value })} />}
                </Field>
                <Field label="Valor residual contable" error={shown('residual')} hint="En guaraníes; 0 si no tiene.">
                  {(p) => <AmountInput {...p} currency="PYG" disabled={locked} value={draft.residual} onChange={(t) => set({ residual: t })} />}
                </Field>
              </div>
              <Notice tone={check.nonDeductible ? 'warn' : 'neutral'} title="Parámetros contables distintos de los fiscales">
                La depreciación del libro usa los contables; la deducible para el IRE, los fiscales. Si la cuota contable es mayor que la fiscal, la
                diferencia es una <strong className="font-semibold">cuota no deducible</strong>: se registra igual en los libros, pero se suma al resultado
                fiscal en la liquidación del IRE (RG 77/2020, columna 20 del cuadro).
                {check.nonDeductible && (
                  <span className="mt-1 block">
                    Con estos valores, el primer año completo deja {formatMoney(check.nonDeductible, 'PYG')} no deducibles.
                  </span>
                )}
              </Notice>
            </>
          )}
        </Sheet>
      </div>

      <div className="sticky top-6 flex flex-col gap-4">
        <Sheet className="flex flex-col gap-4 p-5">
          <h2 className="font-semibold">Así se deprecia</h2>
          {start ? (
            <p className="text-sm">
              Desde <strong className="font-semibold">{monthYear(start)}</strong>, una cuota por mes.
            </p>
          ) : (
            <p className="text-sm text-ink-3">Elegí la fecha de adquisición para ver desde qué mes.</p>
          )}
          <PlanSummary title={draft.same_params ? 'Fiscal y contable' : 'Contable (los libros)'} plan={check.accounting} residual={check.body?.residual_value} />
          {!draft.same_params && <PlanSummary title="Fiscal (deducible en el IRE)" plan={check.fiscal} />}
          {save.error ? <ApiErrorNotice error={save.error} /> : null}
          {apiCode === 'DEPRECIATION_START_BEFORE_BOOKS' && (
            <Link to="/contabilidad/ejercicios" className="text-sm font-medium text-ledger hover:underline">
              Crear el ejercicio que falta
            </Link>
          )}
          {apiCode === 'DEPRECIATION_ALREADY_RUN' && (
            <Link to="/contabilidad/activos/depreciacion" className="text-sm font-medium text-ledger hover:underline">
              Ver las corridas de depreciación
            </Link>
          )}
          <Button type="submit" busy={save.isPending} disabled={touched && blocked}>
            {asset ? 'Guardar los cambios' : 'Dar de alta el bien'}
          </Button>
          <p className="text-sm text-ink-3">Dar de alta no genera asientos: la depreciación de cada mes se arma desde «Depreciación del mes».</p>
        </Sheet>
      </div>
    </form>
  )
}

export function AssetFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const perms = useAccountingPerms()
  const settings = useAccountingSettings()
  const categories = useAssetCategories()
  const asset = useQuery({ enabled: Boolean(id), queryKey: accountingKeys.asset(id ?? ''), queryFn: () => get<FixedAsset>(`/accounting/fixed-assets/${id}`) })
  const acquisition = useEntry(asset.data?.acquisition_entry_id ?? undefined)
  const back = id ? `/contabilidad/activos/${id}` : '/contabilidad/activos'
  const loading = settings.isPending || categories.isPending || (id && asset.isPending) || (asset.data?.acquisition_entry_id && acquisition.isPending)
  const usable = (categories.data ?? []).filter((c) => c.complete && !c.archived_at)

  return (
    <>
      <Link to={back} className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft size={15} aria-hidden />
        {id ? 'Volver al bien' : 'Volver a los bienes'}
      </Link>
      <PageHeader title={id ? `Editar ${asset.data?.name ?? 'el bien'}` : 'Nuevo bien de uso'} description="El costo y la categoría definen la cuota; nada se contabiliza al guardar." />
      {!perms.canManage ? (
        <ReadOnlyHint reason={perms.manageReason} />
      ) : loading ? (
        <Sheet className="flex flex-col gap-4 p-5">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
          <Skeleton className="h-24" />
        </Sheet>
      ) : asset.isError ? (
        <ApiErrorNotice error={asset.error} title="No se pudo cargar el bien." />
      ) : !id && usable.length === 0 ? (
        <Sheet>
          <EmptyState
            title="No hay categorías listas para usar"
            action={
              <Link to="/contabilidad/activos/categorias" className="font-medium text-ledger hover:underline">
                Ir a las categorías
              </Link>
            }
          >
            Cada bien necesita una categoría completa (vida útil, residual y las tres cuentas). Cargá las propuestas y completá la que corresponda.
          </EmptyState>
        </Sheet>
      ) : (
        <AssetForm
          asset={asset.data}
          acquisitionNumber={acquisition.data?.number ?? null}
          onSaved={(a) => {
            toast('ok', id ? `Bien «${a.name}» guardado.` : `Bien «${a.name}» dado de alta: se deprecia desde ${monthYear(a.depreciation_start)}.`)
            navigate(`/contabilidad/activos/${a.id}`)
          }}
        />
      )}
    </>
  )
}
