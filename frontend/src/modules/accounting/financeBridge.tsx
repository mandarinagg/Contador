/** Piezas de contabilidad que se muestran dentro de las pantallas de finanzas (D-041, D-048). */
import { BookCheck, BookDashed, BookX } from 'lucide-react'
import { Link } from 'react-router'
import { Field, Notice } from '../../components/ui'
import { cx } from '../../lib/cx'
import { LedgerAccountSelect } from './components'
import type { LedgerMapping } from './entryRefs'
import type { EntryRef, LedgerAccount } from './types'

/** Estado contable de un movimiento de la empresa: N°, borrador o revertido, con enlace. */
export function JournalEntryLink({ entry, className }: { entry: EntryRef; className?: string }) {
  const posted = entry.status === 'posted'
  const draft = entry.status === 'draft'
  const Icon = posted ? BookCheck : draft ? BookDashed : BookX
  const text = posted ? `Asiento N° ${entry.number}` : draft ? 'Asiento en borrador' : `Asiento N° ${entry.number} revertido`
  return (
    <Link
      to={`/contabilidad/asientos/${entry.id}`}
      className={cx(
        'inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium hover:underline',
        posted ? 'bg-ledger-soft text-ledger' : draft ? 'bg-amber-soft text-amber' : 'bg-sunken text-ink-2',
        className,
      )}
      title={posted ? 'Contabilizado: ver el asiento' : draft ? 'Borrador: falta revisarlo y contabilizarlo' : 'El asiento se revirtió: se puede proponer otro'}
    >
      <Icon size={13} aria-hidden />
      {text}
    </Link>
  )
}

export function PostedEntryNotice({ entry, action }: { entry: EntryRef; action: 'void' | 'edit' }) {
  return (
    <Notice tone="warn" title={`Tiene el asiento N° ${entry.number} contabilizado`}>
      {action === 'void'
        ? 'Un movimiento con asiento contabilizado no se anula: revertí primero el asiento y después anulá el movimiento. '
        : 'La fecha, el importe y la cuenta no se cambian mientras el asiento esté contabilizado. Para corregirlos, revertí primero el asiento. '}
      <Link to={`/contabilidad/asientos/${entry.id}`} className="font-medium underline">
        Ir al asiento N° {entry.number}
      </Link>
    </Notice>
  )
}

/** Campo «Cuenta contable» de una cuenta o categoría de finanzas de la empresa. */
export function LedgerAccountField({
  mapping,
  kinds,
  value,
  onChange,
  hint,
}: {
  mapping: LedgerMapping
  kinds: LedgerAccount['kind'][]
  value: string
  onChange: (id: string) => void
  hint: string
}) {
  if (!mapping.show) return null
  if (mapping.canEdit && mapping.accounts.length === 0) {
    return (
      <div>
        <p className="text-sm font-medium text-ink-2">Cuenta contable</p>
        <p className="mt-1 text-sm text-ink-2">
          Todavía no hay plan de cuentas.{' '}
          <Link to="/contabilidad/plan" className="font-medium text-ledger underline">
            Cargalo en Contabilidad
          </Link>{' '}
          y después elegí la cuenta acá.
        </p>
      </div>
    )
  }
  return (
    <Field label="Cuenta contable" hint={mapping.canEdit ? hint : 'La configura quien prepara la contabilidad (propietario, administrador o contador).'}>
      {(p) => <LedgerAccountSelect {...p} disabled={!mapping.canEdit} accounts={mapping.accounts} kinds={kinds} value={value} onChange={onChange} />}
    </Field>
  )
}

/** Código y nombre de la cuenta contable, o «Sin cuenta contable». */
export function LedgerAccountTag({
  mapping,
  id,
  inherited,
}: {
  mapping: LedgerMapping
  id: string | null | undefined
  inherited?: { id: string; from: string } | null
}) {
  if (!mapping.show) return null
  const own = id ? mapping.byId.get(id) : undefined
  const parent = !own && inherited ? mapping.byId.get(inherited.id) : undefined
  if (own)
    return (
      <span className="text-sm text-ink-2" title={`Cuenta contable: ${own.code} ${own.name}`}>
        <span className="tabular-nums">{own.code}</span> {own.name}
      </span>
    )
  if (parent)
    return (
      <span className="text-sm text-ink-3" title={`Usa la cuenta contable de «${inherited?.from}»`}>
        <span className="tabular-nums">{parent.code}</span> (la de «{inherited?.from}»)
      </span>
    )
  return <span className="text-sm text-ink-3">Sin cuenta contable</span>
}
