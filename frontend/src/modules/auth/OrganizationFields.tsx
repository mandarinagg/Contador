import { Field, Input, Select } from '../../components/ui'
import { COMPANY_LEGAL_FORMS } from '../../lib/format'
import type { LegalForm } from '../../types/api'
import { expectedCheckDigit, isPerson, type OrganizationDraft } from './organizationDraft'

/**
 * Campos de identificación de una organización, compartidos por la configuración inicial y el alta de
 * otra organización. `errors` trae los mensajes por campo (`legal_name`, `ruc`...); con `withRuc` se
 * piden también el RUC y su dígito verificador. La primera elección es empresa o persona física (D-141).
 */
export function OrganizationFields({
  value,
  onChange,
  errors = {},
  withRuc = false,
  autoFocus = false,
}: {
  value: OrganizationDraft
  onChange: (next: OrganizationDraft) => void
  errors?: Record<string, string | undefined>
  withRuc?: boolean
  autoFocus?: boolean
}) {
  const expected = expectedCheckDigit(value.ruc)
  const dvMismatch = expected !== null && value.ruc_check_digit !== '' && value.ruc_check_digit !== expected
  const person = isPerson(value.legal_form)
  return (
    <>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="mb-1 text-sm font-medium text-ink-2">Es una</legend>
        <div className="flex gap-5">
          {[
            { id: 'company', label: 'Empresa', checked: !person, form: 'EAS' as const },
            { id: 'person', label: 'Persona física', checked: person, form: 'PERSONA_FISICA' as const },
          ].map((o) => (
            <label key={o.id} className="flex items-center gap-2">
              <input
                type="radio"
                name="organization-kind"
                checked={o.checked}
                onChange={() => !o.checked && onChange({ ...value, legal_form: o.form })}
              />
              {o.label}
            </label>
          ))}
        </div>
      </fieldset>
      {person ? (
        <>
          <Field label="Nombres" error={errors.first_names}>
            {(p) => <Input {...p} required autoFocus={autoFocus} value={value.first_names} onChange={(e) => onChange({ ...value, first_names: e.target.value })} />}
          </Field>
          <Field label="Apellidos" error={errors.last_names}>
            {(p) => <Input {...p} required value={value.last_names} onChange={(e) => onChange({ ...value, last_names: e.target.value })} />}
          </Field>
        </>
      ) : (
        <Field label="Razón social" error={errors.legal_name}>
          {(p) => <Input {...p} required autoFocus={autoFocus} value={value.legal_name} onChange={(e) => onChange({ ...value, legal_name: e.target.value })} />}
        </Field>
      )}
      <Field label="Nombre de fantasía" hint="Opcional. Es el nombre que se muestra en la aplicación." error={errors.trade_name}>
        {(p) => <Input {...p} value={value.trade_name} onChange={(e) => onChange({ ...value, trade_name: e.target.value })} />}
      </Field>
      {!person && (
        <Field label="Forma jurídica">
          {(p) => (
            <Select {...p} value={value.legal_form} onChange={(e) => onChange({ ...value, legal_form: e.target.value as LegalForm })}>
              {COMPANY_LEGAL_FORMS.map(([v, label]) => (
                <option key={v} value={v}>
                  {label}
                </option>
              ))}
            </Select>
          )}
        </Field>
      )}
      {withRuc && (
        <>
          <Field label={person ? 'RUC (es tu cédula)' : 'RUC'} hint="Opcional. Sin puntos ni dígito verificador." error={errors.ruc}>
            {(p) => (
              <Input {...p} inputMode="numeric" maxLength={8} value={value.ruc} onChange={(e) => onChange({ ...value, ruc: e.target.value.replace(/\D/g, '') })} />
            )}
          </Field>
          <Field
            label="Dígito verificador"
            error={dvMismatch ? `Para ese RUC el dígito verificador es ${expected}.` : errors.ruc_check_digit}
          >
            {(p) => (
              <Input
                {...p}
                inputMode="numeric"
                maxLength={1}
                className="w-20"
                value={value.ruc_check_digit}
                onChange={(e) => onChange({ ...value, ruc_check_digit: e.target.value.replace(/\D/g, '') })}
              />
            )}
          </Field>
        </>
      )}
    </>
  )
}
