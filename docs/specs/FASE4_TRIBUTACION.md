# Especificación: Fase 4, Tributación (núcleo)

**Estado:** aprobada por el jefe de proyecto (2026-11-24). Se apoya en las fases 2 y 3, que ya están implementadas.
- **Decisiones nuevas:** D-082 a D-095.
- **Reglas de negocio:** BR-TAX-01 (reformulada), BR-TAX-02 y BR-TAX-03, y las nuevas BR-TAX-04 a BR-TAX-12.
- **Fuentes:**
  - `docs/research/TRIBUTACION_PY.md` y `docs/research/tax_rules_candidatas.yaml`: 25 reglas, todas `pending`.
  - `docs/research/TRIBUTACION_FASE4.md`: formato del registro de comprobantes, Formulario 120, crédito fiscal y feriados. Ver §7.
- **Regla madre:** el sistema **no presenta nada**: ni declaraciones, ni el registro de comprobantes, ni pagos (prompt maestro, regla 15). Arma borradores, recordatorios y controles. La persona confirma y presenta en Marangatu.

## 0. Alcance

**Entra (fase 4):**
- **Perfil fiscal** de la empresa: régimen, obligaciones inscriptas y cierre del ejercicio. Lo declara el propietario y lo verifica el contador con la constancia de RUC.
- **Motor de reglas versionado**: las reglas candidatas cargadas como datos, verificables por el contador.
- **Feriados y excepciones de calendario**, para correr los vencimientos.
- **Obligaciones y calendario**: vencimientos por terminación del RUC, con estado (pendiente, presentada, pagada, no aplica) e importes calculado, declarado y pagado.
- **Registro de comprobantes** de compras y ventas: validaciones de timbrado, número, RUC y DV, imputación (IVA, IRE, IRP), duplicados y bloqueo del período confirmado.
- **Asiento propuesto desde un comprobante**: gasto o ingreso, IVA crédito o débito fiscal, y proveedor, cliente o banco.
- **Estimación mensual del IVA** y **borrador del Formulario 120**, para copiar a mano en Marangatu.
- **Avisos**: vencimientos próximos y vencidos, registro de comprobantes sin confirmar, y comprobantes del mes sin cargar.
- **Exportación** del registro a XLSX. Si existe un formato público verificado (§7), también al formato de importación de Marangatu.

**Queda fuera (fase 4B o posterior):**
- estimación del IRE (Formulario 500 o 501), anticipos, IDU y retenciones;
- prorrateo del crédito fiscal en operaciones mixtas: en esta fase solo se **avisa** (D-090);
- importar comprobantes electrónicos (XML o CDC) desde SIFEN o Marangatu, que es la fase 5;
- notificaciones del sistema operativo: en esta fase los avisos son dentro de la app;
- obligaciones laborales (IPS y MTESS), que son la fase 7.

## 1. Decisiones de modelo

| ID | Decisión | Motivo |
|---|---|---|
| D-082 | **Reglas `pending` utilizables con aviso (reformula BR-TAX-01).** Una regla `pending` **sí** alimenta el calendario, los avisos y las estimaciones. Todo resultado que dependa de ella lleva `rule_status: "pending"` y la interfaz lo muestra como «sin verificar por un contador», igual que el plan de cuentas (D-038). Nada se presenta nunca como oficial. Una regla `deprecated` no se usa. Una regla sin versión vigente para la fecha da «sin regla» y no genera nada. | Sin esto la app no avisaría ningún vencimiento hasta que el contador revise 25 reglas, y un aviso marcado «sin verificar» es menos riesgoso que ninguno. El prompt maestro pide **marcar** lo pendiente, no ocultarlo. |
| D-083 | **Perfil fiscal versionado** (`tax.profiles`): régimen del IRE (`ire_general`, `ire_simple` o `unknown`), mes de cierre del ejercicio (por defecto 12), si es contribuyente del IVA, y la lista de obligaciones inscriptas con su código DNIT y su fecha de alta (`tax.profile_obligations`). Cada versión tiene `valid_from`. El origen es `declared` (lo cargó el propietario) o `verified` (el contador lo comparó con la constancia de RUC: nombre, matrícula y referencia del documento). El RUC y el DV salen de `core.organizations` y son obligatorios para tener perfil. Sin perfil no hay obligaciones: la interfaz guía a cargarlo. | Prompt maestro: no asumir el régimen ni las obligaciones. Los períodos pasados conservan el perfil que regía entonces. |
| D-084 | **Reglas como datos** (`tax.rule_versions`): `code`, `version` (entero, único por código), descripción, `parameters` jsonb, `valid_from`, `valid_to`, `published_at`, `source_url`, `legal_reference`, `consulted_at`, `confidence`, `notes`, `validation_status` (`pending`, `verified` o `deprecated`), y `reviewed_by_name`, `reviewed_reference` y `reviewed_at`. Las reglas son **globales**, no de una organización: son normas del país. Se cargan con `POST /tax/rules/load-candidates` desde la copia empaquetada del YAML, que tiene que ser idéntica al de la investigación (con una prueba, como en D-037), y la carga es idempotente. La versión no se edita: lo que cambia es una versión nueva con `valid_from`. Solo cambia el estado: `pending → verified` y `cualquiera → deprecated`, este último con motivo. Lo restringe un trigger. Cada código que el sistema usa tiene un esquema Pydantic para sus `parameters`, y una versión que no lo cumple no se carga. | BR-TAX-02. Un cambio de ley es una versión nueva, nunca reescribir el pasado. |
| D-085 | **Códigos que usa esta fase:** `CAL-PERPETUO-DJ`, `CAL-PERPETUO-DJI`, `CAL-EXCEPCION-*` (excepciones fechadas), `IVA-GENERAL-TASAS`, `IVA-GENERAL-LIQUIDACION`, `REG-COMPROB-MENSUAL`, `IRE-GENERAL-DJ`, `IRE-SIMPLE-DJ` y `EEFF-PRESENTACION`. El resto se carga y se muestra, pero ningún cálculo lo usa todavía. | Alcance acotado y probado. |
| D-086 | **Días inhábiles:** sábados, domingos, los feriados de `tax.holidays` (fecha, nombre, fuente, `validation_status`, cargados desde `docs/research/feriados_py.yaml`, editables con auditoría) y las excepciones. Un vencimiento que cae en un día inhábil pasa al siguiente hábil (RG 38/2020, art. 3). **Las excepciones** (`tax.due_date_exceptions`: código de obligación o «todas las determinativas», período, terminaciones de RUC, fecha nueva, norma y URL) **reemplazan** la fecha calculada. Las carga el usuario o vienen del YAML (por ejemplo, la RG DNIT 60/2026). | La RG 38 corre los inhábiles, y las resoluciones puntuales no son la regla general (investigación §3.2). |
| D-087 | **Obligaciones** (`tax.obligations`): una fila por (organización, código, período). El período es el mes, o el ejercicio en las anuales. Se guardan el vencimiento calculado, la versión de la regla aplicada y la excepción aplicada si la hubo. `POST /tax/obligations/sync` crea las que falten desde el alta de cada obligación del perfil hasta 3 meses adelante, y se puede llamar las veces que haga falta. La app lo llama al abrir el calendario. Si cambian el perfil, una regla o una excepción, se **recalcula el vencimiento de las que no se presentaron**, nunca el de las presentadas. Si el perfil deja de tener una obligación, sus filas sin presentar pasan a `not_applicable` con motivo automático, y ninguna se borra. Estados: `pending → filed → paid`, `pending → not_applicable` (con motivo) y `filed → pending` (reabrir con motivo, si se presentó una rectificativa o hubo un error de carga). «Vencida» se deriva: `pending` y vencimiento < hoy. Al presentar se guardan fecha, número de constancia o talón e importe declarado. Al pagar se guardan fecha, importe pagado y, si se quiere, el movimiento de finanzas. | Prompt maestro, módulo 4: tipo, período, vencimiento, estado, importes calculado, declarado y pagado, respaldo y fuente. |
| D-088 | **Comprobantes** (`tax.vouchers`): `direction` (`purchase` o `sale`), tipo, si es electrónico, CDC (44 dígitos, solo electrónicos), timbrado (8 dígitos), número (`^\d{3}-\d{3}-\d{7}$`), fecha, contraparte (RUC y DV validados con el algoritmo módulo 11 de §7, o documento de identidad o «sin nombre» según el tipo), nombre, condición (contado o crédito), moneda y cotización (D-041), importes en PYG enteros (`taxed_10`, `taxed_5`, `exempt`, todos **con IVA incluido** como en la factura), y `vat_10`, `vat_5` e imputación (`imputes_vat`, `imputes_ire`, `imputes_irp`). El IVA se calcula con la regla `IVA-GENERAL-TASAS` (incluido: 10 % → importe/11; 5 % → importe/21, redondeo al guaraní más cercano, mitades hacia arriba). Se acepta el IVA impreso si difiere en ±1 guaraní, y lo que se guarda es lo impreso. Una nota de crédito o de débito referencia el comprobante original (`related_voucher_id`, misma contraparte) y resta o suma en su período. Para evitar duplicados hay un índice único sobre (organización, dirección, RUC de la contraparte, timbrado, número), sin contar los anulados. Puede vincularse a una contraparte de finanzas y a un movimiento del contexto de la empresa (FK compuestas; nunca a uno personal). | El registro es la base del IVA y de la RG 90. Los importes se cargan como figuran en la factura. |
| D-089 | **Período confirmado y bloqueo:** cuando la obligación `REG-COMPROB-MENSUAL` del mes pasa a `filed`, los comprobantes de ese mes **no se pueden crear, modificar ni anular**. Lo impone un trigger que mira la obligación. Para corregir se reabre la obligación (`filed → pending`, con motivo, auditado), igual que una rectificativa en Marangatu. | Lo confirmado en Marangatu tiene carácter de declaración jurada (RG 90, art. 15). |
| D-090 | **Estimación de IVA del mes** (`GET /tax/vat/{year}/{month}`), calculada en el momento: débito fiscal (ventas que imputan IVA), crédito fiscal (compras que imputan IVA), notas de crédito y de débito en su período, saldo a favor del mes anterior (el **declarado** en la obligación IVA presentada del mes anterior si existe, si no el estimado), y el resultado, a ingresar o saldo a favor. Muestra por separado cada tasa, la regla aplicada con su versión y estado, y el control contra los saldos de las cuentas de IVA del mayor para ese mes. Una diferencia es solo un aviso. Si en el mes hay ventas exentas y compras con crédito, avisa que puede corresponder **prorrateo** (pendiente del contador) y no lo calcula. El **borrador del Formulario 120** lleva esos valores a los rubros y casillas que documente la investigación (§7). Si un rubro no está verificado, se muestra con el nombre genérico y el aviso. La estimación se puede «llevar» a la obligación IVA del mes como `calculated_amount`. | Estimación ≠ declaración (BR-TAX-03). Sin prorrateo inventado. |
| D-091 | **Asiento desde un comprobante** (`POST /tax/vouchers/{id}/propose-entry`), como borrador:<br>• **compra**: debe a la cuenta elegida (gasto o activo) por la base, debe a IVA crédito fiscal 10 % o 5 % por el impuesto, y haber a proveedores (crédito) o al banco o caja del movimiento vinculado (contado);<br>• **venta**: lo simétrico, con IVA débito fiscal.<br>Las cuentas de IVA se configuran en `tax.settings` y por defecto apuntan a las del plan propuesto (`1.01.03.05.03.01` y `2.01.03.01.02.01`, `1.01.03.05.03.02` y `2.01.03.01.02.02` para el 5 %). **Nunca dos asientos vivos para el mismo hecho:** si el movimiento vinculado ya tiene asiento vivo, el comprobante no propone (409 `VOUCHER_TRANSACTION_HAS_ENTRY`), y si el comprobante tiene asiento vivo, proponer desde el movimiento da 409 `TRANSACTION_VOUCHER_HAS_ENTRY`. El asiento queda vinculado al comprobante y, si lo hay, al movimiento. Contabiliza una persona (BR-ACC-06). | Trazabilidad entre tributación y contabilidad (prompt maestro) sin duplicar. |
| D-092 | **Avisos** (`GET /tax/alerts`), calculados en el momento:<br>• obligaciones vencidas;<br>• obligaciones que vencen en los próximos 10 días;<br>• registro de comprobantes de un mes ya cerrado sin confirmar;<br>• meses con movimientos de la empresa (finanzas) pero sin comprobantes cargados;<br>• perfil sin verificar;<br>• reglas en uso sin verificar.<br>Se muestran en el Inicio y con una marca en el menú. No hay procesos en segundo plano. | Lo que pidió el propietario: «avisarme para cargar mis facturas». |
| D-093 | **Exportación:** `GET /tax/vouchers/export?year=&month=&direction=&format=xlsx` arma el libro de compras o ventas con las columnas de la RG 90 que documente la investigación. El formato de importación de Marangatu (`format=marangatu`) se implementa **solo si** `docs/research/formato_registro_comprobantes.yaml` existe con una fuente oficial o claramente identificada. Si no, no se inventa: queda fuera y la interfaz explica la carga manual. | La memoria no es fuente. |
| D-094 | **Permisos nuevos:** `tax.read` (ver todo lo tributario), `tax.manage` (perfil declarado, comprobantes, obligaciones, feriados, excepciones y configuración) y `tax.verify` (verificar reglas y el perfil, deprecar reglas). Propietario y Contador tienen los tres. Administrador tiene `read` y `manage`. Consulta, solo `read`. Verificar pide nombre y matrícula, como en el plan de cuentas. | Mismo criterio que D-043: la verificación es un acto profesional. |
| D-095 | **Todo se audita** con el registro existente (acción `tax.*` y antes/después): perfil, verificaciones, comprobantes, cambios de estado de obligaciones, feriados, excepciones y configuración. Los importes son siempre `Decimal` o string en la API, nunca `float`. | Igual que las fases anteriores. |

## 2. Esquema (migración `0005_tributacion`, `down_revision = "0004"`: verificar el id real)

Esquema `tax`, con las mismas convenciones que `accounting`: `uuidv7`, `TimestampMixin` y FK compuestas `(x_id, organization_id)`.

| Tabla | Clave y restricciones principales |
|---|---|
| `rule_versions` | global; `UNIQUE(code, version)`; exclusión (`btree_gist`) para que no haya dos versiones no `deprecated` del mismo código con vigencias que se pisen; `ck` de estado; si es `verified`, revisor, matrícula y fecha completos |
| `holidays` | global; `UNIQUE(day)`; nombre, fuente y estado |
| `due_date_exceptions` | global; obligación o grupo, período (`date` del primer día del mes), terminaciones (`smallint[]`, vacío = todas), fecha nueva, norma y URL |
| `profiles` | por organización; `UNIQUE(organization_id, valid_from)`; régimen, mes de cierre (1-12), `vat_taxpayer`, origen, y verificación completa si `verified` |
| `profile_obligations` | (profile_id, code) único; código DNIT (`211`, `955`, `700`, `701`, `948`…) y fecha de alta |
| `obligations` | `UNIQUE(organization_id, code, period_start)`; vencimiento, `rule_version_id`, `exception_id`, estado y sus campos (presentación, pago, motivo); importes `numeric(18,0)`; FK compuesta opcional a un movimiento de finanzas de la empresa |
| `vouchers` | lo de D-088; `UNIQUE` parcial anti duplicado; `ck` de formatos (timbrado, número, CDC, DV); `ck` de importes ≥ 0 y `vat_10`/`vat_5` consistentes; FK compuesta a contraparte y movimiento de la empresa, y a `accounting.journal_entries` |
| `settings` | por organización: cuentas de IVA crédito y débito, al 10 % y al 5 % (FK compuestas a cuentas imputables) y días de anticipación de los avisos (por defecto 10) |

**Triggers** (la base es la última defensa):
- `rule_versions_guard`: solo cambian el estado y los campos de revisión, y solo en las transiciones válidas. No se borran.
- `vouchers_period_lock`: no se insertan, actualizan ni anulan comprobantes de un mes cuyo `REG-COMPROB-MENSUAL` está `filed` (D-089).
- `obligations_guard`: transiciones válidas. Una obligación `filed` o `paid` no cambia su vencimiento ni su regla. No se borran.
- `vouchers_no_delete`: un comprobante se anula (`voided_at`, motivo), nunca se borra.

La bajada de la 0005 se niega si hay comprobantes u obligaciones presentadas (mismo criterio que D-080).

## 3. API (`/api/v1/tax`)

Lectura con `tax.read`; escritura con `tax.manage`, salvo donde dice `verify`. Errores con el formato existente (`code`, `message`, `details`).

| Método | Ruta | Notas |
|---|---|---|
| GET/POST | `/rules`, `/rules/load-candidates` | Listado con filtros (código, estado, vigente a una fecha). La carga es idempotente. |
| POST | `/rules/{id}/verify`, `/rules/{id}/deprecate` | `verify` pide nombre, matrícula y nota. `deprecate` pide motivo. |
| GET/POST/PATCH/DELETE | `/holidays`, `/holidays/load-candidates` | Un feriado puede borrarse solo si nunca corrió un vencimiento presentado (si no, 409). |
| GET/POST/PATCH | `/due-date-exceptions` | |
| GET/PUT | `/profile` | Perfil vigente e historial. `PUT` crea una versión nueva con `valid_from`. |
| POST | `/profile/{id}/verify` | `verify`: nombre, matrícula y referencia de la constancia de RUC. |
| POST/GET | `/obligations/sync`, `/obligations?from&to&status&code` | |
| POST | `/obligations/{id}/file`, `/pay`, `/not-applicable`, `/reopen` | Cada una con sus campos. `reopen` pide motivo. |
| GET/POST/PATCH | `/vouchers`, `/vouchers/{id}` | Cursor y filtros (mes, dirección, contraparte, texto, anulados). |
| POST | `/vouchers/{id}/void`, `/vouchers/{id}/propose-entry` | |
| GET | `/vouchers/export` | `format=xlsx` (y `marangatu` solo si se cumple D-093). |
| GET | `/vat/{year}/{month}` | Estimación y borrador del Formulario 120. `?format=xlsx` también. |
| POST | `/vat/{year}/{month}/apply` | Lleva el estimado a `calculated_amount` de la obligación IVA. |
| GET | `/alerts` | |
| GET/PUT | `/settings` | |

Cada respuesta que depende de reglas incluye `rules_applied: [{code, version, validation_status, legal_reference}]` (BR-TAX-02).

## 4. Reglas de negocio (agregar a `docs/BUSINESS_RULES.md`)

- **BR-TAX-01 (reformulada):** Toda obligación, vencimiento o estimación indica la regla aplicada. Si la regla no está `verified`, se muestra como «sin verificar» y nunca como oficial (D-082).
- **BR-TAX-04:** Sin perfil fiscal no se generan obligaciones (D-083).
- **BR-TAX-05:** Un vencimiento en día inhábil pasa al siguiente hábil, y las excepciones fechadas reemplazan la fecha (D-086).
- **BR-TAX-06:** Las obligaciones presentadas no cambian de vencimiento ni de regla, y ninguna se borra (D-087).
- **BR-TAX-07:** No hay comprobantes duplicados: misma dirección, RUC, timbrado y número (D-088).
- **BR-TAX-08:** Los comprobantes de un mes con el registro confirmado no se tocan sin reabrirlo (D-089).
- **BR-TAX-09:** El IVA se calcula con la regla de tasas vigente a la fecha del comprobante. Se acepta el impreso con ±1 ₲ (D-088).
- **BR-TAX-10:** Nunca dos asientos vivos para el mismo hecho, ni desde el comprobante ni desde el movimiento (D-091).
- **BR-TAX-11:** El prorrateo no se calcula: se avisa (D-090).
- **BR-TAX-12:** Solo `tax.verify` verifica reglas y perfiles, con nombre y matrícula (D-094).

## 5. Pruebas mínimas (pytest contra PostgreSQL real)

1. **Reglas:**
   - la carga de candidatas es idempotente y la copia empaquetada es idéntica al YAML;
   - un `parameters` inválido no se carga;
   - el trigger impide editar una versión y las transiciones inválidas;
   - no se pisan vigencias;
   - la regla vigente a una fecha.
2. **Calendario:**
   - las 10 terminaciones de RUC para DJ y DJI;
   - un vencimiento en sábado, en domingo y en un feriado pasa al siguiente hábil, también cuando hay varios inhábiles seguidos;
   - la excepción RG 60/2026 reemplaza la fecha solo de las terminaciones y obligaciones que nombra;
   - cierre de ejercicio distinto de diciembre para las anuales;
   - cálculo de referencia en Python para un año entero.
3. **Obligaciones:**
   - `sync` es idempotente y concurrente: dos pedidos a la vez no duplican (conexiones reales);
   - un cambio de perfil o de regla recalcula solo lo no presentado;
   - una obligación que el perfil quita pasa a `not_applicable`;
   - las transiciones válidas e inválidas (también por SQL directo contra el trigger);
   - «vencida» derivada.
4. **Perfil:**
   - versiones por `valid_from`;
   - la verificación exige matrícula;
   - no hay perfil sin RUC en la organización.
5. **Comprobantes:**
   - formatos (timbrado, número, CDC, DV módulo 11, con casos reales de la investigación);
   - IVA incluido por tasa con redondeo, y ±1 aceptado, ±2 rechazado;
   - duplicado (también entre dos pedidos concurrentes);
   - nota de crédito con su original;
   - moneda extranjera con cotización;
   - FK compuesta: un movimiento personal da error;
   - anulación sin borrar.
6. **Bloqueo:** el registro confirmado impide crear, editar y anular en el mes, también por SQL directo; reabrir lo permite y queda auditado.
7. **IVA:**
   - estimación con 10 %, 5 %, exentas, notas de crédito y saldo a favor del mes anterior (declarado contra estimado);
   - el aviso de prorrateo;
   - el control con el mayor (que cuadra y que no cuadra);
   - `apply`;
   - el XLSX se abre y sus totales coinciden.
8. **Asiento desde un comprobante:** compra al contado y a crédito, venta, y 5 % y 10 % en el mismo comprobante (el asiento balancea exacto); las dos direcciones del 409 de D-091; los vínculos.
9. **Avisos:** cada tipo aparece y desaparece cuando se resuelve; respeta los días de anticipación.
10. **Permisos y privacidad:**
    - viewer solo lee;
    - el Administrador no verifica;
    - ningún endpoint expone datos del contexto personal;
    - todo cambio deja auditoría.
11. **Migración:** `upgrade`/`downgrade` con datos; `alembic check` limpio; la bajada se niega con comprobantes.
12. **Rendimiento (`slow`):** con 20.000 comprobantes en un año, la estimación de IVA de un mes tarda menos de 300 ms y el XLSX del año menos de 3 s.

Comprobar que la prueba de cada trigger falla si se quita el trigger.

## 6. Interfaz (frontend, después del backend)

Menú **Impuestos**:
- **Resumen** con los avisos (D-092) y los próximos vencimientos.
- **Calendario** en vista de lista por mes. Cada obligación muestra su estado y sus acciones (presentada, pagada, no aplica, reabrir), y la regla y la norma a un clic.
- **Comprobantes**: alta rápida pensada para cargar facturas en serie. Teclado, autocompletado de la contraparte por RUC (de finanzas), IVA calculado mientras se escribe, aviso de duplicado antes de guardar, y «Proponer asiento».
- **IVA del mes** con el borrador del Formulario 120, «Imprimir / PDF» y «Descargar Excel».
- **Perfil fiscal**: un asistente que explica cada dato y dónde está en la constancia de RUC.
- **Reglas y feriados**: lectura y verificación.

Todas las pantallas muestran el estado «sin verificar» que corresponda. La marca de avisos en el menú y el bloque en el Inicio usan `/tax/alerts`. E2E en `frontend/e2e/tributacion.spec.ts`.

## 7. Datos que aporta la investigación de la fase 4

`docs/research/TRIBUTACION_FASE4.md` (en curso al aprobar esta especificación). Lo que encuentre ajusta, sin cambiar las decisiones:
- el formato de importación de Marangatu (D-093);
- los rubros y casillas del Formulario 120 (D-090);
- los requisitos del crédito fiscal (validaciones de D-088 y avisos);
- los tipos de comprobante y el algoritmo del DV (D-088);
- los feriados (`docs/research/feriados_py.yaml`, D-086).

Si algo contradice una decisión, manda la decisión más conservadora y se anota en `DECISIONS.md`.
