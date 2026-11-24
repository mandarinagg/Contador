# Plan de cuentas: ¿hay uno oficial en Paraguay?

> **Estado: propuesta para que la valide el contador. No está aprobada.**
> Fecha de consulta de las fuentes: **2026-11-24**. Preparado por un asistente de IA.

## 1. Respuesta corta

- **No encontré un plan de cuentas oficial y obligatorio** para empresas privadas (no financieras) en Paraguay.
- Lo que sí existe es un **modelo oficial de estados financieros con códigos** (RG N° 49/2014 de la ex SET, hoy DNIT). Quien liquida el IRE General debe presentar sus estados financieros con esos códigos.
- Conviene que el plan de cuentas **use esos mismos códigos** en sus primeros niveles. Así el balance para la DNIT sale directo del sistema.

## 2. Qué dicen las fuentes

### 2.1 RG N° 49/2014: modelo de estados financieros

- **Norma:** Resolución General N° 49/2014, 19-12-2014. Su título: «Por la cual se dispone el nuevo modelo de los Estados Financieros y del cuadro de revalúo y depreciación de los bienes del activo fijo».
  - Texto: <https://www.dnit.gov.py/documents/20123/209894/Resoluci%C3%B3n+General+N%C2%B0+49_14.pdf/dfbb9772-68b6-dcff-2312-3990e0ca1728?t=1684192313142.pdf>
  - Anexos (XLS, última modificación del archivo en 2016): <https://www.dnit.gov.py/documents/20123/209894/Resoluci%C3%B3n+General+N%C2%B0+49_14+Anexos.xls/1be53adb-b8a2-37d3-2561-7d2b93810387?t=1684192313142>
- **Confianza:** oficial leída. El PDF es un escaneo de 3 páginas, leído como imagen. Los anexos se leyeron completos.
- **Anexos:**
  1. Balance General
  2. Estado de Resultados
  3. Estado de Flujo de Efectivo
  4. Estado de Cambios del Patrimonio Neto
  5. Notas
  6. Cuadro de Revalúo y Depreciación
- **Art. 3** (cita textual): «En la preparación y emisión de los Estados Financieros, los contribuyentes y demás obligados deberán utilizar los códigos establecidos en los modelos anexos a esta Resolución, pudiendo incorporar adicionalmente en el Balance General y en el Estado de Resultados, las cuentas o subcuentas que consideren necesarias, de acuerdo a las actividades que desarrollen. Los códigos asignados a una determinada cuenta o subcuenta hasta el quinto nivel, no podrán ser modificados en ejercicios posteriores.»
- **Art. 5:** los rubros, partidas o cuentas que alcancen o superen el 10% del total del activo, pasivo, patrimonio, ingresos o gastos se muestran por separado en el balance o en las notas.
- **Partes de la RG 49/2014 que ya no rigen tal cual:**
  - Habla de IRACIS/IRAGRO, la presentación por Hechauka y el Formulario 158.
  - Hoy la presentación sigue la **RG N° 38/2020, art. 8** (obligación 948).
  - El modelo de la RG 49/2014 se sigue usando por remisión de la **RG N° 77/2020**: <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-77-20>.

### 2.2 Notas a los estados financieros: RG DNIT N° 49/2026

- **Fecha:** 24-03-2026.
- **Fuente:** <https://www.dnit.gov.py/web/portal-institucional/w/resoluci%C3%B3n-general-dnit-n%C2%B0-49/26>
- Exige detallar en las notas:
  - utilidades
  - reservas legales, facultativas y estatutarias
  - distribución y capitalización de utilidades.
- Rige para los estados financieros cerrados desde el 31-12-2025.
- **Para el plan de cuentas:** las reservas y los movimientos de resultados acumulados deben poder distinguirse.

### 2.3 Ley de la EAS y reglamento del IRE

- **Ley 6480/2020, art. 32:** los estados financieros se preparan «de acuerdo a las normas vigentes y los principios de contabilidad generalmente aceptados».
  - Fuente: <https://eas.mic.gov.py/files/LEY-EAS-6480-2020-1-.pdf>
- **Ley 6480/2020, art. 31:** obliga a llevar libro diario y libro de inventario, entre otros.
- **Decreto 3182/2019, art. 64:**
  - Fuente: <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3182-19.pdf/ee6adbdb-f9c2-7a3f-877d-96a0bbbc0a3d?t=1681424260226.pdf>
  - Exige los libros diario, inventario y mayor según la Ley 1034/83 «Del Comerciante».
  - Un atraso de más de 90 días corridos es infracción tributaria.
- **Ninguna de estas normas** impone un plan de cuentas.

### 2.4 Normas contables profesionales

- El Consejo de Contadores Públicos del Paraguay emite **Normas de Información Financiera (NIF)**. Ejemplo: la NIF 23 sobre diferencias de cambio, obligatoria para los períodos desde el 01-01-2026 según EY.
- Solo lo encontré en fuentes **secundarias**:
  - <https://www.ey.com/es_py/insights/financial-services/esta-su-empresa-preparada-para-la-nif-23>
  - <https://infonegocios.com.py/y-ademas/vigencia-y-adopcion-de-la-nif23-en-los-estados-financieros-de-las-empresas-locales>
- No leí el texto oficial de ninguna NIF. No encontré que el Consejo publique un plan de cuentas modelo.

## 3. Propuesta

- **Archivo:** `plan_de_cuentas_propuesto.yaml`.
- **Tamaño:** 173 cuentas en total (159 en la versión del núcleo; 14 más desde la fase 3B, ver §3.4).
  - 122 son imputables, es decir que reciben asientos.
  - 142 tienen código y nombre idénticos al modelo de la RG 49/2014. Lo verifiqué contra el XLS oficial.
  - 31 se agregaron como propuesta y están marcadas con `origen: propuesta`.

### 3.1 Criterios

1. **Respetar los códigos de la RG 49/2014.** Las cuentas del modelo conservan su código y nombre exactos.
   - Las subcuentas propias se agregan **debajo** de un código del modelo, nunca reutilizando uno.
   - Ejemplos: `1.01.01.04.01` para un banco concreto, o `2.01.03.01.02.01` para el IVA débito 10%.
2. **Sacar lo que no aplica.** Se omitieron rubros de agro, ganadería, forestal, exportación, zona franca, maquila y turismo de compras. Si alguno aplica, se agrega con el código del modelo.
3. **Separar el IVA por tasa** (10% y 5%), tanto en débito como en crédito. Facilita la DJ del Formulario 120 y el registro de comprobantes.
4. **Separar lo del accionista:**
   - Préstamos **a** él: `1.01.03.04`.
   - Préstamos **de** él: `2.01.02.02`.
   - El art. 40 de la Ley 6380 presume distribución de utilidades, y por tanto IDU, en ciertos préstamos o retiros del dueño. La cuenta del accionista debe estar visible y no mezclarse con gastos.
5. **Las cuentas regularizadoras tienen naturaleza inversa:**
   - previsiones
   - depreciación y amortización acumuladas
   - capital a integrar
   - descuentos y devoluciones.
6. **Los subtotales del Estado de Resultados** (códigos 6, 9, 12, 16, 18 y 20) **no son cuentas** y no se incluyen. La aplicación los calcula.
7. **El campo `tipo` admite cinco valores.** Los costos (grupo 5) van como `gasto`.
   - En el grupo 14 (previsiones), la desafectación (`14.01`) es `ingreso` y la constitución (`14.02`) es `gasto`.
   - La diferencia de cambio aparece dos veces, como en el modelo: ganancia en `8.05` y pérdida en `13.04`.
8. **Activo fijo por clase de bien (fase 3B).** El terreno, que no se deprecia, va separado de las construcciones; cada clase de bien con vida útil propia tiene su cuenta de activo y su subcuenta de depreciación acumulada bajo `1.02.04.99`, para que el saldo por clase cuadre con el cuadro de depreciación (RG 77/2020). Las cuentas nuevas sin código del modelo van en los códigos libres `1.02.04.xx` que el XLS reserva para «nuevas cuentas a incluir».

### 3.2 Estructura resumida

| Grupo | Nombre (RG 49/2014) | Tipo | Naturaleza |
|---|---|---|---|
| 1 | ACTIVO | activo | deudora |
| 2 | PASIVO | pasivo | acreedora |
| 3 | PATRIMONIO NETO | patrimonio | acreedora |
| 4 | INGRESOS OPERATIVOS | ingreso | acreedora |
| 5 | COSTOS OPERATIVOS | gasto | deudora |
| 8 | OTROS INGRESOS | ingreso | acreedora |
| 10 | GASTOS DE VENTAS O COMERCIALIZACIÓN | gasto | deudora |
| 11 | GASTOS DE ADMINISTRACIÓN | gasto | deudora |
| 13 | GASTOS BANCARIOS Y FINANCIEROS | gasto | deudora |
| 14 | PREVISIONES | mixto (14.01 ingreso / 14.02 gasto) | según cuenta |
| 15 | DEPRECIACIONES Y AMORTIZACIONES | gasto | deudora |
| 17 | OTROS RESULTADOS NO OPERATIVOS | ingreso | acreedora (puede tener saldo de cualquier signo) |
| 19 | IMPUESTO A LA RENTA | gasto | deudora |

### 3.3 Cuentas agregadas como propuesta

| Código | Nombre | Motivo |
|---|---|---|
| 1.01.01.04.01 a .03 | Bancos por cuenta y moneda | Conciliación bancaria |
| 1.01.03.05.03.01 / .02 | IVA crédito fiscal 10% / 5% | DJ del IVA por tasa |
| 1.01.03.05.05 | Saldo a favor de IVA (ejercicios anteriores) | Arrastre de crédito fiscal |
| 1.02.04.05.01 | Equipos de informática | Uso habitual |
| 1.02.07.03 | Software | Intangible habitual |
| 2.01.03.01.02.01 / .02 | IVA débito fiscal 10% / 5% | DJ del IVA por tasa |
| 2.01.03.01.03.01 | Retención IDU a ingresar | Obligación 726 |
| 2.01.03.01.03.02 | Retenciones de IVA y renta a ingresar | Solo si es designada agente |
| 2.01.03.02.01 a .03 | Sueldos, aportes IPS y aguinaldo a pagar | Solo con empleados |
| 4.01.01.01 / .02 | Ventas gravadas IVA 10% / 5% | DJ del IVA por tasa |
| 11.19 | Suscripciones de software y servicios digitales | Gasto habitual |
| 1.02.04.01.01 / .02 | Terrenos / Construcciones y mejoras | El terreno no se deprecia (fase 3B) |
| 1.02.04.09 | Envases retornables | Categoría del art. 31 (Decreto 6105/2021); código libre |
| 1.02.04.10 | Otros bienes de propiedad, planta y equipo | Categoría residual del art. 31; código libre |
| 1.02.04.99.01 a .10 | (-) Depreciación acumulada por clase de bien | Una regularizadora por cuenta de activo (salvo el terreno) |

### 3.4 Retoques de la fase 3B (2026-11-24)

Pedidos por `docs/specs/FASE3B_CONTABILIDAD.md` §6, a partir de `docs/research/DEPRECIACION_PY.md` §8. Las organizaciones que ya cargaron el plan no se tocan: el plan se carga una sola vez.

- **`1.02.04.04 MAQUINARIAS`: agregada con `origen: rg49_2014`.** Verificado el 2026-11-24 contra el XLS oficial de anexos (URL de §2.1, archivo de 128.000 bytes guardado por última vez el 26-04-2016): la hoja `1_Balance General` trae, en la fila 112, «1.02.04.04 | MAQUINARIAS», entre «1.02.04.03 MUEBLES, ÚTILES Y ENSERES» y «1.02.04.05 EQUIPOS». El XLS también lista `1.02.04.07 BIENES FUERA DE OPERACIÓN`, `1.02.04.97 BIENES INCORPORADOS AL AMPARO DE LA LEY N° 60/90` y `1.02.04.98 BIENES EN ARRENDAMIENTO FINANCIERO`, que siguen omitidas (no aplican a esta EAS), y la fila `1.02.04.xx (nuevas cuentas a incluir)`.
- **`1.02.04.01 INMUEBLES` pasa a agrupadora** con `1.02.04.01.01 TERRENOS` y `1.02.04.01.02 CONSTRUCCIONES Y MEJORAS` (propuesta).
- **`1.02.04.99 (-) DEPRECIACIÓN ACUMULADA` pasa a agrupadora** con una subcuenta por clase de bien: `.01` construcciones y mejoras, `.02` rodados, `.03` muebles, útiles y enseres, `.04` maquinarias, `.05` equipos, `.06` herramientas, `.08` mejoras en predio ajeno, `.09` envases retornables y `.10` otros bienes. El sufijo repite el de la cuenta de activo.
- **`1.02.04.09 ENVASES RETORNABLES` y `1.02.04.10 OTROS BIENES DE PROPIEDAD, PLANTA Y EQUIPO`** (propuesta) para las dos categorías candidatas que no tenían cuenta.
- Las categorías candidatas (`categorias_activo_fijo_candidatas.yaml`) apuntan ahora a estas cuentas: ninguna queda sin cuenta de activo, y solo `terrenos` queda sin cuenta de depreciación acumulada (no se deprecia).

## 4. Preguntas para el contador sobre el plan

1. ¿Acepta tomar la **RG 49/2014** como columna vertebral del plan? ¿O prefiere otra estructura con un mapeo a esos códigos para el balance?
2. **Actividad real de la EAS:** ¿vende bienes, servicios o ambos? Eso define si hacen falta inventarios y costo de mercaderías, o solo costo de servicios.
3. **Reserva legal:** ¿es obligatoria para la EAS, por aplicación supletoria de las normas de sociedades anónimas (Ley 6480, art. 42)? ¿Con qué porcentaje? No lo investigué.
4. **Moneda extranjera:** ¿habrá cuentas en dólares? Si las hay, aplica la NIF 23 y se necesita registrar la diferencia de cambio.
5. **Depreciación:** las vidas útiles y los valores residuales fiscales están investigados en `DEPRECIACION_PY.md` (Decreto 3182, art. 31) y el cuadro vigente es el Anexo de la RG 77/2020, no el Anexo 6 de la RG 49/2014. Falta que el contador valide las 34 categorías y las subcuentas por clase de bien de §3.4.
6. **Gastos de constitución de la EAS:** ¿se activan en `1.02.06.01` y se amortizan, o van a gastos del ejercicio?
