/** Selectores de cuenta, categoría y contraparte con la jerarquía y los archivados bien tratados. */
import type { SelectHTMLAttributes } from 'react'
import { Select } from '../../components/ui'
import { byName } from './labels'
import type { Account, Category, Counterparty } from './types'

type SelectProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'>

/** Cuentas activas (más la elegida si está archivada), con su moneda a la vista. */
export function AccountSelect({ accounts, empty, ...props }: SelectProps & { accounts: Account[]; empty?: string }) {
  const options = accounts.filter((a) => !a.archived_at || a.id === props.value).sort(byName)
  return (
    <Select {...props}>
      {empty !== undefined && <option value="">{empty}</option>}
      {options.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} ({a.currency}){a.archived_at ? ' — archivada' : ''}
        </option>
      ))}
    </Select>
  )
}

/** Categorías agrupadas por tipo, subcategorías debajo de su padre. */
export function CategorySelect({
  categories,
  empty = 'Sin categoría',
  first = 'expense',
  ...props
}: SelectProps & { categories: Category[]; empty?: string; first?: 'income' | 'expense' }) {
  const usable = categories.filter((c) => !c.archived_at || c.id === props.value)
  const kinds = first === 'expense' ? (['expense', 'income'] as const) : (['income', 'expense'] as const)
  return (
    <Select {...props}>
      <option value="">{empty}</option>
      {kinds.map((kind) => {
        const ofKind = usable.filter((c) => c.kind === kind)
        const top = ofKind.filter((c) => !c.parent_id || !ofKind.some((p) => p.id === c.parent_id)).sort(byName)
        if (top.length === 0) return null
        return (
          <optgroup key={kind} label={kind === 'expense' ? 'Gastos' : 'Ingresos'}>
            {top.flatMap((c) => [
              <option key={c.id} value={c.id}>
                {c.name}
              </option>,
              ...ofKind
                .filter((ch) => ch.parent_id === c.id)
                .sort(byName)
                .map((ch) => (
                  <option key={ch.id} value={ch.id}>
                    {'   '}
                    {c.name} › {ch.name}
                  </option>
                )),
            ])}
          </optgroup>
        )
      })}
    </Select>
  )
}

export function CounterpartySelect({ counterparties, empty = 'Sin contraparte', ...props }: SelectProps & { counterparties: Counterparty[]; empty?: string }) {
  const options = counterparties.filter((c) => !c.archived_at || c.id === props.value).sort(byName)
  return (
    <Select {...props}>
      <option value="">{empty}</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>
          {c.name}
          {c.ruc ? ` (${c.ruc}-${c.ruc_check_digit})` : ''}
        </option>
      ))}
    </Select>
  )
}
