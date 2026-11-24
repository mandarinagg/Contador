/** Detalle de un movimiento: todo lo que se sabe de él y, en la empresa, su asiento contable. */
import { Ban, BookPlus, Pencil } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge, Button } from '../../components/ui'
import { formatDateTime } from '../../lib/format'
import { canPropose } from '../accounting/entryRefs'
import { JournalEntryLink } from '../accounting/financeBridge'
import { Amount } from './components'
import { categoryLabel, formatBookDate } from './labels'
import type { Account, Category, Counterparty, Transaction } from './types'

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  )
}

export function TransactionDetail({
  tx,
  business,
  account,
  categories,
  counterparty,
  canWrite,
  canManageAccounting,
  onEdit,
  onVoid,
  onPropose,
}: {
  tx: Transaction
  business: boolean
  account?: Account
  categories: Category[]
  counterparty?: Counterparty
  canWrite: boolean
  canManageAccounting: boolean
  onEdit: () => void
  onVoid: () => void
  onPropose: () => void
}) {
  const voided = Boolean(tx.voided_at)
  const proposable = business && canManageAccounting && canPropose(tx)
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-lg font-semibold break-words">{tx.description}</p>
          <p className="mt-1 flex flex-wrap gap-1.5">
            {tx.transfer_group_id && <Badge>Transferencia</Badge>}
            {tx.source === 'import' && <Badge>Importado</Badge>}
            {voided ? <Badge tone="bad">Anulado</Badge> : !tx.reviewed_at && <Badge tone="warn">Sin revisar</Badge>}
          </p>
        </div>
        <p className="shrink-0 text-xl">
          <Amount value={tx.amount} currency={tx.currency} flow strong />
        </p>
      </div>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
        <Item label="Fecha">{formatBookDate(tx.booked_on)}</Item>
        <Item label="Cuenta">{account?.name ?? 'Cuenta'}</Item>
        <Item label="Categoría">
          {tx.transfer_group_id ? <span className="text-ink-3">No aplica</span> : (categoryLabel(categories, tx.category_id) ?? <span className="text-ink-3">Sin categoría</span>)}
        </Item>
        <Item label="Contraparte">{counterparty?.name ?? <span className="text-ink-3">Ninguna</span>}</Item>
        <Item label="Referencia">{tx.reference ?? <span className="text-ink-3">Sin referencia</span>}</Item>
        <Item label="Cargado">{formatDateTime(tx.created_at)}</Item>
        {voided && (
          <div className="col-span-2">
            <Item label="Anulado">
              {formatDateTime(tx.voided_at as string)}. Motivo: {tx.void_reason}
            </Item>
          </div>
        )}
      </dl>

      {business && (
        <section aria-labelledby="tx-accounting" className="rounded-sm border border-line px-4 py-3">
          <h3 id="tx-accounting" className="font-medium">
            Contabilidad
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-2">
              {tx.journal_entry ? (
                <span className="flex flex-wrap items-center gap-2">
                  <JournalEntryLink entry={tx.journal_entry} />
                  {tx.journal_entry.status === 'posted'
                    ? 'Ya está en los libros. Para anular el movimiento o cambiar su fecha, importe o cuenta, primero se revierte el asiento.'
                    : tx.journal_entry.status === 'draft'
                      ? 'Falta revisarlo y contabilizarlo.'
                      : 'Se revirtió: se puede proponer un asiento nuevo.'}
                </span>
              ) : voided ? (
                'Anulado: no lleva asiento.'
              ) : tx.transfer_group_id ? (
                'Las transferencias no se proponen solas: se cargan como asiento manual con las dos cuentas.'
              ) : (
                'Sin asiento todavía.'
              )}
            </p>
            {proposable && (
              <Button variant="secondary" onClick={onPropose}>
                <BookPlus size={16} />
                Proponer asiento
              </Button>
            )}
          </div>
        </section>
      )}

      {canWrite && !voided && (
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button variant="ghost" className="hover:text-debit" onClick={onVoid}>
            <Ban size={15} />
            Anular
          </Button>
          <Button variant="secondary" onClick={onEdit}>
            <Pencil size={15} />
            Editar
          </Button>
        </div>
      )}
    </div>
  )
}
