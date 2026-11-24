# Especificación: Fase 3B, Contabilidad (activos fijos, centros de costos, recurrentes, libros exportables)

**Estado:** aprobada por el jefe de proyecto (2026-11-24). Se apoya en el núcleo ya implementado.
- **Núcleo:** `docs/specs/FASE3_CONTABILIDAD.md`, D-035 a D-055.
- **Decisiones nuevas:** D-056 a D-063.
- **Reglas nuevas:** BR-ACC-13 a BR-ACC-18.
- **Fuente de vidas útiles:** `docs/research/DEPRECIACION_PY.md` y `docs/research/categorias_activo_fijo_candidatas.yaml`, sin validar.

## 0. Alcance

**Entra:**
- activos fijos con depreciación lineal mensual y baja;
- centros de costos como dimensión de las líneas;
- plantillas de asientos recurrentes;
- saldos iniciales en el balance de comprobación;
- exportación de los libros y estados a XLSX, e impresión a PDF desde la interfaz.

**Queda fuera (fase 4 o posterior):**
- revalúo fiscal;
- depreciación acelerada o por unidades de producción;
- distribución automática de costos entre centros;
- presentación del Cuadro de Revalúo y Depreciación (RG 49/2014, Anexo 6) en su formato oficial. En esta tanda alcanza con el cuadro de depreciación interno de §2.1.

## 1. Decisiones de modelo

| ID | Decisión | Motivo |
|---|---|---|
| D-056 | **Categorías de activo fijo** (`accounting.asset_categories`) por organización: nombre, vida útil en meses, las tres cuentas contables (activo, depreciación acumulada y gasto de depreciación), fuente, referencia legal y `validation_status` (`pending` o `validated`). Se cargan a pedido desde las **candidatas** de la investigación, copiadas en el paquete como el plan propuesto (D-037). Una candidata sin vida útil se carga con la vida útil vacía y la categoría **no se puede usar** hasta completarla. | Las vidas útiles son reglas fiscales: no se inventan ni se presentan como verificadas (prompt maestro, módulo 4) |
| D-057 | **Activo fijo:** el costo de adquisición y el valor residual se guardan en PYG enteros. La vida útil se copia de la categoría al dar de alta el bien y puede cambiarse solo mientras no tenga depreciaciones contabilizadas. La depreciación es **lineal mensual** desde el mes de inicio (por defecto, el mes siguiente al de alta; configurable si la investigación indica otra regla). Cuota = (costo − residual) / vida útil, en guaraníes enteros: las cuotas se redondean hacia abajo y la **última absorbe la diferencia**, así la suma es exactamente el importe depreciable. Nada se calcula con `float`. | Exactitud: el valor neto llega exactamente al residual |
| D-058 | **Corrida de depreciación por período:** `POST /depreciation/run {period_id}` genera **un borrador** con una línea de gasto y una de acumulada por categoría (por cuenta contable), con el detalle por bien en `accounting.depreciation_items`. La corrida **no contabiliza** sola: la contabiliza una persona (BR-ACC-06). Hay como máximo una corrida viva (`draft` o `posted`) por período: si se descarta, se puede volver a correr. Los meses no se saltean: no se corre un período si el anterior, con bienes depreciables, no tiene su corrida contabilizada. | Auditable mes a mes; nunca una depreciación duplicada |
| D-059 | **Baja de un bien** (venta, destrucción o donación): genera un borrador que da de baja el costo y la acumulada, e imputa la diferencia a la cuenta de resultado por venta de activos fijos (`17.01` del plan propuesto, configurable en `settings`). Si hubo venta, el cobro se carga como movimiento de finanzas por separado: la baja no inventa la contrapartida. Antes de la baja, la depreciación tiene que estar al día hasta el mes anterior. Un bien dado de baja no se deprecia más. | Partida doble completa y trazable |
| D-060 | **Centros de costos** (`accounting.cost_centers`): código, nombre y archivo, un solo nivel. Una línea puede llevar `cost_center_id` **solo si su cuenta es de ingreso o de gasto**: lo valida el trigger de líneas, no solo el servicio. Es opcional; con `settings.cost_centers_required = true` es obligatorio en las cuentas de resultado al contabilizar. Reporte: estado de resultados por centro, con una columna "sin centro". | Dimensión de gestión que no altera los saldos contables |
| D-061 | **Asientos recurrentes** (`accounting.recurring_templates`): descripción, líneas fijas (cuenta, debe o haber, centro), día del mes, fecha de inicio y de fin opcional, activa o pausada. `POST /recurring/generate {period_id}` crea los **borradores** del período que falten. La unicidad `(template_id, period_id)` impide duplicarlos: si un borrador se descarta, se puede regenerar. No hay un proceso en segundo plano: la app de escritorio lo ofrece al abrir y en el inicio ("hay 3 asientos recurrentes para generar en noviembre"). | Nada se contabiliza solo; sin tareas ocultas |
| D-062 | **Saldos iniciales en el balance de comprobación:** columnas `opening_debit` y `opening_credit`, con el acumulado de todo lo contabilizado antes de `from`. Las cuentas de resultado arrancan en cero si su ejercicio anterior está refundido. No se generan asientos de apertura (D-042). Si el contador pide un asiento formal de apertura en el libro diario, se agrega como `kind = 'opening'` y los reportes lo excluyen del acumulado para no contarlo dos veces. | Resuelve el pendiente del núcleo sin duplicar saldos |
| D-063 | **Libros exportables:** `GET /reports/{journal,ledger,trial-balance,balance-sheet,income-statement,depreciation-schedule}?format=xlsx` devuelve un XLSX (`openpyxl` en modo escritura, ya es dependencia) con: razón social, RUC, título, rango, fecha de emisión, aviso de plan sin validar si corresponde, importes como números con formato `#.##0` y totales. El **PDF** sale de la impresión de la interfaz (`window.print()` con una hoja de estilo de impresión: el WebView2 de Windows ofrece "Microsoft Print to PDF"), sin agregar una librería de PDF al backend. | Sin dependencias pesadas en el ejecutable; la rubricación sigue siendo un trámite del propietario |

## 2. Esquema (migración `0004_contabilidad_3b`, `down_revision = "0003"`)

Mismas convenciones que el núcleo: `uuidv7`, `TimestampMixin`, `organization_id` y FK compuestas `(x_id, organization_id)`.

- **`accounting.asset_categories`:**
  - `name`;
  - `useful_life_months` int NULL, CHECK `> 0`;
  - `asset_account_id`, `accumulated_account_id`, `expense_account_id`, NULL mientras la categoría no esté completa;
  - `source_url`, `legal_reference`, `validation_status`, `archived_at`.

  El servicio exige vida útil y las tres cuentas antes de usar la categoría. La cuenta de activo tiene que ser de activo; la acumulada, de activo con naturaleza acreedora (regularizadora); la de gasto, de gasto.
- **`accounting.fixed_assets`:**
  - `category_id`, `name`, `description`, `serial_or_reference`;
  - `acquired_on`, `depreciation_start` (primer día de un mes);
  - `cost` numeric(18,2) CHECK entero y `> 0`, `residual_value` CHECK entero, `>= 0` y `< cost`;
  - `useful_life_months`;
  - `acquisition_entry_id` NULL (asiento de compra, si existe), `source_transaction_id` NULL (movimiento de finanzas de la empresa, con las mismas FK que D-035);
  - `status` CHECK `active`/`disposed`, `disposed_on`, `disposal_kind` CHECK `sale`/`scrap`/`donation`, `disposal_entry_id`.
- **`accounting.depreciation_runs`:** `period_id`, `entry_id`. Índice único parcial `(period_id)` sobre las corridas cuyo asiento está vivo (garantizarlo con un trigger o una columna de estado sincronizada; documentarlo).
- **`accounting.depreciation_items`:** `run_id`, `asset_id`, `amount` (entero `> 0`). `UNIQUE (run_id, asset_id)`.
- **`accounting.cost_centers`:** `code` (`UNIQUE (organization_id, code)`), `name`, `archived_at`.
- **`accounting.journal_lines.cost_center_id`** NULL, FK compuesta. Ampliar el trigger de líneas: solo con cuentas `income` o `expense`, y no archivado.
- **`accounting.recurring_templates`** y **`recurring_template_lines`** (mismas columnas que las líneas, sin `entry_id`). **`recurring_generations`:** `template_id`, `period_id`, `entry_id`, unicidad parcial sobre generaciones vivas como en las corridas.
- **`journal_entries.kind`:** ampliar el CHECK con `depreciation`, `disposal` y `recurring`. Ampliar el trigger de reversión para que esos tres también se puedan revertir.
  - Revertir una corrida de depreciación la libera: se puede volver a correr.
  - Revertir una baja devuelve el bien a `active`. Lo hace el servicio en la misma transacción.
- **`settings`:** `asset_disposal_account_id` NULL, `cost_centers_required` bool DEFAULT false.

### 2.1 Cuadro de depreciación (reporte)
`GET /reports/depreciation-schedule?fiscal_year_id=`: por bien y agrupado por categoría, con costo, residual, vida útil, depreciación acumulada al inicio del ejercicio, depreciación del ejercicio (solo corridas contabilizadas), acumulada al cierre, valor neto contable, fecha de baja, y totales por categoría y generales. Si la investigación da las columnas del Anexo 6, acercarse a ellas, sin el revalúo.

## 3. Permisos
- **`accounting.manage`:** categorías, bienes, centros, plantillas; generar borradores de depreciación, bajas y recurrentes.
- **`accounting.post`:** contabilizar cualquiera de esos borradores, y validar categorías (D-056).
- Sin permisos nuevos.

## 4. API (`/api/v1/accounting`)

| Método | Ruta | Descripción |
|---|---|---|
| GET / POST / PATCH | `/asset-categories[/{id}]` | `POST /asset-categories/load-proposed` (409 si ya hay); `POST /asset-categories/{id}/validate` |
| GET / POST / PATCH | `/fixed-assets[/{id}]` | Filtros: categoría, estado, texto. El detalle trae el plan de cuotas (pasadas contabilizadas, pendientes calculadas) |
| POST | `/fixed-assets/{id}/dispose` | `{date, kind, reason}` → borrador de baja (D-059) |
| POST | `/depreciation/run` | `{period_id}` → borrador (D-058). 409 si hay corrida viva o falta la del mes anterior; 422 si alguna categoría está incompleta (decir cuál) |
| GET / POST / PATCH | `/cost-centers[/{id}]` | |
| GET / POST / PATCH | `/recurring[/{id}]` | Plantillas; `POST /recurring/generate {period_id}` devuelve los borradores creados y los que ya existían |
| GET | `/recurring/due?period_id=` | Qué falta generar (para el aviso de la interfaz) |
| GET | `/reports/income-statement?by_cost_center=true` | Columnas por centro |
| GET | `/reports/*?format=xlsx` | D-063 |

`/entries` acepta `cost_center_id` por línea, y `GET /reports/trial-balance` devuelve los saldos iniciales (D-062).

## 5. Pruebas mínimas (pytest, PostgreSQL real)
1. **Depreciación exacta:**
   - un bien de ₲ 10.000.000 con residual ₲ 1.000.000 a 36 meses suma exactamente ₲ 9.000.000 en sus 36 cuotas;
   - la última cuota absorbe la diferencia;
   - casos con división no exacta, vida de 1 mes y residual cero;
   - un cálculo de referencia en Python contra el servicio, sobre bienes variados.
2. **Corridas:** una sola viva por período; no se saltean meses; descartar o revertir libera la corrida; un bien dado de baja no se deprecia más; un bien con `depreciation_start` posterior al período no entra.
3. **Baja:** saldos del bien en cero después de contabilizar; resultado de la baja correcto con y sin depreciación completa; revertir la baja devuelve el bien a `active`.
4. **Categorías:**
   - la copia empaquetada es idéntica al YAML candidato;
   - una categoría incompleta no se usa (422);
   - cuentas de tipo incorrecto rechazadas;
   - `validation_status` no pasa a `validated` sin `accounting.post`.
5. **Centros:** por SQL directo, la base rechaza un centro en una línea de activo o pasivo; con `cost_centers_required`, no se contabiliza una línea de resultado sin centro; el estado de resultados por centro suma igual al total.
6. **Recurrentes:** generar dos veces no duplica; descartar y regenerar funciona; fin de vigencia y pausa respetados; un día 31 en meses cortos cae el último día del mes.
7. **Saldos iniciales:** el balance de comprobación de un rango posterior a otro trae los saldos iniciales correctos, y las cuentas de resultado arrancan en cero después de la refundición. Cálculo de referencia.
8. **XLSX:** cada reporte se abre con `openpyxl`, trae encabezado, aviso y totales iguales a los del JSON; los importes son numéricos, no texto.
9. **Migración:** `alembic check` limpio, y `downgrade 0003` → `upgrade head` con datos.
10. **Rendimiento** (`slow`): una corrida de depreciación con 2.000 bienes en menos de 1 s; el XLSX del diario con 20.000 líneas en menos de 3 s.
