# Depreciación del activo fijo para el IRE (Paraguay)

> **Estado: propuesta para que la valide el contador. Nada está verificado; todo queda `pending`.**
> Fecha de consulta de las fuentes: **2026-11-24**. Preparado por un asistente de IA. No es asesoramiento tributario.
>
> Niveles de confianza: `oficial leída` (leí el texto en una fuente oficial), `oficial vista solo por título`, `secundaria` (tercero, solo como pista).
> Archivo hermano: [`categorias_activo_fijo_candidatas.yaml`](categorias_activo_fijo_candidatas.yaml) (34 categorías con vida útil, valor residual y cuentas del plan propuesto).

## 1. Respuesta corta

- **Vidas útiles y valor residual por tipo de bien: sí hay tabla oficial.** Está en el Decreto 3182/2019 (reglamento del IRE), Anexo, **art. 31**, hoy con la redacción del **Decreto 6105/2021** (14-10-2021). Ejemplos: equipos de informática 2 años (residual 10%); muebles y equipos en general 5 años (10%); vehículos automotores 5 años (20%); maquinarias 10 años (20%); construcciones 30 años (20%); intangibles pagados 5 años.
- **Valor residual:** es **obligatorio** determinarlo (Ley 6380, art. 11) y no puede superar el **20% del costo**. La tabla lo fija por categoría (0%, 10% o 20%). La cuota se calcula sobre el valor **menos** el residual.
- **Método:** ninguna norma del IRE que leí dice «línea recta» con esas palabras. La Ley habla de «distribución sistemática» y el modelo oficial del cuadro (RG 77/2020) divide el valor depreciable entre los años de vida útil restantes, lo que equivale a **línea recta anual**. Es una inferencia: ver D-DEP-1.
- **Desde cuándo:** a **opción del contribuyente, por cada bien**, desde el **mes siguiente** o desde el **ejercicio siguiente** a la incorporación (Decreto 3182, art. 30). No es obligatorio depreciar desde el mes de alta. Esto condiciona el diseño.
- **Bienes de bajo valor:** **no encontré ningún tope** para imputar directo al gasto. La Ley define activo fijo como el bien tangible que se espera usar **más de un ejercicio fiscal**. Ver D-DEP-3.
- **Venta o baja:** el resultado de vender un activo fijo es **precio de venta − costo + depreciaciones admitidas fiscalmente**, y es renta bruta (Ley 6380, art. 8). La baja por descomposición u obsolescencia exige acta del contador o constancia del auditor externo (Decreto 3182, art. 58, texto del Decreto 6105/2021).
- **Revalúo:** el revalúo anual con coeficientes de la DNIT **ya no existe como práctica anual** (era del IRACIS). En el IRE solo hay un **revalúo obligatorio que debe disponer el Poder Ejecutivo** cuando el IPC acumulado llegue al 20% desde el último ajuste (Ley 6380, art. 11). **No encontré ningún decreto que lo haya dispuesto.** El cuadro oficial lo trae como columna «Coeficiente de Revalúo», que se llena **solo si el Poder Ejecutivo lo establece**.
- **Cuadro de depreciación:** el modelo vigente es el **Anexo de la RG 77/2020** (22 columnas, valores fiscales y contables en paralelo). Sustituye al «Cuadro de Revalúo y Depreciación» del Anexo 6 de la RG 49/2014 (17 columnas), que ya había sido sustituido por la RG 94/2016. Ver §5.
- **IRE SIMPLE (ver §7):** no hay depreciación. La Ley 6380, art. 26, deja **deducir en el momento de la compra** los muebles, equipos y la construcción o refacción del establecimiento. **RESIMPLE** es una cuota fija y no admite deducciones; además es solo para empresas unipersonales, no para una EAS.
- **Lo que cambia el diseño:** ver §8. Lo principal: el inicio de la depreciación es una opción por bien; hay que llevar depreciación **fiscal y contable en paralelo**; la vida útil se fija por la norma vigente **a la fecha de adquisición**; y el cuadro anual necesita guardar el valor neto de cada bien en cada cierre.

---

## 2. Vidas útiles y valor residual (pregunta 1)

### 2.1 Qué norma rige

| Norma | Fecha | Qué hace | URL | Confianza |
|---|---|---|---|---|
| Ley N° 6380/2019, art. 11 | 25-09-2019 (fecha de la ley según los VISTOS de la RG 77/2020) | Define activo fijo, hace obligatorios el valor residual y la depreciación, y manda al reglamento a fijar vidas útiles y residual (máximo 20%) | <https://www.dnit.gov.py/web/portal-institucional/w/ley-n-6380-19> | oficial leída (copia en la web de la DNIT; no leí la versión de bacn.gov.py) |
| Decreto N° 3182/2019, Anexo, arts. 23, 24, 25, 30, 31, 32, 33, 36, 40, 67, 104 | 30-12-2019 (el mes es ilegible en el escaneo; los metadatos del PDF dicen 30-12-2019). Rige desde el 01-01-2020 (art. 8 del decreto) | Reglamento del IRE | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3182-19.pdf/ee6adbdb-f9c2-7a3f-877d-96a0bbbc0a3d?t=1681424260226.pdf> (55 págs., escaneo con capa de texto; las cifras las comprobé mirando las imágenes de las págs. 23 a 25) | oficial leída |
| Decreto N° 6105/2021, art. 1° | 14-10-2021 (fecha leída en la imagen de la pág. 1) | Da nueva redacción a los arts. 5, 28, **31** y **58** del Anexo del Decreto 3182 | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+6105-2021.pdf/d46a54b7-ab0d-e762-8a98-204d2a921ce9?t=1681415771708.pdf> (15 págs.) | oficial leída |

- **Cita, Ley 6380, art. 11:** «La reglamentación establecerá las estimaciones de vida útil para cada tipo o clase de bien depreciable […] así como también establecerá el valor residual para cada tipo o clase de activo fijo depreciable, el cual no podrá ser superior al 20% (veinte por ciento) de su valor de costo.»
- **Cita, Ley 6380, art. 11:** «Será obligatorio a los efectos del presente impuesto, la determinación del valor residual de los bienes del activo fijo, así como la depreciación de éstos.»
- **Cita, Ley 6380, art. 11 (qué es activo fijo):** «los bienes tangibles de propiedad, planta y equipo que sean propiedad del contribuyente, para ser usados en la producción o abastecimiento de bienes o servicios, para rentar a terceros o para propósitos administrativos y sobre los cuales se espera sean usados durante más de un ejercicio fiscal; con excepción de los bienes destinados a inversión o para la venta.»
- **Cita, Ley 6380, art. 15 num. 15:** son gastos deducibles «Las depreciaciones por desgaste, obsolescencia y agotamiento.»
- **Cita, Decreto 3182, art. 30:** «Para la determinación de los años de vida útil y la consecuente determinación de la cuota de depreciación, serán aplicables las disposiciones vigentes al momento de la adquisición de los activos respectivos.»

### 2.2 Tabla del art. 31 (bienes que puede tener una EAS)

Cita de encabezado (Decreto 3182, art. 31, igual en el Decreto 6105): «La cuota de depreciación por desgaste, deterioro u obsolescencia se aplicará sobre el valor del activo fijo, incluido el biológico, de acuerdo con los años de vida útil menos el porcentaje de valor residual, que se señalan más abajo, por cada tipo de bien.»

Todas las filas: confianza **oficial leída**, redacción del Decreto 6105/2021 (pág. indicada del PDF de 15 págs.), `pending`.

| Tipo de bien (art. 31) | Años | Residual | Cuenta del plan propuesto (activo) | Cita corta |
|---|---|---|---|---|
| a) i) Muebles y equipos en general | 5 | 10% | 1.02.04.03 | «Muebles y equipos en general, excluidos los comprendidos en el enunciado siguiente: 5 años. Valor Residual: 10%.» |
| a) ii) Muebles y enseres en viviendas del personal | 2 | 10% | 1.02.04.03 | «…2 años. Valor Residual: 10%.» |
| a) iii) Útiles de trabajo rural para el personal | 2 | 10% | 1.02.04.03 | idem |
| a) iv) Útiles y enseres en general | 2 | 10% | 1.02.04.03 | «Útiles y enseres en general: 2 años. Valor Residual: 10%.» |
| a) v) Envases retornables (nuevo en 2021) | 3 | 10% | sin cuenta | «Envases retornables: 3 años. Valor Residual: 10%.» |
| b) i) Maquinarias e implementos | 10 | 20% | sin cuenta en el plan propuesto (el modelo RG 49/2014 tiene 1.02.04.04) | «Maquinarias e implementos: 10 años. Valor Residual: 20%.» |
| b) ii) Herramientas y equipos | 5 | 10% | 1.02.04.06 | «Herramientas y equipos: 5 años. Valor Residual: 10%.» |
| **b) iii) Equipos de informática** | **2** | **10%** | 1.02.04.05.01 | «Equipos de informática: 2 años. Valor Residual: 10%.» |
| c) i) Vehículos automotores (los no listados abajo) | 5 | 20% | 1.02.04.02 | «Vehículos automotores, excluidos los comprendidos en los enunciados siguientes: 5 años. Valor Residual: 20%.» |
| c) ii) Motocicletas, motonetas, cuatriciclos, triciclos, bicicletas | 2 | 10% | 1.02.04.02 | idem |
| c) iii) Transporte público de pasajeros y vehículos utilitarios | 10 | 20% | 1.02.04.02 | «…vehículos utilitarios: 10 años. Valor Residual: 20%.» |
| c) iv) Restantes bienes de transporte terrestre | 5 | 20% | 1.02.04.02 | idem |
| d), e), f) Aeronaves, embarcaciones, ferroviario | 2 a 20 | 10% a 20% | 1.02.04.02 | Improbables en esta EAS. Están completas en el YAML. |
| g) i) Construcciones y mejoras de inmuebles, sin terreno | 30 | 20% | 1.02.04.01 | «…excluido el terreno y los comprendidos en los enunciados siguientes: Vida útil 30 años. Valor Residual: 20%.» |
| g) ii) Silos, almacenes y galpones | 20 | 20% | 1.02.04.01 | |
| g) iii) a v) Tanques de agua, canales, alambrados | 5 / 15 / 10 | 10% / 20% / 20% | 1.02.04.01 | Rurales. |
| **g) vi) Construcciones en propiedad de terceros** | **20** | **0%** | 1.02.04.08 | «…Vida útil 20 años, salvo que el contrato establezca un plazo menor. Valor Residual: 0%.» |
| **g) vii) Mejoras en propiedad de terceros** | **10** | **0%** | 1.02.04.08 | «…Vida útil 10 años, salvo que el contrato establezca un plazo menor. Valor Residual: 0%.» |
| g) viii) Instalaciones de electrificación | 10 | 10% | 1.02.04.01 | |
| g) ix) Caminos internos | 15 | 20% | 1.02.04.01 | |
| g) x) Instalaciones eléctricas, prevención de incendios, mamparas, incorporadas a construcciones | 10 | 20% | 1.02.04.01 | |
| g) xi) Restantes bienes no contemplados | 5 | 20% | sin cuenta | «Los restantes bienes no contemplados en los incisos precedentes. Vida útil 5 años. Valor residual: 20%.» |
| 2) Intangibles pagados | 5 | no fija | 1.02.07.01 / 1.02.07.03 | «Los bienes intangibles efectivamente pagados, tales como marcas, patentes, licencias y otros, se amortizarán en cinco (5) años.» |

Cuenta de depreciación acumulada: 1.02.04.99 para PPE, 1.02.07.99 para intangibles. Cuenta de gasto: 15.01 (depreciaciones) y 15.02 (amortizaciones).

- **Activos biológicos** (ganado y plantaciones, art. 31 num. 1 del grupo «Activos Biológicos»): leídos, no incluidos en el YAML. Todos 4 años y 20% (ganado) o 5-10 años y 0% (plantaciones).
- **Gastos de constitución y organización:** Ley 6380, art. 15 num. 9: «podrán ser amortizados en un período de hasta cinco años a opción del contribuyente.» Está en el YAML (`gastos_de_constitucion_y_organizacion`). Confianza: oficial leída.
- **Bienes usados:** Decreto 3182, art. 30: «la vida útil será estimada por el contribuyente no pudiendo ser mayor a la establecida en el presente reglamento para bienes similares.»
- **Vida útil distinta:** art. 31, último párrafo (texto 2021): «A solicitud del contribuyente, la Administración Tributaria podrá autorizar la aplicación de un periodo de vida útil distinto a lo enunciado precedentemente u otro sistema de depreciación, si lo considera técnicamente adecuado.»
- **Clasificación obligatoria:** art. 31: «En los inventarios, libros y estados financieros, deberá discriminarse la nomenclatura y clasificación de los bienes dispuestos en el presente artículo.» Quien tenga una clasificación más analítica puede seguir usándola «pero deberán ajustarse a la clasificación vigente […] en todas las declaraciones juradas».

### 2.3 Otras normas de valuación del activo fijo

- **Costo capitalizable (Decreto 3182, art. 23)** — «El valor impositivo de los activos fijos está constituido por el costo de adquisición o construcción más todos los gastos inherentes a dicha operación debidamente documentados. Asimismo, se adicionará el costo de incorporaciones posteriores, excluyendo los gastos de financiación y las diferencias de cambio, menos las depreciaciones acumuladas.» Confianza: oficial leída.
- **Inmuebles (art. 24):** si el precio no separa construcción y terreno, se usa la proporción de la **valuación fiscal del impuesto inmobiliario** a la fecha de adquisición. El concepto de mejoras incluye pavimentos, veredas, cercas y caminos de acceso. Confianza: oficial leída.
- **Construcciones en propiedad de terceros (art. 25):** si quedan en beneficio del propietario sin compensación, se deprecia el monto invertido en el plazo de vida útil del reglamento.
- **Reparaciones extraordinarias (art. 32):** «El costo de reparaciones extraordinarias que se realicen en los bienes muebles, se deducirá en cuotas anuales por los años de vida útil que las mismas agreguen a dichos bienes, lo que no podrá exceder a los años de vida útil del bien reparado […]. Se podrán considerar reparaciones extraordinarias, aquellas cuyo monto sea superior al veinte por ciento (20%) del valor fiscal neto del bien al principio del ejercicio en que se realice la misma.» El mantenimiento de equipos es un gasto general deducible (Ley 6380, art. 15 num. 3).
- **Intangibles (art. 33):** «se computarán en el activo, siempre que signifiquen una inversión real y el mismo sea adquirido a través de una compra.» Los gastos de registro y organización «podrán deducirse en el ejercicio en que se haya efectuado dicho gasto o amortizarse a cuota fija».
- **Ley 6380, art. 15 num. 16:** la amortización de intangibles es deducible «siempre que al momento de la adquisición hayan estado gravados por alguno de los Impuestos a las Rentas por parte del enajenante». El num. 4 del art. 16 (no deducible) excluye el valor llave autogenerado.

---

## 3. Método, inicio, valor residual, bajo valor, venta y baja (pregunta 2)

### 3.1 Método

- **Ley 6380, art. 11:** «La depreciación de bienes del activo fijo será la distribución sistemática del desgaste o deterioro que experimente el bien, el cual deberá considerar la estimación de vida útil para cada tipo o clase de activo fijo.» No nombra un método.
- **Decreto 3182, art. 31:** cuota sobre el valor «de acuerdo con los años de vida útil menos el porcentaje de valor residual». No dice «línea recta» literalmente.
- **RG 77/2020, Anexo, columna 11:** la cuota fiscal es «el "Valor Fiscal Revaluado o Valor Fiscal Neto del Ejercicio Anterior menos el Valor Residual Fiscal" […] por el número de años de Vida Útil Fiscal restantes, incluido el que se liquida [valor de la columna 10 / (valor de la columna 8 +1)]». Para un bien nuevo y sin revalúo eso da `(costo − residual) / vida útil`: **línea recta anual**. Confianza: oficial leída.
- **Otros sistemas:** requieren autorización de la Administración (art. 31, último párrafo, texto 2021). Una consulta vinculante de 2012 (régimen anterior, IRACIS) dice textualmente que la Administración «adopta como método de cálculo de Depreciación el Lineal o de Línea Recta». Confianza: oficial leída pero **de otro régimen**; solo apoya la inferencia. URL: <https://www.dnit.gov.py/web/portal-institucional/w/amortizacion-activo-intangible-prolongacion-de-tiempo-fiscal->.
- **Conclusión:** línea recta, por año, sobre `costo − valor residual`. Es una **inferencia** de la fórmula del cuadro. Ver D-DEP-1.

### 3.2 Desde cuándo se deprecia

- **Cita, Decreto 3182, art. 30 (sin cambios en 2021):** «A opción del contribuyente, la depreciación de cada uno de los bienes que integran el activo fijo, biológico e intangibles comenzará a partir del mes siguiente o del ejercicio siguiente a su incorporación o de finalizada la construcción total o parcial, en caso de edificios.»
- Entonces la regla es: **la opción es del contribuyente y se aplica bien por bien**. «En caso de edificios», el inicio se cuenta desde que termina la construcción (total o parcial), «de acuerdo con lo que establezca la Administración» (frase parcialmente tapada en el escaneo).
- **No encontré** cómo se prorratea el primer año cuando se elige «mes siguiente»: el cuadro del Anexo de la RG 77 es anual y no tiene una columna de meses. Ver D-DEP-2.
- Confianza: oficial leída.

### 3.3 Valor residual

- **Obligatorio y máximo 20% del costo** (Ley 6380, art. 11, citas en §2.1). La tabla lo fija por categoría.
- **Cálculo en el cuadro (RG 77, Anexo, col. 6):** «Valor Residual Fiscal: Consignar el valor que resulte de multiplicar el Valor de Costo o de Adquisición por el Porcentaje de Valor Residual Fiscal.»
- **Transición (Decreto 3182, art. 104 y RG 77, art. 2):** solo para bienes adquiridos **antes** de 2020. No aplica a una EAS nueva (la Ley de EAS es de 2020); lo anoto solo para no confundirlo.
- **Qué pasa con el residual al final de la vida útil:** no encontré regla expresa. Con la fórmula del cuadro, el bien queda con valor fiscal neto igual al residual. Ver D-DEP-6.

### 3.4 Bienes de bajo valor

- **Tope de importe para imputar directo al gasto: no encontrado.** Busqué en la Ley 6380 (arts. 8, 11, 14, 15), en el Decreto 3182 (todo el texto del PDF, buscando «bajo valor», «escaso valor», «valor unitario», «tope»), en las cartillas de IRE General, RESIMPLE y SIMPLE de la DNIT, y en la web de la DNIT con búsquedas por «bienes de poco valor». Solo hay un criterio: activo fijo es el bien tangible que se espera usar **más de un ejercicio fiscal** (Ley 6380, art. 11). Lo que se consuma en un ejercicio sería gasto; lo que dure más sería activo fijo y se depreciaría.
- Para esta EAS: no hay un umbral oficial para inventar. Si la política contable fija uno (por ejemplo, G. X), sería interna y debería ser validada. D-DEP-3.

### 3.5 Venta o baja

- **Venta (Ley 6380, art. 8, renta bruta num. 1):** «El resultado de la enajenación de bienes del activo fijo, el que se determinará por la diferencia entre el precio de venta y el valor de costo, menos las amortizaciones o depreciaciones admitidas fiscalmente.» Es decir, resultado = precio − (costo − depreciación fiscal acumulada). Confianza: oficial leída.
  - El plan propuesto tiene `17.01 UTILIDAD/PÉRDIDA EN VENTA DE ACTIVOS FIJOS` para el resultado.
- **Inmuebles y forestación:** el contribuyente puede optar por renta neta presunta del 30% del valor de venta (Ley 6380, art. 19, Renta Neta Presunta). Leído; no profundizado.
- **Baja por descomposición u obsolescencia (Decreto 3182, art. 58, texto del Decreto 6105/2021):** con auditor externo, este «será el responsable de comprobar el detalle de los bienes afectados que se darán de baja»; en los demás casos, «se certificará la realización del acto mediante la intervención del contador del contribuyente, debiendo suscribirse el acta pertinente, señalándose pormenorizadamente en la misma los bienes dados de baja con sus valores correspondientes. La respectiva acta formará parte del archivo tributario». Referencia: Ley 6380, art. 11 y art. 15 num. 15. Confianza: oficial leída.
- **Pérdidas extraordinarias** por incendio o siniestro no cubiertas por seguro: deducibles (Ley 6380, art. 15 num. 11).
- **Donación de un activo fijo:** su valor debe coincidir con el valor contable neto (Decreto 3182, art. 62).
- **Cambio de destino (art. 37):** el valor impositivo al cierre pasa a ser valor de costo como activo corriente al ejercicio siguiente, y a la inversa.
- **No encontré:** el tratamiento del IVA (comprobante de venta de un activo fijo) ni el mes hasta el que se deprecia el bien vendido. Ver D-DEP-10.

---

## 4. Revalúo fiscal (pregunta 3)

### 4.1 Qué existe hoy

- **Revalúo obligatorio (Ley 6380, art. 11, último párrafo):** «El Poder Ejecutivo podrá establecer el revalúo obligatorio de los bienes del activo fijo, cuando la variación del Índice de Precios al Consumo determinado por el Banco Central del Paraguay alcance al menos 20% (veinte por ciento), acumulado desde el ejercicio en el cual se haya dispuesto el último ajuste por revalúo. El reconocimiento del revalúo obligatorio establecido por el Poder Ejecutivo formará parte de una reserva patrimonial cuyo único destino podrá ser la capitalización.»
  - **Es una facultad, no una obligación anual.** Solo rige si el Poder Ejecutivo lo establece por decreto.
  - No es renta: el aumento de patrimonio por este revalúo queda fuera de la renta (Ley 6380, art. 8, num. 13).
  - **No encontré ningún decreto que lo haya dispuesto.** Revisé por título los 280 decretos del listado de la DNIT (<https://www.dnit.gov.py/web/portal-institucional/decretos>, que incluye 2026): ninguno trata de revalúo del activo fijo. Y la DNIT no publica coeficientes del IRE: el Anexo de la RG 77/2020 dice que el coeficiente se consigna «únicamente cuando el Poder Ejecutivo lo establezca, conforme al último párrafo del Art. 11 de la Ley N° 6380/19».
  - **No verifiqué** si el IPC acumulado ya superó el 20% desde 2019. Ver D-DEP-7.
- **Revalúo técnico o extraordinario (voluntario):** Ley 6380, art. 8 num. 13 y 14: los aumentos por revalúos técnicos «se considerarán imponibles en el ejercicio de su efectiva enajenación». Decreto 3182, art. 36: no es renta del ejercicio, «pero tampoco podrá ser considerada como gasto deducible la cuota de depreciación anual, ni como costo deducible el valor revaluado al momento de su efectiva realización. […] la reserva de revalúo así determinada, deberá ser expuesta en una cuenta separada dentro del patrimonio neto.» Y el art. 67: «Estas reservas no serán deducibles ni estarán gravadas al momento de su constitución, sino al momento de su efectiva realización.» Y el art. 23: se identifica como «Revalúo técnico no deducible» por separado. Confianza: oficial leída.
  - Es optativo y **no tiene efecto fiscal deducible**, solo contable.

### 4.2 Lo que ya no rige (secundario para el diseño)

- Bajo el IRACIS la DNIT publicaba cada año resoluciones de «Actualización» con coeficientes de revalúo por mes de adquisición. Ejemplo leído: **Resolución de Actualización N° 06/20 (06-07-2020)**, ejercicio cerrado al 30-06-2020, IRACIS e IRAGRO, «POR LA CUAL SE ESTABLECEN LOS COEFICIENTES DE REVALÚO DE LOS BIENES DEL ACTIVO FIJO». No menciona el IRE de la Ley 6380. URL: <https://www.dnit.gov.py/en/web/portal-institucional/w/resolucion-de-actualizacion-n-06>. Confianza: oficial leída (resumen de la página).
- **No encontré** resoluciones de actualización para ejercicios IRE (2020 en adelante) con coeficientes obligatorios.

### 4.3 ¿Condiciona el diseño?

Sí, de forma acotada: el cuadro tiene la columna «Coeficiente de Revalúo» y la cuota se recalcula con el valor revaluado. Para no cerrar la puerta hay que **guardar, por bien y por ejercicio, el valor fiscal neto al cierre** (no recalcularlo siempre desde el costo) y poder cargar un coeficiente opcional por categoría y ejercicio. No hace falta implementar el revalúo ahora. Ver §8.

---

## 5. Cuadro de depreciación (pregunta 4)

### 5.1 Qué modelo está vigente

La cadena de normas, tal como la citan los VISTOS de la RG 77/2020:

1. **RG 49/2014 (19-12-2014)**: Anexo 6, «Cuadro de Revalúo y Depreciación de Bienes del Activo Fijo».
2. **RG 94/2016**: «sustituye el Cuadro de Revalúo y Depreciación […] dispuesto en la Resolución General N° 49/2014». **No leí** esta resolución ni encontré su texto.
3. **RG 77/2020 (31-12-2020), arts. 2 y 4**: el contribuyente del IRE RG «deberá elaborar un Cuadro de Depreciación de los Bienes del Activo Fijo, conforme al modelo contenido en el Anexo»; el modelo «sustituye al modelo aprobado por la Resolución General N° 94/2016».
   - Texto: <https://www.dnit.gov.py/documents/20123/221869/RESOLUCION+GENERAL+N%C2%B0+77.pdf/1cf796c1-8bfd-4cbc-d69a-1c052ae5ec3d?t=1684181904180> (2 págs.) y <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-77-20>
   - Anexo (XLSX): <https://www.dnit.gov.py/documents/47797/47809/Resoluci%C3%B3n+General+N%C2%BA+77-20+-+Anexo.xlsx/f794aea6-31bc-3891-e885-98c8769c1e68?t=1681960429369>
   - Modificada en su art. 3 por la RG 102/2021 (solo medidas de transición del ejercicio 2021; no leída, vista solo por título en la página IRE de la DNIT).
   - Confianza: oficial leída (texto y las 22 columnas con sus definiciones).

**Consecuencia: la app debe emitir el modelo de la RG 77/2020, no el Anexo 6 de la RG 49/2014.** Aplica solo al **IRE Régimen General**.

### 5.2 Columnas del Anexo de la RG 77/2020 (22)

Cabecera: 1. identificación del contribuyente (razón social, RUC), 2. datos de la declaración jurada (formulario, N° de orden), 3. ejercicio fiscal (desde, hasta), 4. representante legal (nombre, RUC), 5. contador (nombre, RUC/CI).

| N° | Columna | Cómo se obtiene (definición del anexo, resumida) |
|---|---|---|
| | **BIENES** | |
| 1 | Descripción de los Bienes | Cada bien o partida, con fecha de adquisición y tipo |
| 2 | Valor de Costo o de Adquisición | Valor de compra en guaraníes, con documentación de respaldo |
| 3 | Fecha de Adquisición | La del documento de compra |
| 4 | Coeficiente de Revalúo | Solo cuando el Poder Ejecutivo lo establezca (art. 11 Ley 6380) |
| | **VALORES FISCALES** | |
| 5 | Porcentaje de Valor Residual Fiscal | El de la norma para cada tipo de bien |
| 6 | Valor Residual Fiscal | col. 2 × col. 5 |
| 7 | Años de Vida Útil Fiscal | Los de la norma vigente |
| 8 | Años de Vida Útil Fiscal Restantes | Al cierre del ejercicio que se liquida |
| 9 | Valor Fiscal Neto del Ejercicio Anterior | Col. 13 del ejercicio anterior (bien adquirido en el año: = col. 2) |
| 10 | Valor Fiscal Revaluado, o Valor Fiscal Neto del Ejercicio Anterior menos Valor Residual Fiscal si no hay revalúo | (col. 9 − col. 6) × col. 4 con revalúo; (col. 9 − col. 6) sin revalúo |
| 11 | Cuota Fiscal de Depreciación Anual | col. 10 / (col. 8 + 1) |
| 12 | Depreciación Fiscal Acumulada | col. 11 + col. 12 del ejercicio anterior |
| 13 | Valor Fiscal Neto al Cierre | col. 10 + col. 6 − col. 11 |
| | **VALORES CONTABLES** | |
| 14 | Valor Residual Contable | El estimado contablemente por el contribuyente |
| 15 | Años de Vida Útil Contable | A criterio de la empresa |
| 16 | Años de Vida Útil Contable Restantes | Al cierre |
| 17 | Valor Contable Neto del Ejercicio Anterior | Col. 22 del ejercicio anterior |
| 18 | Valor Contable Revaluado, o Valor Contable Neto del Ejercicio Anterior menos Residual Contable | (col. 17 − col. 14) × col. 4 con revalúo; (col. 17 − col. 14) sin revalúo |
| 19 | Cuota Contable de Depreciación Anual | col. 18 / (col. 16 + 1) |
| 20 | Cuota de Depreciación Anual no Deducible | col. 19 − col. 11 si la contable es mayor; si no, 0 |
| 21 | Depreciación Contable Acumulada | col. 19 + col. 21 del ejercicio anterior |
| 22 | Valor Contable Neto al Cierre | col. 18 + col. 14 − col. 19. «La sumatoria o total de esta columna deberá coincidir con los respectivos saldos de las cuentas del Balance General.» |

Hay además una fila de TOTALES. El archivo trae también las definiciones de cada columna (que están resumidas arriba).

### 5.3 Anexo 6 de la RG 49/2014 (modelo anterior, para comparar)

Archivo: <https://www.dnit.gov.py/documents/20123/209894/Resoluci%C3%B3n+General+N%C2%B0+49_14+Anexos.xls/1be53adb-b8a2-37d3-2561-7d2b93810387?t=1684192313142> (hoja `6_Cuadro de Revalúo`; el archivo se guardó por última vez en 2016, así que puede ser ya la versión de la RG 94/2016, no lo sé). Confianza: oficial leída.

Mismo encabezado (6 bloques) y 17 columnas (A a Q): Descripción de los Bienes; Fecha de Adquisición; Años de Vida Útil; Años de Vida Útil Restante; Valor de Costo o de Adquisición; Valor Fiscal Revaluado del Ejercicio Anterior; Valor Contable Revaluado del Ejercicio Anterior; Coeficiente de Revalúo; Valor Revaluado Fiscal; Valor Revaluado Contable; Cuota de Depreciación Anual Deducible; Cuota de Depreciación Anual no Deducible; Depreciación Fiscal Acumulada; Depreciación Contable Acumulada; Valor Fiscal Neto al Cierre; Valor Contable Neto al Cierre. No tiene columnas de valor residual ni de vida útil contable separada.

---

## 6. Contradicciones y diferencias entre fuentes

1. **Anexo 6 (RG 49/2014) frente a Anexo RG 77/2020.** Dos modelos de cuadro con distinta cantidad de columnas (17 y 22). Manda el de la RG 77/2020 (art. 4). El archivo de anexos de la RG 49/2014 en la web de la DNIT todavía trae la hoja 6. El plan de cuentas y `TRIBUTACION_PY.md` §5.1 hablan del «Anexo 6»; conviene actualizar esas menciones a «Anexo de la RG 77/2020».
2. **Decreto 3182 original (2019) frente a Decreto 6105/2021, art. 31.** Diferencias encontradas al comparar las dos redacciones:
   - Se agregó «v) Envases retornables: 3 años. Valor Residual: 10%.».
   - Ganado vacuno hembra: el texto de 2019 decía «destinado a la producción de leche»; el de 2021 dice «destinado a la cría y a la producción de leche». Sin relevancia para esta EAS.
   - Se agregó «u otro sistema de depreciación» al último párrafo.
   - El resto de las cifras que leí (muebles, informática, vehículos, maquinarias, construcciones, intangibles) es igual.
   - El art. 28 (envases) también se modificó. El art. 30 (inicio de la depreciación) no.
   - No encontré un decreto posterior que modifique los arts. 30 o 31 (revisé por título el listado de decretos de la DNIT). Pero solo leí títulos.
3. **Ley 6380, art. 11 solo habla de «bienes tangibles».** Los intangibles se tratan en el art. 10 (valuación a costo neto de amortizaciones), el art. 15 num. 16 (amortización deducible con condición) y el Decreto 3182, arts. 31 num. 2 y 33. Se leen bien juntas, pero la Ley no dice que los intangibles se amorticen en 5 años: eso lo dice el Decreto.
4. **Intangibles: Decreto (5 años, sin condición) frente a Ley (deducible solo si el enajenante estaba gravado).** La condición del art. 15 num. 16 puede dejar sin deducción a un software o licencia comprados a un no residente. No lo analicé. D-DEP-4.
5. **Decreto 3182, art. 21 frente a art. 40.** El art. 21 dice que quien pasa a liquidar el IRE RG valora el activo fijo a «costo de adquisición o construcción». El art. 40 dice que quien cambió de régimen y «ya dedujo el valor de los activos fijos» al adquirirlos «no podrá depreciarlos ni volver a deducirlo». Probablemente se aplican a casos distintos (nuevo vs. ya deducido), pero no es evidente. Relevante si la EAS pasa del SIMPLE al RG. D-DEP-8.
6. **Consultas vinculantes viejas.** Las encontradas en la DNIT (2011 y 2012 sobre intangibles a 4 años y 25% anual; otra sobre tanques a 15 años; otra de una eléctrica sobre revalúo con IRACIS) se refieren a la Ley 125/91 y el Decreto 6359/05. **No valen para el IRE**: se citan solo porque la DNIT todavía las muestra. Confianza: oficial leída. Ejemplo de la tasa vieja: <https://www.dnit.gov.py/web/portal-institucional/w/consulta-vinculante-cambio-de-criterio-vida-util-de-un-bien-intangible->.
7. **Cartilla del IRE SIMPLE frente a la Ley sobre sociedades.** Ya señalado en `TRIBUTACION_PY.md` D-1: la Ley 6380, art. 26, abre el SIMPLE a los numerales 1 y 8 del art. 2 y el FAQ del MIC dice que una EAS puede optar; la presentación de la DNIT lista «sociedades en general» entre los que **no** pueden. No lo resuelvo aquí.

---

## 7. IRE SIMPLE y RESIMPLE (pregunta 5)

- **IRE SIMPLE (Ley 6380, art. 26).** Fuente: <https://www.dnit.gov.py/web/portal-institucional/w/ley-n-6380-19>, oficial leída. Renta neta: la menor entre (1) ingresos menos egresos relacionados con la actividad, y (2) el 30% de la facturación bruta anual. Cita: «En este concepto, se podrá deducir la adquisición de mercaderías, insumos, materias primas, muebles, equipos, así como los egresos relativos a la construcción, remodelación o refacción de su establecimiento.»
  - **No hay depreciación:** la compra de muebles y equipos se deduce de una vez en el ejercicio. Los egresos se imputan por lo devengado (Decreto 3182, art. 76).
  - «Los resultados negativos derivados de los egresos previstos en el presente artículo no serán objeto de compensación ni arrastre.»
  - El texto dice «muebles, equipos». **No dice vehículos, maquinarias ni inmuebles**; ver D-DEP-16.
  - Los egresos deben ser reales, documentados, y el IVA incluido no se computa (Decreto 3182, art. 79).
  - Tasa del 10%.
- **Normas subsidiarias:** la Ley 6380, art. 32, aplica el Régimen General «subsidiariamente» a SIMPLE y RESIMPLE, «salvo las disposiciones específicas». No encontré en las cartillas ni en las presentaciones del SIMPLE (2024) ninguna mención a depreciación. Revisé la presentación: <https://www.dnit.gov.py/documents/20123/216504/PRESENTACI%C3%93N+IRE+SIMPLE+2024.pdf/e5c0b5be-0c29-9965-33ff-ff8a9b77cfb8?t=1714761224978.pdf>. Confianza: oficial leída.
- **Pasar del SIMPLE al IRE General:** Decreto 3182, art. 40: quien cambió al IRE RG y ya dedujo el activo al adquirirlo «no podrá depreciarlos ni volver a deducirlo al momento de la enajenación». Confianza: oficial leída. Si se elige SIMPLE en el primer año y se pasa al RG después, esos bienes no se depreciarían.
- **RESIMPLE (Ley 6380, art. 27):** cuota mensual fija según ingresos (₲ 20.000 a ₲ 80.000), solo para **empresas unipersonales** con ingresos hasta ₲ 80.000.000. No hay determinación de renta, y por lo tanto ni depreciación ni deducciones. **Una EAS no puede estar en RESIMPLE** (es una sociedad; ver también el art. 81 del Decreto 3182). Cartilla: <https://www.dnit.gov.py/documents/20123/216504/IRE+Resimple+Cartilla+6.08.24.pdf/a0586c49-bc45-a6df-377d-562d771ddcf1?t=1722964955242.pdf> (no menciona depreciación).
- **El cuadro de depreciación (RG 77/2020)** es solo para IRE Régimen General. No encontré obligación de presentarlo para SIMPLE.

---

## 8. Qué obliga a cambiar el diseño

No toco código; esto es para quien lo implemente.

1. **El inicio de la depreciación no puede estar fijo en «mes de alta».** Es opción del contribuyente por bien: `mes_siguiente` o `ejercicio_siguiente`. Hay que guardar la opción por bien (y definir un valor por defecto que apruebe el contador).
2. **Dos contabilidades en paralelo:** vida útil y valor residual **fiscales** (de la norma) y **contables** (de la empresa). La diferencia es la «cuota de depreciación anual no deducible». El cuadro lo exige.
3. **Vida útil y residual versionados por fecha de adquisición** (Decreto 3182, art. 30: rige la norma «vigente al momento de la adquisición»). Va en el mismo esquema de reglas con vigencia que ya usa el proyecto (`tax_rule_versions`).
4. **Guardar el valor neto al cierre por bien y por ejercicio**, porque la cuota se calcula sobre el valor neto del ejercicio anterior y los años restantes, no sobre el costo original. Esto además habilita un revalúo futuro sin rehacer el modelo.
5. **Coeficiente de revalúo opcional** por categoría y ejercicio, y una cuenta de reserva de revalúo en patrimonio, solo si aparece un decreto. No implementar ahora.
6. **El plan propuesto necesita retoques menores:** falta `1.02.04.04 MAQUINARIAS` (existe en la RG 49/2014); hay una sola cuenta de depreciación acumulada (1.02.04.99); `1.02.04.01 INMUEBLES` junta terreno y construcción, y el terreno no se deprecia; no hay cuenta para «otros bienes de PPE». El YAML deja `null` donde no hay cuenta adecuada.
7. **Régimen:** si la EAS está en IRE SIMPLE, no hay depreciación fiscal; las compras de activos van a deducción directa. Si pasa al RG, aplica el art. 40. La aplicación debería tomar el régimen de la configuración del contribuyente.
8. **Baja de bienes:** necesita un documento (acta del contador o constancia del auditor externo) y valores del bien dado de baja.
9. **Valor depreciable:** el costo capitalizable excluye gastos de financiación y diferencias de cambio (art. 23).
10. **El cuadro oficial está en guaraníes por bien**, con descripción libre: el módulo de activos debe permitir emitirlo con las 22 columnas y que el total de la col. 22 cuadre con las cuentas del balance.

---

## 9. No encontrado

| Dato | Qué busqué | Resultado |
|---|---|---|
| Tope de importe para gastar directo un bien de bajo valor | Ley 6380 (arts. 8, 11, 14, 15), Decreto 3182 completo (texto del PDF), Decreto 6105, cartillas IRE General/SIMPLE/RESIMPLE, búsquedas en dnit.gov.py | **No encontrado** |
| Palabras «línea recta» o «lineal» en una norma del IRE | Decreto 3182 (todo), Ley 6380, RG 77/2020 | **No encontrado** (solo en consultas viejas del IRACIS) |
| Prorrata mensual del primer año al elegir «mes siguiente» | RG 77/2020 y su anexo; Decreto 3182 art. 30 | **No encontrado** |
| Decreto del Poder Ejecutivo que establezca el revalúo obligatorio del activo fijo (IRE) | Listado de decretos de la DNIT (280 títulos), búsquedas web | **No encontrado** |
| Coeficientes de revalúo para ejercicios IRE | Resoluciones de la DNIT | **No encontrado** (solo hay los del IRACIS, hasta 2020) |
| Tratamiento expreso del software (¿intangible a 5 años o equipo de informática a 2?) | Decreto 3182 y 6105, Ley 6380, cartillas | **No encontrado** (el software no se nombra) |
| Regla expresa de que el terreno no se deprecia | Decreto 3182, art. 24 y 31 | **No encontrado** (se infiere de la exclusión en el art. 31) |
| Texto de la RG 94/2016 | Búsqueda web | **No encontrado** (solo la cita en los VISTOS de la RG 77/2020) |
| Texto de la RG 102/2021 | Solo vi su título en la página IRE | **No leído** |
| Versión de la Ley 6380 en bacn.gov.py | Búsqueda; el archivo es de unos 58 MB | **No leído**; usé la copia de la web de la DNIT |
| IPC acumulado desde 2019 (¿llegó al 20%?) | No lo busqué en el BCP | **No verificado** |
| Tratamiento del IVA en la venta de un activo fijo | No lo busqué a fondo | **No investigado** |
| Deducibilidad de vehículos de uso mixto o personal | No lo busqué | **No investigado** |

---

## 10. Dudas para el contador

**D-DEP-1. ¿Línea recta anual?** Ninguna norma del IRE usa esas palabras; el cuadro de la RG 77 equivale a línea recta anual. ¿Confirma? ¿Hay prorrata mensual del primer año?

**D-DEP-2. Inicio de la depreciación.** El art. 30 deja elegir «mes siguiente» o «ejercicio siguiente». ¿Cuál usa la EAS? ¿Es por bien o una política general? ¿Cómo se refleja en el cuadro anual (que no tiene meses) la depreciación del primer año con «mes siguiente»?

**D-DEP-3. Bajos valores.** No hay tope en las normas. ¿La EAS capitaliza todo bien tangible que dure más de un ejercicio, sin importar el precio? Si quiere una política interna (por ejemplo, gasto directo bajo cierto importe), ¿cómo se justifica ante la DNIT frente al art. 11 de la Ley?

**D-DEP-4. Software.** El reglamento no lo nombra. ¿Es «licencia» (intangible, 5 años) o «equipo de informática» (2 años)? ¿Qué pasa con el requisito del art. 15 num. 16 (enajenante gravado) si se compra a un proveedor del exterior? Las suscripciones (SaaS) ¿son siempre gasto del período?

**D-DEP-5. Contable frente a fiscal.** ¿Qué vida útil y residual contables usará la EAS (NIC 16 / NIF)? Si difieren de las fiscales, aparece la «cuota no deducible» y hay que ajustarla en la liquidación del IRE.

**D-DEP-6. Residual al final de la vida útil.** Con la fórmula del cuadro, el bien queda con valor neto igual al residual (por ejemplo, 10% o 20% del costo). ¿Se sigue llevando en libros? ¿Cómo se trata al venderlo o darlo de baja?

**D-DEP-7. Revalúo.** ¿Hay algún decreto vigente que disponga el revalúo obligatorio? ¿El IPC acumulado desde el último ajuste ya llegó al 20% (condición del art. 11 de la Ley)? ¿Conviene hacer un revalúo técnico voluntario? (No tiene efecto deducible.)

**D-DEP-8. Régimen de la EAS y cambio de régimen.** ¿La EAS está en IRE General o SIMPLE? En SIMPLE no hay depreciación. Si empezó en SIMPLE y pasa al General, ¿cómo aplica el art. 40 del Decreto 3182 (no depreciar lo ya deducido) frente al art. 21 (valuar a costo)?

**D-DEP-9. Reparaciones extraordinarias.** El art. 32 las define como las que superan el 20% del valor fiscal neto del bien al inicio del ejercicio y solo habla de bienes **muebles**. ¿Qué pasa con las reformas de un inmueble o de una mejora en local alquilado?

**D-DEP-10. Venta y baja.** ¿Hasta qué mes se deprecia un bien vendido en el año? ¿Qué comprobante se emite al vender un activo fijo y cómo se trata el IVA? ¿La baja por obsolescencia exige siempre el acta del contador (art. 58)?

**D-DEP-11. Costo capitalizable.** El art. 23 excluye gastos de financiación y diferencias de cambio. ¿Los gastos de importación, fletes y seguros del bien importado sí se capitalizan («gastos inherentes a dicha operación debidamente documentados»)?

**D-DEP-12. Terreno y construcción.** El art. 31 excluye el terreno. ¿Se separan en el registro? Si la escritura no los individualiza, se usa la valuación fiscal del impuesto inmobiliario (art. 24).

**D-DEP-13. Vehículo «utilitario».** ¿Una camioneta o utilitario de la EAS se deprecia a 10 años (c iii) o a 5 años (c i)? La norma no define «utilitarios».

**D-DEP-14. Clasificación.** ¿Un aire acondicionado, un teléfono, una impresora o un escritorio son «muebles y equipos» (5 años), «útiles y enseres» (2) o «informática» (2)? El reglamento no da ejemplos.

**D-DEP-15. «Restantes bienes» (g xi).** ¿Esta categoría residual (5 años, 20%) es solo del grupo Construcciones o de todo el activo fijo no listado?

**D-DEP-16. Alcance de «muebles, equipos» en el SIMPLE.** ¿Incluye vehículos y maquinarias? Si no, ¿se depreciarían aun en el SIMPLE, o no se deducirían?

**D-DEP-17. Vehículos de uso mixto.** ¿Cómo se trata la parte de uso personal del dueño (gastos personales no deducibles) en la depreciación de un vehículo? No investigué.

---

## 11. Fuentes y límites

**Oficiales leídas:**
- Ley 6380/2019 (copia en la web de la DNIT), arts. 7, 8, 10, 11, 14, 15, 16, 26, 27, 32: <https://www.dnit.gov.py/web/portal-institucional/w/ley-n-6380-19>
- Decreto 3182/2019 (PDF escaneado, 55 págs., con capa de texto): leí los arts. 21, 23, 24, 25, 30, 31, 32, 33, 36, 37, 40, 58, 62, 67, 76, 79, 80, 81, 92, 104. Verifiqué las cifras de las págs. 23 a 25 mirando las imágenes. En «equipos de informática» una firma tapa parte de la cifra (se lee «2 años»); la confirma el texto legible del Decreto 6105.
- Decreto 6105/2021 (PDF escaneado, 15 págs.). La fecha se leyó en la imagen de la pág. 1.
- RG 77/2020 (texto, PDF de 2 págs. y Anexo XLSX), RG 49/2014 (Anexo 6 en XLS).
- Cartillas DNIT: IRE General (27-08-2024), RESIMPLE (06-08-2024), presentación IRE SIMPLE 2024. Las revisé buscando depreciación y revalúo; no hay nada, salvo la mención de la Ley en la cartilla del IRE General.
- Resolución de Actualización 06/20 y consultas de la DNIT (régimen anterior): leídas por resumen de la página, no como PDF.
- Una imagen de la DNIT («Tratamiento fiscal del activo fijo», para contribuyentes con cierre en junio): es transitoria del ejercicio 2020 y no aplica a una EAS nueva. <https://www.dnit.gov.py/documents/20123/224320/Tratamiento+fiscal+del+activo+fijo.png/b282e394-58be-2b1f-e912-ed0c435f1353?t=1684775235766>

**Secundarias:** usé una reseña de impuestospy.com del Decreto 6105/2021 solo para encontrar el decreto; después leí el texto oficial. No cito ninguna cifra desde allí.

**Limitaciones:**
- Un asistente de IA hizo esta lectura. Las cifras de la tabla del art. 31 se contrastaron entre el Decreto 3182 original y el Decreto 6105, pero no las valida ningún contador.
- Algunas páginas de la DNIT las leí con un resumen automático de la página y no como texto completo (consultas vinculantes y Resolución de Actualización). Las cifras clave (art. 31, art. 30, art. 11) sí las leí del texto o de la imagen.
- No verifiqué si existen normas posteriores a las encontradas (otras resoluciones de la DNIT de 2022 a 2026 sobre depreciación). Busqué por título en la lista de decretos y con búsquedas web.

---

## Verificación de CONTADOR AI, bloque 3 (2026-11-25)

### Consultas de la DNIT bajo el Decreto 3182 (texto del Decreto 6105/2021)

Son tres consultas no vinculantes publicadas por la DNIT. No son normas, pero las cifras que citan las toma la DNIT del propio art. 31 vigente. Confirman la tabla de este documento con una fuente oficial independiente.

- **N.° 7340000519, del 16-12-2025** (equipos de informática, <https://www.dnit.gov.py/documents/20123/2741790/AMPLIAC.+DE+VIDA+%C3%9ATIL+DE+EQUIPOS+INFORM%C3%81T._ACTIVO+FIJO+A+UN+PLAZO+DE+5+A%C3%91OS.+N%C2%B0+800+CNV.pdf/f63b5c44-173c-e93a-ee13-329d02f8097e?t=1771246522439>):
  - «numeral 1), literal b) iii […] el periodo de vida útil es de 2 años, y su valor residual es de 10%; lo que se aplica a los equipos de informática».
  - Rechaza ampliarla a 5 años porque el informe técnico no estaba «sólidamente argumentado y debidamente respaldado».
- **N.° 737, de 2025** (maquinarias, <https://www.dnit.gov.py/documents/20123/422349/DEPRECIACI%C3%93N+DE+BIENES+DEL+ACTIVO+FIJO.+N%C2%B0+737.pdf/2ff0490d-d14e-515e-424a-bbf1b7082a83?t=1764935663595>):
  - «numeral 1), literal b) i) […] el periodo de vida útil es de 10 años, y su valor residual es de 20%; lo que se aplica a las maquinarias e implementos».
  - El informe tiene que ser de «un tercero, ajeno a la firma recurrente» y en castellano.
- **Consulta sobre equipos de tomografía**, de la SET antes de la DNIT (<https://www.dnit.gov.py/documents/47797/47809/IRE_Depreciaci%C3%B3n+bienes+del+activo+fijo.pdf/8caa69a5-3b98-4dd9-ce7a-0f8334f26abe?t=1680717914555>):
  - «“Muebles y Equipos en general”, según lo establecido en el numeral 1, literal a) i […] el periodo de vida útil será de cinco (5) años y su valor residual del 10%».
  - Autoriza 15 años con un informe técnico. La autorización «no es extensible a otros bienes de similar naturaleza».
  - **«la norma reglamentaria no contempla la facultad de modificar la categoría de los bienes»**: cada bien se clasifica según el Anexo.
- Las tres repiten la fórmula del art. 31: la cuota se aplica sobre el valor del activo fijo «de acuerdo con los años de vida útil, menos el porcentaje de valor residual».

**Para la app:**
- Confirmadas con fuente oficial independiente: informática (2 años, 10 %), maquinarias (10, 20 %) y muebles y equipos en general (5, 10 %).
- Una vida útil distinta de la tabla solo vale con una autorización particular de la DNIT para ese bien. Por eso la app no debería aceptar vidas útiles fiscales fuera de la tabla sin el número de esa autorización. Hecho en la D-125: la app exige el número de la autorización.
- **D-DEP-14 (clasificación):** sigue sin ejemplos oficiales. Lo único firme es que la DNIT no cambia la categoría: la elige el contribuyente según el Anexo.

### Las páginas viejas de la DNIT no sirven

Las páginas HTML de la DNIT sobre depreciación («Depreciación de período de vida útil…», «Amortización activo intangible…» de 2012 y «Depreciaciones y reservas de revalúo» de 2009) aplican la Ley 125/1991 y el Decreto 6359/2005, derogados. Por ejemplo, intangibles al 25 % anual y muebles a 10 años. **No se usan.**

### Cómo quedan las 17 dudas D-DEP

- **Decisiones de política contable.** Las toma CONTADOR AI con un criterio por defecto y el propietario puede cambiarlo:
  - D-DEP-2 (mes siguiente o ejercicio siguiente);
  - D-DEP-3 (bienes de bajo valor);
  - D-DEP-5 (vida útil contable);
  - D-DEP-7 (revalúo voluntario);
  - D-DEP-12 (separar terreno y construcción, con el dato de la escritura).
- **Dependen del perfil de la EAS:** D-DEP-8 y D-DEP-16 (régimen del IRE, D-1 y D-2).
- **Sin respuesta oficial vigente, después de buscar:**
  - D-DEP-1 (prorrata mensual del primer año);
  - D-DEP-4 (software);
  - D-DEP-9 (reformas de inmuebles);
  - D-DEP-13 («utilitarios»);
  - D-DEP-14 (clasificación);
  - D-DEP-15 («restantes bienes»);
  - D-DEP-17 (uso mixto).
  - Solo se resuelven con una consulta vinculante a la DNIT (Ley 125/1991, art. 241), que la presenta el contribuyente.
- **Con respuesta en la norma ya leída:**
  - D-DEP-6: el bien queda con su valor residual y, al venderlo, el resultado es precio − costo + depreciaciones admitidas (Ley 6380, art. 8).
  - D-DEP-10: la baja por obsolescencia exige el acta del contador o del auditor (art. 58).
  - D-DEP-11: el art. 23 incluye los «gastos inherentes a dicha operación debidamente documentados».

