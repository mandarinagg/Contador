/**
 * Activos fijos (fase 3B): bienes, categorías, depreciación del mes y cuadro anual. El aviso de
 * que las vidas útiles y los residuales son propuestas sin validar está siempre a la vista
 * (D-056, BR-ACC-14), como el del plan de cuentas (D-038).
 */
import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router'
import { PageHeader } from '../../../components/ui'
import { cx } from '../../../lib/cx'
import { useAssetCategories } from '../data'

const TABS = [
  { to: '/contabilidad/activos', label: 'Bienes', end: true },
  { to: '/contabilidad/activos/categorias', label: 'Categorías' },
  { to: '/contabilidad/activos/depreciacion', label: 'Depreciación del mes' },
  { to: '/contabilidad/activos/cuadro', label: 'Cuadro de depreciación' },
]

/** Estado de validación de las categorías, en una franja (lo que diga, lo dice siempre). */
export function CategoryValidationStrip() {
  const categories = useAssetCategories()
  const list = (categories.data ?? []).filter((c) => !c.archived_at)
  if (categories.isPending) return <div className="mb-5 h-9" />
  const validated = list.filter((c) => c.validation_status === 'validated').length
  const all = list.length > 0 && validated === list.length
  return (
    <div
      role="note"
      aria-label="Estado de las vidas útiles"
      data-print="hide"
      className={cx('mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-4 py-2 text-sm', all ? 'border-line bg-ledger-soft' : 'border-amber/40 bg-amber-soft')}
    >
      {all ? <ShieldCheck size={16} className="text-ledger" aria-hidden /> : <ShieldAlert size={16} className="text-amber" aria-hidden />}
      {list.length === 0 ? (
        <span>
          <span className="font-semibold text-amber">Todavía no hay categorías de activo fijo.</span> Las propuestas salen del Decreto 3182/2019, art. 31, y
          están sin validar.
        </span>
      ) : all ? (
        <span>
          <span className="font-semibold text-ledger">Las {list.length} categorías en uso están validadas</span> por un contador.
        </span>
      ) : (
        <span>
          <span className="font-semibold text-amber">Vidas útiles y residuales: propuestas sin validar.</span> {validated} de {list.length} categorías validadas
          por un contador. Hasta entonces, la depreciación y el cuadro son un cálculo de trabajo.
        </span>
      )}
      <Link to="/contabilidad/activos/categorias" className="ml-auto font-medium text-ledger hover:underline">
        {list.length === 0 ? 'Cargar las categorías' : 'Ver las categorías'}
      </Link>
    </div>
  )
}

export function AssetsLayout() {
  return (
    <>
      <div data-print="hide">
        <PageHeader
          title="Activos fijos"
          description="Los bienes de uso de la empresa, su depreciación lineal mensual y el cuadro anual. Nada se contabiliza solo: cada mes la depreciación es un borrador que alguien revisa y contabiliza."
        />
      </div>
      <CategoryValidationStrip />
      <nav aria-label="Secciones de activos fijos" data-print="hide" className="mb-5 flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              cx(
                '-mb-px border-b-2 px-3.5 py-2 transition-colors',
                isActive ? 'border-ledger font-semibold text-ink' : 'border-transparent text-ink-2 hover:border-line-strong hover:text-ink',
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  )
}
