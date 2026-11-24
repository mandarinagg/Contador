/**
 * Editor de una plantilla de asiento recurrente (D-061): las mismas líneas y el mismo teclado
 * que el editor de asientos, más el día del mes y la vigencia. La plantilla tiene que balancear.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Button, Field, Input, Notice, PageHeader, Sheet, Skeleton } from '../../../components/ui'
import { useToast } from '../../../components/ui/toast'
import { get, patch, post } from '../../../services/api'
import { ApiErrorNotice, Check, ReadOnlyHint, Th } from '../../finance/components'
import { todayIso } from '../../finance/labels'
import { isZeroPyg } from '../amounts'
import { postableAccounts } from '../chartTree'
import { Pyg } from '../components'
import { accountingKeys, useAccountingPerms, useAccountsById, useChart, useCostCenters, useInvalidateAccounting } from '../data'
import { buildLines, emptyLine, type LineDraft, missingCenters, totalsOf } from '../editor'
import { LinesEditor } from '../LinesEditor'
import type { RecurringTemplate, RecurringTemplateIn, TemplateStatus } from '../types3b'
import { linesFromTemplate, type TemplateHeader, templateHeaderErrors, validityText } from './logic'

function TemplateForm({ template }: { template?: RecurringTemplate }) {
  const navigate = useNavigate()
  const toast = useToast()
  const invalidate = useInvalidateAccounting()
  const chart = useChart()
  const centers = useCostCenters()
  const byId = useAccountsById(chart.data?.accounts)
  const options = useMemo(() => postableAccounts(chart.data?.accounts ?? []), [chart.data])
  const kindOf = (id: string) => byId.get(id)?.kind
  const [header, setHeader] = useState<TemplateHeader>(() => ({
    description: template?.description ?? '',
    document_reference: template?.document_reference ?? '',
    day_of_month: template ? String(template.day_of_month) : '5',
    start_date: template?.start_date ?? `${todayIso().slice(0, 7)}-01`,
    end_date: template?.end_date ?? '',
    status: (template?.status as TemplateStatus) ?? 'active',
  }))
  const [lines, setLines] = useState<LineDraft[]>(() => (template ? linesFromTemplate(template) : [emptyLine(), emptyLine()]))
  const [showErrors, setShowErrors] = useState(false)
  const set = (p: Partial<TemplateHeader>) => setHeader((h) => ({ ...h, ...p }))
  const headerErrors = templateHeaderErrors(header)
  const built = buildLines(lines, kindOf)
  const totals = totalsOf(lines)
  const general =
    built.general ?? (built.lines.length < 2 ? 'Una plantilla lleva al menos dos líneas.' : !totals.balanced ? 'La plantilla tiene que balancear: el debe igual al haber.' : undefined)
  const missing = missingCenters(lines, kindOf, Boolean(chart.data?.cost_centers_required))
  const valid = Object.keys(headerErrors).length === 0 && Object.keys(built.errors).length === 0 && !general

  const save = useMutation({
    mutationFn: () => {
      const body: RecurringTemplateIn = {
        description: header.description.trim(),
        document_reference: header.document_reference.trim() || null,
        day_of_month: Number(header.day_of_month),
        start_date: header.start_date,
        end_date: header.end_date || null,
        status: header.status,
        lines: built.lines,
      }
      return template ? patch<RecurringTemplate>(`/accounting/recurring/${template.id}`, body) : post<RecurringTemplate>('/accounting/recurring', body)
    },
    onSuccess: (t) => {
      invalidate()
      toast('ok', template ? `Plantilla «${t.description}» guardada.` : `Plantilla «${t.description}» creada.`)
      navigate('/contabilidad/recurrentes')
    },
  })

  if (chart.isPending) return <Skeleton className="h-64" />
  return (
    <form
      noValidate
      onKeyDown={(e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
          e.preventDefault()
          setShowErrors(true)
          if (valid && !save.isPending) save.mutate()
        }
      }}
      onSubmit={(e) => {
        e.preventDefault()
        setShowErrors(true)
        if (valid) save.mutate()
      }}
    >
      <Sheet className="mb-5 grid grid-cols-[minmax(0,1fr)_14rem] gap-x-5 gap-y-4 p-5">
        <Field label="Descripción" error={showErrors ? headerErrors.description : undefined} hint="Va en cada asiento generado.">
          {(p) => <Input {...p} maxLength={500} placeholder="Alquiler de la oficina" value={header.description} onChange={(e) => set({ description: e.target.value })} />}
        </Field>
        <Field label="Comprobante" hint="Opcional: contrato, n° de factura habitual.">
          {(p) => <Input {...p} maxLength={100} value={header.document_reference} onChange={(e) => set({ document_reference: e.target.value })} />}
        </Field>
        <div className="col-span-2 grid grid-cols-[9rem_12rem_12rem_1fr] items-start gap-5">
          <Field label="Día del mes" error={showErrors ? headerErrors.day_of_month : undefined} hint="29 a 31: el último día si el mes es más corto.">
            {(p) => <Input {...p} inputMode="numeric" className="tabular-nums" value={header.day_of_month} onChange={(e) => set({ day_of_month: e.target.value })} />}
          </Field>
          <Field label="Rige desde" error={showErrors ? headerErrors.start_date : undefined}>
            {(p) => <Input {...p} type="date" value={header.start_date} onChange={(e) => set({ start_date: e.target.value })} />}
          </Field>
          <Field label="Hasta" error={showErrors ? headerErrors.end_date : undefined} hint="Vacío: sin fin.">
            {(p) => <Input {...p} type="date" value={header.end_date} onChange={(e) => set({ end_date: e.target.value })} />}
          </Field>
          <div className="pt-7">
            <Check
              label="Activa"
              hint="En pausa no se genera ni aparece en el aviso."
              checked={header.status === 'active'}
              onChange={(v) => set({ status: v ? 'active' : 'paused' })}
            />
          </div>
        </div>
      </Sheet>

      <LinesEditor
        lines={lines}
        setLines={setLines}
        errors={showErrors ? built.errors : {}}
        options={options}
        known={byId}
        kindOf={kindOf}
        centers={centers.data ?? []}
        missingCenterKeys={totals.balanced ? missing : []}
        allowFx={false}
        label="Líneas de la plantilla"
      />

      <div className="mt-4 flex flex-col gap-3">
        {showErrors && general && <Notice tone="bad" title={general} />}
        {missing.length > 0 && totals.balanced && (
          <Notice tone="warn" title="Faltan centros de costos">
            La empresa exige centro en las líneas de ingreso y gasto: la plantilla se guarda, pero cada borrador generado va a pedir el centro antes de
            contabilizarse.
          </Notice>
        )}
        {save.error ? <ApiErrorNotice error={save.error} title="No se guardó la plantilla." /> : null}
        <p className="text-sm text-ink-3">
          Las plantillas van en guaraníes. Para un importe en moneda extranjera, generá el borrador y completá la cotización del mes en el asiento.
        </p>
        <div className="flex justify-end gap-2">
          <Link to="/contabilidad/recurrentes" className="inline-flex h-9 items-center rounded-sm px-3.5 font-medium text-ink-2 hover:bg-sunken hover:text-ink">
            Cancelar
          </Link>
          <Button type="submit" busy={save.isPending}>
            {template ? 'Guardar la plantilla' : 'Crear la plantilla'}
          </Button>
        </div>
      </div>
    </form>
  )
}

function TemplateView({ template, reason }: { template: RecurringTemplate; reason: string }) {
  return (
    <>
      <p className="mb-4 text-ink-2">
        Día {template.day_of_month}, {validityText(template)}. {template.status === 'active' ? 'Activa.' : 'En pausa.'}
      </p>
      <Sheet>
        <table className="w-full" aria-label="Líneas de la plantilla">
          <thead className="border-b border-line bg-sunken text-sm text-ink-2">
            <tr>
              <Th>Cuenta</Th>
              <Th>Descripción</Th>
              <Th align="right" className="w-36">
                Debe
              </Th>
              <Th align="right" className="w-36">
                Haber
              </Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {template.lines.map((l) => (
              <tr key={l.line_no}>
                <td className="px-4 py-2">
                  <span className="mr-2 text-ink-2 tabular-nums">{l.account_code}</span>
                  {l.account_name}
                </td>
                <td className="px-4 py-2 text-ink-2">{l.description}</td>
                <td className="px-4 py-2 text-right">{isZeroPyg(l.debit) ? null : <Pyg value={l.debit} />}</td>
                <td className="px-4 py-2 text-right">{isZeroPyg(l.credit) ? null : <Pyg value={l.credit} />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Sheet>
      <div className="mt-3">
        <ReadOnlyHint reason={reason} />
      </div>
    </>
  )
}

export function TemplatePage() {
  const { id } = useParams()
  const perms = useAccountingPerms()
  const template = useQuery({
    enabled: Boolean(id),
    queryKey: [...accountingKeys.recurring(), id],
    queryFn: () => get<RecurringTemplate>(`/accounting/recurring/${id}`),
  })
  return (
    <>
      <Link to="/contabilidad/recurrentes" className="mb-3 inline-flex items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft size={15} aria-hidden />
        Volver a los asientos recurrentes
      </Link>
      <PageHeader
        title={id ? (template.data?.description ?? 'Plantilla') : 'Nueva plantilla recurrente'}
        description="Las líneas del asiento que se repite. Cada mes se genera un borrador con estas líneas y la fecha del día elegido."
      />
      {!perms.canManage && !id ? (
        <ReadOnlyHint reason={perms.manageReason} />
      ) : id && template.isPending ? (
        <Skeleton className="h-64" />
      ) : id && template.isError ? (
        <ApiErrorNotice error={template.error} title="No se pudo cargar la plantilla." />
      ) : !perms.canManage && template.data ? (
        <TemplateView template={template.data} reason={perms.manageReason} />
      ) : (
        <TemplateForm key={template.data?.id ?? 'nueva'} template={template.data} />
      )}
    </>
  )
}
