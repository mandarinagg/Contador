/**
 * Campos de un ingreso o egreso del registro anual (956) del IRP-RSP (D-143): sin timbrado
 * ni IVA, y con lo que pide cada tipo de la Tabla 4 (período, cuenta y banco, número de
 * empleador en IPS, descripción o comprobante asociado). Lo que muestra sale de
 * `registerFields` (`registerDraft.ts`).
 */
import type { ReactNode, Ref } from 'react'
import { Field, Input, Select } from '../../components/ui'
import { formatMoney } from '../../lib/money'
import { AmountInput, Check } from '../finance/components'
import { DoubtNote } from './components'
import { DOC_TYPE_LABELS, VOUCHER_TYPE_LABELS } from './labels'
import { checkCounterpartyRuc, maskTimbrado, readPyg, splitRucInput, sumBig } from './logic'
import { REGISTER_TYPES, registerFields, withRegisterType } from './registerDraft'
import type { DocType, RegisterDirection, VoucherType } from './types'
import type { DraftErrors, VoucherDraft } from './voucherDraft'

export function RegisterVoucherFields({
  draft: d,
  set,
  setDraft,
  errors,
  directionPicker,
  firstFieldRef,
}: {
  draft: VoucherDraft
  set: (patch: Partial<VoucherDraft>) => void
  setDraft: (d: VoucherDraft) => void
  errors: DraftErrors
  directionPicker: ReactNode
  firstFieldRef?: Ref<HTMLInputElement>
}) {
  const direction = d.direction as RegisterDirection
  const f = registerFields(direction, d.voucher_type)
  const none = f.counterpartyOptional && d.no_counterparty
  const rucCheck = !none && d.doc_type === 'ruc' ? checkCounterpartyRuc(d.ruc, d.dv) : null
  const taxed = readPyg(d.taxed_10)
  const untaxed = readPyg(d.exempt)
  const total = taxed.ok && untaxed.ok ? sumBig(taxed.value, f.split ? untaxed.value : '0') : null

  return (
    <>
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        {directionPicker}
        <Field label="Tipo" error={errors.voucher_type}>
          {(p) => (
            <Select {...p} className="w-80" value={d.voucher_type} onChange={(e) => setDraft(withRegisterType(d, e.target.value as VoucherType))}>
              {REGISTER_TYPES[direction].map((t) => (
                <option key={t} value={t}>
                  {VOUCHER_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        {f.period ? (
          <Field label="Período" error={errors.issued_on} hint="Mes y año">
            {(p) => (
              <Input
                {...p}
                type="month"
                className="w-44"
                value={d.issued_on.slice(0, 7)}
                onChange={(e) =>
                  set({
                    issued_on: e.target.value ? `${e.target.value}-01` : '',
                  })
                }
              />
            )}
          </Field>
        ) : (
          <Field label="Fecha" error={errors.issued_on}>
            {(p) => <Input {...p} type="date" className="w-40" value={d.issued_on} onChange={(e) => set({ issued_on: e.target.value })} />}
          </Field>
        )}
        <Field label={f.numberRequired ? 'Número' : 'Número (opcional)'} error={errors.number} hint={errors.number ? undefined : 'Del comprobante o de la transacción'}>
          {(p) => <Input {...p} className="w-48 tabular-nums" maxLength={20} value={d.number} onChange={(e) => set({ number: e.target.value })} />}
        </Field>
      </div>

      {/* Contraparte */}
      <div className="flex flex-col gap-3">
        {f.counterpartyOptional && (
          <Check
            label={d.voucher_type === 'ips_statement' ? 'Sin identificación (es el IPS)' : 'Sin identificación de la contraparte'}
            checked={d.no_counterparty}
            onChange={(v) => set({ no_counterparty: v })}
            hint="El formato admite este comprobante sin RUC ni documento."
          />
        )}
        <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)_4.5rem_minmax(0,1.6fr)] items-start gap-x-3 gap-y-3">
          {none ? (
            <div className="col-span-4">
              <Field
                label={d.voucher_type === 'ips_statement' ? 'Nombre (opcional)' : 'Nombre o descripción'}
                error={errors.name}
                hint={d.voucher_type === 'ips_statement' ? 'Vacío: «Instituto de Previsión Social».' : undefined}
              >
                {(p) => <Input {...p} ref={firstFieldRef} maxLength={200} value={d.name} onChange={(e) => set({ name: e.target.value })} />}
              </Field>
            </div>
          ) : (
            <>
              <Field label="Identificación" error={errors.doc_type}>
                {(p) => (
                  <Select {...p} value={d.doc_type} disabled={f.docTypes.length === 1} onChange={(e) => set({ doc_type: e.target.value as DocType })}>
                    {f.docTypes.map((t) => (
                      <option key={t} value={t}>
                        {DOC_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </Select>
                )}
              </Field>
              {d.doc_type === 'ruc' ? (
                <>
                  <Field label="RUC" error={errors.ruc} hint="Sin el DV.">
                    {(p) => (
                      <Input
                        {...p}
                        ref={firstFieldRef}
                        className="tabular-nums"
                        value={d.ruc}
                        onChange={(e) => {
                          const { ruc, dv } = splitRucInput(e.target.value)
                          set({ ruc, dv: dv ?? d.dv })
                        }}
                      />
                    )}
                  </Field>
                  <Field label="DV" error={errors.dv ?? (rucCheck?.kind === 'wrong_dv' ? `Para ese RUC el dígito verificador es ${rucCheck.expected}.` : undefined)}>
                    {(p) => (
                      <Input
                        {...p}
                        inputMode="numeric"
                        maxLength={1}
                        className="text-center tabular-nums"
                        value={d.dv}
                        onChange={(e) =>
                          set({
                            dv: e.target.value.replace(/\D/g, '').slice(0, 1),
                          })
                        }
                      />
                    )}
                  </Field>
                </>
              ) : (
                <div className="col-span-2">
                  <Field label="Número de documento" error={errors.document}>
                    {(p) => <Input {...p} ref={firstFieldRef} maxLength={20} value={d.document} onChange={(e) => set({ document: e.target.value })} />}
                  </Field>
                </div>
              )}
              <Field label={direction === 'income' ? 'Nombre de quien paga' : 'Nombre o razón social'} error={errors.name}>
                {(p) => <Input {...p} maxLength={200} value={d.name} onChange={(e) => set({ name: e.target.value })} />}
              </Field>
            </>
          )}
        </div>
      </div>

      {/* Lo que pide el tipo */}
      {(f.account || f.ipsEmployer || f.description || f.related) && (
        <div className="grid grid-cols-2 items-start gap-x-3 gap-y-3">
          {f.account && (
            <>
              <Field label="Número de cuenta o de tarjeta" error={errors.account_number}>
                {(p) => <Input {...p} maxLength={30} value={d.account_number} onChange={(e) => set({ account_number: e.target.value })} />}
              </Field>
              <Field label="Banco, financiera o cooperativa" error={errors.bank_name}>
                {(p) => <Input {...p} maxLength={250} value={d.bank_name} onChange={(e) => set({ bank_name: e.target.value })} />}
              </Field>
            </>
          )}
          {f.ipsEmployer && (
            <Field label="Número de empleador en IPS" error={errors.ips_employer_number}>
              {(p) => <Input {...p} maxLength={30} className="tabular-nums" value={d.ips_employer_number} onChange={(e) => set({ ips_employer_number: e.target.value })} />}
            </Field>
          )}
          {f.description && (
            <div className="col-span-2">
              <Field label="Tipo de documento" error={errors.document_description} hint="Qué es: «Recibo de honorarios», «Boleta de pago»…">
                {(p) => <Input {...p} maxLength={50} value={d.document_description} onChange={(e) => set({ document_description: e.target.value })} />}
              </Field>
            </div>
          )}
          {f.related && (
            <>
              <Field label={`Número de la ${direction === 'income' ? 'venta' : 'compra'} a crédito`} error={errors.related_number} hint="001-001-0000001">
                {(p) => <Input {...p} className="tabular-nums" maxLength={15} placeholder="001-001-0000001" value={d.related_number} onChange={(e) => set({ related_number: e.target.value })} />}
              </Field>
              <Field label="Timbrado de ese comprobante" error={errors.related_timbrado}>
                {(p) => (
                  <Input
                    {...p}
                    inputMode="numeric"
                    className="tabular-nums"
                    placeholder="12345678"
                    value={d.related_timbrado}
                    onChange={(e) => set({ related_timbrado: maskTimbrado(e.target.value) })}
                  />
                )}
              </Field>
            </>
          )}
        </div>
      )}

      {/* Importes: el formato pide gravado y no gravado en INGRESOS y solo el total en EGRESOS. */}
      <section aria-labelledby="register-amounts-h" className="rounded-sm border border-line px-4">
        <h3 id="register-amounts-h" className="border-b border-line py-2.5 font-medium">
          Importes
        </h3>
        <div className="grid grid-cols-2 items-start gap-x-4 gap-y-3 py-3">
          <Field label={f.split ? 'Monto gravado (IRP)' : 'Monto total'} error={errors.taxed_10 ?? errors.amounts}>
            {(p) => <AmountInput {...p} currency="PYG" value={d.taxed_10} onChange={(t) => set({ taxed_10: t })} />}
          </Field>
          {f.split && (
            <Field label="Monto no gravado o exonerado" error={errors.exempt}>
              {(p) => <AmountInput {...p} currency="PYG" value={d.exempt} onChange={(t) => set({ exempt: t })} />}
            </Field>
          )}
        </div>
        <div className="flex items-baseline justify-end gap-6 border-t border-line py-3 text-sm">
          <span className="text-ink-2">
            Total{' '}
            <span className="ledger-rule ml-1 inline-block min-w-28 text-right text-md font-semibold text-ink tabular-nums" data-testid="voucher-total">
              {total !== null ? formatMoney(total, 'PYG') : '—'}
            </span>
          </span>
        </div>
      </section>

      {/* Imputación: sin IVA (el registro anual es de quien no es contribuyente del IVA). */}
      <fieldset className="flex flex-wrap items-start gap-x-6 gap-y-2">
        <legend className="mb-1.5 text-sm font-medium text-ink-2">Imputa a</legend>
        <Check label="IRP" checked={d.imputes_irp} onChange={(v) => set({ imputes_irp: v })} hint="Renta personal (IRP-RSP)" />
        <Check label="IRE" checked={d.imputes_ire} onChange={(v) => set({ imputes_ire: v })} hint="Si además tenés el IRE" />
      </fieldset>
      <DoubtNote codes={['D-PF-18', 'D-PF-7']} />
    </>
  )
}
