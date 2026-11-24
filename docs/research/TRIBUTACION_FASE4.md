# Investigación tributaria, fase 4: registro de comprobantes, IVA y calendario

> **Estado: investigación preliminar. Nada de este documento está verificado.**
> Lo armó un asistente de IA leyendo fuentes oficiales el **2026-11-24**. Solo un contador matriculado puede validar cada punto. Todas las reglas derivadas quedan en `pending` (ver `tax_rules_candidatas.yaml`) y **no generan obligaciones ni cálculos en la aplicación** (BR-TAX-01).
> No es asesoramiento tributario. Completa a [`TRIBUTACION_PY.md`](TRIBUTACION_PY.md): lo que ya está ahí no se repite.

**Fecha de consulta de todas las fuentes:** 2026-11-24.

**Niveles de confianza:** los mismos de `TRIBUTACION_PY.md`.

| Nivel | Significado |
|---|---|
| **oficial leída** (`oficial_leida`) | Abrí y leí el texto en un sitio oficial (DNIT, BACN, Gaceta Oficial). |
| **oficial citada por terceros** (`oficial_citada_por_terceros`) | Una fuente oficial lo menciona, pero no leí el texto original. |
| **secundaria** (`secundaria`) | Solo lo encontré en prensa, estudios, firmas privadas o en una copia alojada fuera de un sitio oficial. |
| **no encontrada** (`no_encontrada`) | No hallé fuente oficial. |
| **calculado** | Solo en `feriados_py.yaml`: una fecha obtenida con un algoritmo a partir de una regla leída. |

**Documentos escaneados:** el Decreto 3107/2019 está escaneado sin texto. Lo leí mirando las páginas del PDF oficial (arts. 1° a 5° del cuerpo y arts. 4° a 30 del anexo). Usé la transcripción de impuestospy.com solo para ubicar los artículos.

**Archivos que acompañan este documento:**

| Archivo | Contenido |
|---|---|
| [`formato_registro_comprobantes.yaml`](formato_registro_comprobantes.yaml) | Formato oficial de importación del registro de comprobantes: archivo, nombre, columnas en orden, tipos, longitudes y tablas de códigos. |
| [`feriados_py.yaml`](feriados_py.yaml) | Feriados fijos y móviles (Ley 7544/2025), Semana Santa calculada, traslados y feriados adicionales de 2025 y 2026. |
| [`tax_rules_candidatas.yaml`](tax_rules_candidatas.yaml) | 14 reglas nuevas al final (sección «FASE 4»); total 39. Todas `pending`. No modifiqué las 25 anteriores. |

---

## Índice

1. [Formato de importación del Registro de Comprobantes](#1-formato-de-importación-del-registro-de-comprobantes)
2. [Formulario 120 v4 (IVA General)](#2-formulario-120-v4-iva-general)
3. [Crédito fiscal del IVA: Ley 6380 y Decreto 3107/2019](#3-crédito-fiscal-del-iva-ley-6380-y-decreto-31072019)
4. [Tipos de comprobante, formatos, CDC y dígito verificador](#4-tipos-de-comprobante-formatos-cdc-y-dígito-verificador)
5. [Feriados nacionales y días inhábiles](#5-feriados-nacionales-y-días-inhábiles)
6. [Contradicciones y dudas para el contador](#6-contradicciones-y-dudas-para-el-contador)
7. [Lo que no se pudo verificar](#7-lo-que-no-se-pudo-verificar)
8. [Índice de fuentes](#8-índice-de-fuentes)

---

## 1. Formato de importación del Registro de Comprobantes

**Conclusión: el formato existe y es público.** La investigación anterior no lo encontró porque no está enlazado desde la página de la RG 90/2021, sino desde la página «Registro de Comprobantes» de la DNIT.

### 1.1 Especificación Técnica para Importación (versión 1, junio de 2021)

- **Fuente:** <https://www.dnit.gov.py/documents/20123/203596/Especificaciones+T%C3%A9cnicas+para+registro+de+comprobantes+en+Marangatu.pdf/fca12623-f680-a630-e624-8c825db31b7d?t=1684176028356>
  - La misma especificación está en otra URL de la DNIT; comparé los dos PDF byte a byte y son idénticos: <https://www.dnit.gov.py/documents/44828/0/Especificaciones+T%C3%A9cnicas+para+registro+de+comprobantes+en+Marangatu.pdf/fd50732c-4232-750a-b253-5b14843cdccb?t=1682430005384.pdf>
  - Página que la enlaza: <https://www.dnit.gov.py/web/portal-institucional/registro-de-comprobantes>
- **Fecha:** «JUNIO 2021». Control de cambios: «1 — 06/2021 — Versión Inicial del Documento». Es la única versión que encontré.
- **Norma que la manda:** RG 90/2021, art. 6°: el contribuyente que importe archivos «deberá realizarla conforme a la especificación técnica que estará disponible en la página web de la SET».
- **Confianza:** oficial leída.

**Archivo** (sección «Consideraciones técnicas»):

- Cita textual: «El archivo debe tener el formato .CSV (delimitado por comas) o .TXT (delimitado por tabulaciones) y estar guardado con la codificación de caracteres UTF-8. Al momento de importar el archivo se debe comprimir en formato ZIP con el mismo nombre del archivo contenido.»
- **Nombre:** «<RUC>_REG_MMAAAA_XXXXX para la obligación 955-Registro Mensual de Comprobantes» y «<RUC>_REG_AAAA_XXXXX para la obligación 956». El RUC va **sin** dígito verificador. XXXXX es un identificador «alfanumérico, hasta 5 (cinco) posiciones», distinto en cada archivo. Ejemplo: `80000000_REG_012021_V0001.zip`.
- «El archivo puede contener un máximo de 5.000 (cinco mil) filas de datos.»
- Puede mezclar ventas, compras, ingresos y egresos en un mismo archivo.
- Los campos van «en el orden especificado en la tabla correspondiente a cada tipo de registro».
- «En los campos donde se registren valores de RUC, los mismos deben ser cargados sin el dígito verificador (DV).»
- «Los campos correspondientes a montos pueden ser registrados con o sin separador de miles. El separador de miles permitido es el punto (.)»
- Anexo: «El archivo a ser importado no debe contener los títulos utilizados como cabecera en la hoja de cálculo».
- **Contradicción interna:** el texto dice «delimitado por comas», pero el «Modelo del Formato y contenido» del anexo usa punto y coma: `1;11;80024627;MINISTERIO DE HACIENDA;109;05/05/2021;11138251;001-002-0000250;3630000;0;0;3630000;1;N;S;N;N;;`. Ver D-F4-1.

**Reglas generales** (sección «Consideraciones generales»):

- **Electrónicos y virtuales fuera:** «Este archivo no deberá incluir comprobantes emitidos a través del Sistema de Facturación Electrónica Nacional (E-kuatia) ni del Sistema de Comprobantes Virtuales, los cuales el contribuyente obtendrá directamente del Sistema Marangatu.»
- **Imputación:** «Un comprobante debe ser imputado al menos a una obligación (IMPUTA IVA, IMPUTA IRE o IMPUTA IRP-RSP), la que deberá estar activa para el informante a la fecha de emisión del comprobante.» Una parte puede quedar sin imputar («NO IMPUTA»), siempre que el resto se impute.
- **Nombre:** no se pide para RUC ni cédula paraguaya ni «Sin Nombre»: Marangatu lo toma de sus registros.

**Columnas:** 19 en ventas, 20 en compras, 15 en ingresos y 18 en egresos. El detalle completo (orden, tipo NUM o ALF, longitud máxima, obligatoriedad y notas) está en [`formato_registro_comprobantes.yaml`](formato_registro_comprobantes.yaml). Resumen de **compras**, el caso principal para una EAS:

| # | Campo | Tipo y long. | Notas |
|---|---|---|---|
| 1 | Código tipo de registro | NUM 1 | 2 |
| 2 | Tipo de identificación del proveedor | NUM 2 | 11 (RUC), salvo autofactura y despacho de importación |
| 3 | Número de identificación | ALF 20 | RUC sin DV |
| 4 | Nombre o razón social | ALF 250 | no requerido con RUC o CI |
| 5 | Tipo de comprobante | NUM 3 | Tabla 4 (109 = factura) |
| 6 | Fecha de emisión | ALF 10 | dd/mm/aaaa; no antes del 01/01/2021 salvo crédito |
| 7 | Timbrado | NUM 8 | 0 para despacho de importación |
| 8 | Número de comprobante | ALF 20 | `###-###-#######` |
| 9 | Monto gravado al 10% (IVA incluido) | NUM 20 | entero, sin decimales; 0 si no hay |
| 10 | Monto gravado al 5% (IVA incluido) | NUM 20 | ídem |
| 11 | Monto no gravado o exento | NUM 20 | ídem |
| 12 | Monto total | NUM 20 | = 9 + 10 + 11, mayor que 0 |
| 13 | Condición de compra | NUM 1 | 1 contado, 2 crédito; vacío = contado |
| 14 | Operación en moneda extranjera | ALF 1 | S/N; vacío = N |
| 15 | Imputa al IVA | ALF 1 | S/N |
| 16 | Imputa al IRE | ALF 1 | S/N (ver más abajo: solo IRE SIMPLE) |
| 17 | Imputa al IRP-RSP | ALF 1 | S/N |
| 18 | No imputa | ALF 1 | S/N |
| 19 | Número del comprobante asociado | ALF 20 | solo notas de crédito y débito |
| 20 | Timbrado del comprobante asociado | NUM 8 | ídem |

**Tablas de códigos** (Tablas 1 a 5 de la especificación):

- **Tipo de registro:** 1 ventas, 2 compras, 3 ingresos, 4 egresos.
- **Condición:** 1 contado, 2 crédito.
- **Identificación:** 11 RUC, 12 cédula de identidad, 13 pasaporte, 14 cédula extranjero, 15 sin nombre, 16 diplomático, 17 identificación tributaria.
- **Tipo de comprobante:** 101 autofactura, 102 boleta de transporte público, 103 boleta de venta, 104 boleta Resimple, 105 lotería y juegos de azar, 106 boleto o ticket aéreo, 107 despacho de importación, 108 entrada a espectáculos, 109 factura, 110 nota de crédito, 111 nota de débito, 112 ticket de máquina registradora; 201 a 211 para ingresos y egresos (IRP-RSP e IRE SIMPLE).
- **Booleanos:** S, N.

### 1.2 Modelo de planilla (XLSX)

- **Fuente:** <https://www.dnit.gov.py/documents/44828/0/Modelo+de+Planilla+para+Registro+de+Comprobantes+en+Marangatu.xlsx/3012e5a2-57d7-86b4-db8b-6212d39c81f3?t=1682441199202>
- **Fecha:** metadatos del archivo, creado el 18-05-2021 y modificado el 08-09-2022.
- **Confianza:** oficial leída. Lo abrí con la biblioteca estándar de Python, sin ejecutar nada del archivo.
- Cuatro hojas (VENTAS, COMPRAS, INGRESOS, EGRESOS), encabezados en la fila 10. Las columnas coinciden en orden y cantidad con la especificación.
- Única diferencia: en EGRESOS, las columnas 17 y 18 dicen «…DE VENTA ASOCIADO» y la especificación dice «…DE COMPRA ASOCIADO». Gana la especificación.

### 1.3 Guías de la DNIT sobre la importación y la carga manual

**Guía Paso a Paso, Registro de comprobantes a través de Importación** (julio de 2021)

- **Fuente:** <https://www.dnit.gov.py/documents/20123/203596/Guia+Paso+a+Paso+-+Registro+de+comprobantes+a+trav%C3%A9s+de+Importaci%C3%B3n.pdf/c0d1917c-8952-79e5-9e72-a64777916fa8?t=1684165228356.pdf>
- **Confianza:** oficial leída.
- Ruta: «DECLARACIONES INFORMATIVAS/GESTION DE COMPROBANTES INFORMATIVOS» → «Importar».
- «La SET tendrá un plazo máximo de hasta 72 horas para validar la información recibida».
- Estados del archivo: «RECIBIDO», «PROCESADO_TOTAL», «PROCESADO_ERROR», «PROCESADO_PARCIAL». Los errores llegan al buzón Marandu con el detalle por línea.
- «Si usted ya ha realizado la Confirmación del Talón de Presentación, podrá registrar los comprobantes únicamente a través de la opción "Registro Manual".» Esto lo cambió la norma después: ver D-F4-3.

**Presentación «Opción Importar»** (agosto de 2021)

- **Fuente:** <https://www.dnit.gov.py/documents/47797/47809/Registro+de+comprobantes+en+el+Marangatu+-+Opci%C3%B3n+Importar.pdf/67b5cd0a-b20c-a25a-d368-c4df072ee84d?t=1681834631316>
- **Confianza:** oficial leída.
- «No olvidar que los comprobantes timbrados deben contener 13 dígitos en la casilla de N° DE COMPROBANTE.»
- Errores frecuentes que lista la DNIT: cabecera y cálculos auxiliares dentro del archivo; facturas cargadas como egresos; archivo vacío; tipo 11 sin número de RUC.

**Guía Paso a Paso, Registro manual de comprobantes** (septiembre de 2022)

- **Fuente:** <https://www.dnit.gov.py/documents/44828/0/Guia+Paso+a+Paso-+Registro+manual+de+comprobantes+a+trav%C3%A9s+del+sistema+Marangatu.pdf/5dc720af-2425-187a-ff92-0bbfbbfbb578?t=1682441119323>
- **Confianza:** oficial leída.
- **Moneda extranjera:** «Si la operación se realizó en moneda extranjera, los montos a registrar deben estar cambiados/convertidos a guaraníes.»
- **IVA incluido:** «El Monto Gravado 10% y el Monto Gravado 5% se deberán consignar con el IVA INCLUIDO.» Marangatu calcula el IVA.
- **IRE solo para el SIMPLE:** los botones de imputación son «IVA, IRP RSP e IRE (este último aplicable únicamente para el IRE SIMPLE)». Ver D-F4-2.
- **Notas de crédito y débito:** «En la opción Ventas se registran las Notas de Crédito recibidas y las Notas de Débito emitidas.» Y en compras, «las Notas de Crédito emitidas y las Notas de Débito recibidas». Ver D-F4-4.
- **No impacta solo en la declaración:** «al imputar los comprobantes a las obligaciones, estos montos no impactan automáticamente en sus declaraciones juradas de liquidación de impuestos. Usted deberá verificar […] y realizar los cálculos necesarios para presentar sus declaraciones juradas impositivas.» Esto justifica el borrador del Formulario 120 (§2).

### 1.4 Comprobantes electrónicos (CDC) y alternativas a la importación

**No hay columna para el CDC** en el archivo de importación. Los documentos electrónicos se tratan aparte.

**Guía «Cómo obtener comprobantes electrónicos y virtuales»** (mayo de 2026)

- **Fuente:** <https://www.dnit.gov.py/documents/20123/437212/Gu%C3%ADa+Paso+a+Paso+-+C%C3%B3mo+obtener+comprobantes+electr%C3%B3nicos+y+virtuales.pdf/31a43846-a0e3-9ad9-7003-bc19bc5bc92d?t=1778092596059>
- **Confianza:** oficial leída.
- «En el registro manual o en los archivos importados no deberán ser incluidos los comprobantes electrónicos ni virtuales.»
- Opción «Obtener Comprobantes Electrónicos y Virtuales», separada en «Compras a Imputar» y «Ventas a Imputar».
- Tres modos de imputación:
  - «Seleccionar Comprobantes»: hasta 200 comprobantes en el período.
  - «Imputar todo»: todos a los mismos impuestos.
  - «Adjuntar Archivo»: con más de 200 comprobantes, o para facturadores del «Sistema Transaccional - Sistema Contribuyente E-kuatia». Marangatu genera un TXT separado por comas con una columna «NÚMERO DE IDENTIFICADOR DEL COMPROBANTE»; el contribuyente marca «S» o «N» en las columnas de cada impuesto y lo devuelve en CSV o TXT, zipeado, con el mismo nombre («RUC_AAAAMM_TIPO DE REGISTRO_ID_NÚMERO DE ARCHIVO»). La estructura completa de ese archivo **no está publicada**.
- **IRE General:** «no aplica imputar al IRE aquellos comprobantes que serán utilizados única y exclusivamente en la liquidación del IRE GENERAL como costo o gasto; en cuyo caso debe marcar la opción "No imputar"».
- Marangatu se sincroniza con el SIFEN por lotes: lo transmitido después de la última sincronización no se ve hasta la siguiente.

**Imputación automática: RG DNIT N° 12/2024** (31-05-2024)

- **Fuente:** <https://www.dnit.gov.py/documents/20123/796215/Res.+General+DNIT+N%C2%B0+12_2024.pdf/06555b22-920e-f0ac-74d9-f5b6aa50329f?t=1717201434815>
- **Confianza:** oficial leída. La investigación previa ya leyó los arts. 5° y 7°; agrego los arts. 2° y 9°.
- **Art. 2°:** los facturadores de e-Kuatia «podrán informar el código de la obligación afectada a sus operaciones al momento de emitir y transmitir la Factura Electrónica, Nota de Crédito Electrónica, Nota de Débito Electrónica y Autofactura Electrónica al SIFEN». Para ellos «se realizará la imputación automática».
- **Art. 3°:** rige para comprobantes aprobados «a partir del día siguiente hábil de la publicación de la presente resolución, siempre que se haya informado el código de la obligación afectada».
- **Art. 9° (texto vigente de la RG 90/2021):** después del talón se pueden incorporar registros «de manera individual (carga manual) o mediante la importación de archivos».
- **Para la aplicación:** si el proyecto de facturación informa el código de la obligación (211) en cada documento que emite, las ventas electrónicas de la EAS quedarían imputadas solas. Las compras electrónicas recibidas igual hay que imputarlas en Marangatu. Ver D-F4-13.

**Otras resoluciones revisadas que no tocan el formato:**

- **RG 94/2021** (06-08-2021): solo dice que no confirmar enero a junio de 2021 no es incumplimiento hasta el 31-10-2021. Oficial leída: <https://www.dnit.gov.py/documents/20123/199761/RG_+94+Medidas+administrativas+RG+N%C2%B0+90.pdf/05c1be35-52d5-9ade-5cdf-d08d83854851?t=1682697830526>
- **RG 104/2021** (09-12-2021): grupos y plazos de confirmación; identificación genérica para extranjeros no residentes desde enero de 2022 (art. 5°). No menciona archivos. Leída en la DNIT con un asistente de lectura web: <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-104-21-1>
- **Res. DNIT 730/2023** (29-12-2023): sin incumplimiento ni sanción hasta el 30-04-2024 para 2022, 2023 y enero-febrero de 2024. Oficial leída: <https://www.dnit.gov.py/documents/20123/267216/29_12+Resol+DNIT+N%C2%B0+730_23+RG+90.pdf/4d63bcf9-8fb3-e29d-81a3-19bcd0433863?t=1703894983451>
- **RG 131/2023** (06-06-2023): modificó el art. 9° para permitir importar después del talón (noticia DNIT). Hoy rige el texto de la RG DNIT 12/2024. No leí la RG 131.
- **RG DNIT 07/2024:** según la página DNIT de la RG 17/24, trata de la confirmación del talón. No leí su texto.

### 1.5 Qué hacer con esto en la aplicación

1. Exportar compras y ventas **no electrónicas** (preimpresas, autoimpresor, despachos, tickets) con este formato, un ZIP por lote de hasta 5.000 filas.
2. **No exportar** los documentos electrónicos: listarlos para que el usuario los impute en Marangatu, o asegurarse de que el proyecto de facturación informe la obligación al emitir.
3. Mostrar el archivo como **borrador**; la DNIT valida en hasta 72 horas y puede rechazar líneas.
4. Antes del primer uso real, probar con un archivo de una o dos líneas (D-F4-1).

---

## 2. Formulario 120 v4 (IVA General)

### 2.1 Versión vigente

- **RG N° 33/2020** (07-01-2020), art. 2°: «Impuesto al Valor Agregado — IVA GENERAL — 120 Versión 3 [hasta 12/2019] — 120 Versión 4 [desde 01/2020]». Art. 5°: lo usa quien realice «operaciones gravadas y exoneradas (incluidas las exportaciones)», con la obligación 211, mensual según el Calendario Perpetuo. El Anexo del Exportador y la Hoja de Cálculo son solo para inscriptos en el Registro de Exportadores.
  - Fuente: <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-33-20>. Confianza: oficial leída.
- La página de formularios e instructivos de la DNIT solo ofrece la **versión 4** como vigente (también hay instructivos de versiones anteriores). No encontré una versión 5.
  - <https://www.dnit.gov.py/web/portal-institucional/formularios-instructivos>

### 2.2 Estructura

- **Formulario:** <https://www.dnit.gov.py/documents/44828/89027/Formulario+N%C2%B0+120+IVA+Versi%C3%B3n+4.pdf/ced4ba56-a201-5126-29ea-c233d01ed6a4?t=1680627132264> (PDF del 07-02-2020).
- **Instructivo:** <https://www.dnit.gov.py/documents/47797/47809/Instructivo+del+Formulario+N%C2%B0+120+IVA+Versi%C3%B3n+4.pdf/63799cd8-6212-3c22-779b-51b2f97a136b?t=1680624028092.pdf> («Instructivo del Formulario N° 120 IVA 04-01-2020»).
- **Confianza:** oficial leída.

**Reglas generales del instructivo:**

- «LOS IMPORTES SE CONSIGNARÁN SIN CÉNTIMOS» (encabezado del formulario).
- «Los montos de las enajenaciones y/o prestación de servicios (Rubro 1, Col. I), los montos acumulados (Rubro 2), de las Compras (Rubro 3, Col. I y II) y del Anexo del Exportador (Col. I y II) deberán registrarse **sin incluir el IVA**.» Atención: el registro de comprobantes usa montos **con** IVA incluido (§1.1).
- «Las bases imponibles diferenciadas establecidas en la Ley N° 6.380/2019 y sus reglamentaciones deberán ser calculadas y el resultado de las mismas consignadas en las casillas correspondientes.»
- Encabezado: 01 original, 02 rectificativa, 05 cese, período «MM/AAAA».

**Rubro 1: enajenaciones del período** (Col. I monto imponible; Col. II IVA débito 5%; Col. III IVA débito 10%)

| Inc. | Concepto | Col. I | Col. II | Col. III |
|---|---|---|---|---|
| a | Gravadas al 10% | 10 | — | 22 |
| b | Productos agrícolas en estado natural al 5% | 150 | 156 | — |
| c | Otros bienes y servicios al 5% | 151 | 157 | — |
| d | Exoneradas o no alcanzadas | 12 | — | — |
| e, f, g | Exportaciones (solo exportadores) | 152, 153, 14 | — | — |
| h | Ajustes de precios, devoluciones realizadas, descuentos obtenidos y recupero por incobrables, al 10% | 15 | — | 23 |
| i | Ídem al 5%, productos agrícolas | 154 | 158 | — |
| j | Ídem al 5%, otros bienes y servicios | 155 | 159 | — |
| k | Ídem exonerados o no alcanzados | 17 | — | — |
| l | Totales | 18 | 21 | 24 |

**Rubro 2: acumulado de los últimos 6 meses, incluido el que se declara** (base del prorrateo)

- 160 gravadas en el mercado interno (suma de 10, 151, 15 y 155, según el instructivo); 161 agrícolas (150 + 154); 26 exoneradas o no alcanzadas (12 + 17); 27 total mercado interno; 162, 163, 29 y 30 exportaciones; 31 total.

**Rubro 3: compras locales e importaciones del período** (Col. I base 5%, Col. II base 10%, Col. III IVA crédito)

| Inc. | Concepto | 5% | 10% | IVA |
|---|---|---|---|---|
| a | Atribuido directamente a operaciones gravadas | 32 | 35 | 38 |
| b | Atribuido indistintamente a gravadas, exoneradas o no alcanzadas | 33 | 36 | 39 |
| c | Proporcional: «Rubro 3, Col. III: Inc. b x (Rubro 2 Inc. a+b/ Inc. d)» | — | — | 164 |
| d | Proporcional con exportación (hoja de cálculo) | — | — | 165 |
| e | Ajustes de precios, devoluciones y descuentos otorgados por ventas ya declaradas, e incobrables | 34 | 37 | 42 |
| f | Total IVA crédito (a + c + d + e) | — | — | 43 |

**Rubro 4: determinación del impuesto o del saldo técnico**

- 44 IVA débito (21 + 24); 45 IVA crédito (43); 46 saldo a favor del período anterior (casilla 47 de la DJ anterior).
- 166 saldo a favor si 44 < 45 + 46; 167 saldo que se remite al fisco (art. 91 de la ley); 47 saldo a trasladar (166 − 167).
- 48 saldo a favor del fisco si 44 > 45 + 46; 49 crédito del exportador; 168 deducción de la Ley 4962/2013 (personas con discapacidad, no trasladable); **50 impuesto determinado** (48 − 49 − 168).

**Rubro 5: impuesto determinado y saldo financiero**

- 55 impuesto determinado (de 50); 51 saldo a favor del período anterior (casilla 54 de la DJ anterior); **52 retenciones** que le practicaron al contribuyente en el período; 169 percepciones; 56 multa por presentar tarde.
- 53 = 51 + 52 + 169; 57 = 55 + 56.
- 54 saldo a favor del contribuyente (si 53 > 57), «No trasladable al Rubro 4»; **58 saldo a pagar** (si 57 > 53).

**Rubro 6: compras vinculadas a operaciones exoneradas o no alcanzadas**

- 59/65 compras al 10% y su IVA; 60/66 al 5%; 61 y 62 compras exentas (incluidas autofacturas); 63 ajustes; **64 IVA costo o gasto deducible en el IRE o IRP** (65 + 66 + diferencia entre 39 y 164 + casillas del exportador); 170 IVA remitido al fisco, no deducible.

**Para el borrador de la aplicación:** con el registro de compras y ventas del mes, la app puede calcular las casillas 10, 22, 151, 157, 12, 15/23, 155/159, 18/21/24, 32/35/38, 33/36/39, 164, 34/37/42, 43, 44, 45 y 50, y pedir al usuario 46, 51, 52 y 169 (vienen de la DJ anterior y de la cuenta corriente). Una EAS que no exporta no usa 14, 29, 49, 152, 153, 162, 163 ni 165. Dudas en D-F4-6 y D-F4-7.

---

## 3. Crédito fiscal del IVA: Ley 6380 y Decreto 3107/2019

### 3.1 Fuentes

- **Ley N° 6380/2019**, arts. 85 a 96, texto en la DNIT: <https://www.dnit.gov.py/web/portal-institucional/w/d-ley-n-6380-19>. Confianza: oficial leída.
- **Decreto N° 3107/2019** «Por el cual se reglamenta el Impuesto al Valor Agregado (IVA) establecido en la Ley N° 6380/2019».
  - Fuente: <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3107-19.pdf/d723b322-e502-e34b-18bc-3df7bfd0f785?t=1681423809891>
  - **Fecha:** «Asunción, 19 de diciembre de 2019» (manuscrito, legible en la primera página).
  - **Vigencia:** desde el 01-01-2020 (art. 4°). Deroga el Decreto 1030/2013 (art. 2°).
  - **Confianza:** oficial leída, mirando las páginas escaneadas.
  - **Modificaciones que vi:** el Decreto 8175/2022 modifica el art. 19 del anexo (servicios personales; no aplica a una EAS) y el Decreto 5584/2021 el art. 37 (retenciones de exportadores). Solo por título. No hice un rastreo completo de modificaciones.

### 3.2 Qué integra el crédito y cuándo

- **Ley, art. 88:** «El IVA Crédito estará integrado por: 1. La suma del impuesto incluido en los comprobantes de compras en plaza **realizadas en el mes**, que cumplan con lo previsto en el artículo 92 de la presente ley. 2. El impuesto pagado en el mes al importar bienes. 3. Las retenciones o percepciones del impuesto efectuadas a los beneficiarios radicados en el exterior».
- **Decreto, art. 14:** «El impuesto se determinará utilizando el criterio de lo devengado.»
- **Plazo para usar el crédito de comprobantes atrasados: no encontrado.** La letra del art. 88 habla de compras «realizadas en el mes». No hallé una norma que diga si una factura de un mes anterior, recibida tarde, se puede computar después ni hasta cuándo. Ver D-F4-5.

### 3.3 Requisitos

- **Ley, art. 89:** «la deducción del IVA Crédito sólo podrá efectuarse cuando:
  1. El mismo provenga de bienes o servicios que están afectados directa o indistintamente a las operaciones gravadas por el impuesto.
  2. Representen una erogación real.
  3. El comprobante que lo respalde identifique el nombre o razón social, su identificador RUC, la indicación precisa y detallada del bien o servicio adquirido y los demás requisitos legales y reglamentarios. No se podrá invocar el IVA Crédito respaldado con documentos visiblemente adulterados, o cuando los datos consignados en los mismos no reflejen la realidad de los hechos o sujetos en ellos consignados, salvo prueba en contrario.»
- **Ley, art. 92:** comprobantes «debidamente timbrados por la Administración Tributaria»; en todos los casos se consigna el nombre y el documento o RUC del comprador, «salvo que el tipo de comprobante utilizado pueda ser emitido en forma innominada»; conservar «por el plazo de prescripción».
- **Decreto, art. 22:** «El IVA Crédito implícito en los comprobantes, solo podrá ser invocado como tal siempre que la información contenida en los mismos refleje la realidad de la operación, el timbrado se encuentre vigente, y no posean enmiendas ni adulteraciones, verificaciones que serán responsabilidad del adquirente.» El contribuyente «está obligado a verificar […] los datos relacionados a la autorización y vigencia del timbrado».
- **Decreto, art. 26:** los comprobantes «se regirán conforme a los reglamentos generales o particulares vigentes que regulan la materia».
- **Decreto, art. 5° (cuerpo):** hasta un nuevo reglamento, rigen el **Decreto N° 6539/2005** «Por el cual se dicta el Reglamento General de Timbrado y uso de Comprobantes de Venta, Documentos Complementarios, Notas de Remisión y Comprobantes de Retención» y sus modificaciones (8345/2006, 2026/2009, 10797/2013, 312/2018), más el Decreto 7795/2017 (SIFEN) y la RG 61/2015. **No leí el Decreto 6539/2005.**
- **Electrónicos:** el **Decreto N° 872/2023** reglamenta la emisión por SIFEN (ver §4.1). Art. 4°: el documento aprobado por el SIFEN «es válido para todos los efectos tributarios».

### 3.4 Operaciones gravadas, exentas y mixtas (prorrateo)

- **Ley, art. 88:** «Cuando en forma simultánea se realicen operaciones gravadas, no gravadas y con la base imponible diferente al precio neto, la deducción del IVA Crédito afectado indistintamente a las mismas se realizará en la misma proporción en que se encuentren las operaciones gravadas con respecto a las totales, en el período que establezca el Poder Ejecutivo. Se entenderá que la operación gravada se refiere a aquellas sobre las cuales se aplica la tasa del impuesto.»
- **Decreto, art. 18:** la proporción es la de «los ingresos de las operaciones gravadas con respecto a los ingresos totales en el periodo correspondiente a los últimos seis (6) meses, incluyendo el que se liquida». Para nuevos contribuyentes: «un período transitorio que comprenderá dicho momento y el mes por el que se liquida el impuesto, hasta que se completen los cinco (5) primeros meses».
- **Ley, art. 91:** quien vende exonerado o no gravado trata el IVA de esas compras como costo o gasto del IRE o IRP. Formulario 120, casilla 64.
- **Decreto, art. 29:** las cuentas de IVA no van a resultados del IRE General, «salvo que se refieran al IVA incluido en los comprobantes de compras afectados a las operaciones exoneradas» o de exportación no recuperable, o al saldo remitido.

### 3.5 Compras no deducibles (lo que se encontró)

- No afectadas a operaciones gravadas, sin erogación real, o con comprobante que no cumpla requisitos (art. 89).
- Timbrado vencido, enmiendas o adulteraciones (Decreto, art. 22).
- La parte proporcional a operaciones exentas o no gravadas (art. 88; Decreto, art. 18).
- Bienes destruidos, sustraídos o de los que se pierde la posesión: «el contribuyente deberá revertir el IVA Crédito afectado a dichos bienes» (art. 88).
- **No encontré una lista cerrada de compras no deducibles para el IVA** (por ejemplo, gastos personales del dueño). La regla general es el art. 89, num. 1. Ver D-F4-9.

### 3.6 Débito, ajustes, incobrables, moneda y saldos

- **Débito (ley, art. 87):** la suma del impuesto de las operaciones gravadas del mes, menos el de devoluciones, bonificaciones, descuentos e incobrables.
- **Descuentos (decreto, arts. 16 y 28):** los del momento de la venta se muestran en la misma factura y se declaran por el neto; los posteriores se documentan con nota de crédito; «los ajustes debidamente documentados deberán estar reflejados en la liquidación que presenten en el mismo período fiscal» el vendedor y el comprador. El descuento no puede superar el costo.
- **Incobrables (decreto, art. 17):** el primero de: 36 meses desde que es exigible, inhibición general inscripta, quiebra o quita en concordato. Si después se cobra, vuelve a ser débito (art. 15).
- **Moneda extranjera (decreto, art. 13):** «tipo de cambio comprador o vendedor, en el mercado libre a nivel bancario al cierre del día anterior en que se realizó la operación, dispuestas por el Banco Central del Paraguay y publicadas en la página Web de la Administración Tributaria, o la cotización consignada en el correspondiente comprobante de venta». Importación y exportación: el de Aduanas a la fecha del despacho.
- **Saldo técnico (decreto, art. 20):** «el excedente del IVA Crédito podrá ser utilizado en las liquidaciones posteriores del impuesto a partir del periodo fiscal inmediato siguiente, sin que ello genere derecho a devolución en ningún caso. Para tal efecto, dicho excedente se denominará "saldo técnico".»
- **Declaración mensual (decreto, art. 30):** aunque no haya operaciones; consolida sucursales.

### 3.7 Cálculo del IVA incluido y base del 5%

- **Tasas (ley, art. 90):** 5% para alquiler de vivienda, inmuebles, canasta familiar, productos agrícolas, hortícolas, frutícolas y pecuarios, y medicamentos; 10% para todo lo demás. La canasta familiar está detallada en el decreto, art. 23.
- **Fórmula oficial:** Manual Técnico SIFEN v150, campo E735 dBasGravIVA: «[EA008* (E733/100)] / 1,1 si la tasa es del 10%» y «[EA008* (E733/100)] / 1,05 si la tasa es del 5%»; E736 dLiqIVAItem: «E735 * (E734/100)». EA008 es el total del ítem con IVA y E733 la proporción gravada.
  - Fuente: <https://www.dnit.gov.py/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf>. Confianza: oficial leída.
- **Divisores 11 y 21:** consecuencia aritmética, no cita. Con total T: IVA 10% = (T / 1,1) × 0,10 = T / 11; IVA 5% = (T / 1,05) × 0,05 = T / 21.
- **«Base imponible del 5%»:** la tasa de 5% se aplica sobre la base del art. 85. No es una base reducida en general. Las bases reducidas son otras: inmuebles al 30% del valor (art. 85, num. 3), bienes afectados a servicios personales al 30% (num. 9), importador casual +30% (num. 7). Ver regla IVA-BASES-DIFERENCIADAS.
- **Redondeo:** no encontré una regla oficial para redondear el IVA por comprobante. El formulario va sin céntimos. Ver D-F4-7.

---

## 4. Tipos de comprobante, formatos, CDC y dígito verificador

### 4.1 Tipos de comprobante

**Para el registro de comprobantes:** la Tabla 4 de la especificación (§1.1): factura (109), nota de crédito (110), nota de débito (111), autofactura (101), boleta de venta (103), boleta Resimple (104), ticket de máquina registradora (112), despacho de importación (107), etc.

- Autofactura, ticket, boleta Resimple y lotería: en compras «solo se registra el campo MONTO TOTAL DEL COMPROBANTE», con 0 en los gravados. Es decir, **no dan crédito fiscal** en el registro.
- Despacho de importación: timbrado 0, sin número de comprobante, proveedor con identificación distinta de RUC.

**Electrónicos: Decreto N° 872/2023** «Por el cual se reglamenta la emisión electrónica de comprobantes de venta y otros documentos tributarios, a través del Sistema Integrado de Facturación Electrónica Nacional (SIFEN)»

- Fuente: <https://www.dnit.gov.py/documents/20123/559197/Decreto+N%C2%B0+872-23.pdf/c86edb49-54e2-367c-8626-13390cea60b1?t=1704212315637>
- Fecha: 2023; el día y el mes no se leen en el texto extraído. Confianza: oficial leída.
- **Art. 3°:** comprobantes de venta electrónicos (factura, factura cambiaria, factura de exportación, autofactura, boleta Resimple, boleta de entrada a espectáculo); documentos complementarios (nota de crédito y de débito); comprobantes electrónicos (ingreso IRP, donación, importación, retención, percepción); recibo de dinero; nota de remisión. «La DNIT podrá implementar de manera gradual la utilización de estos Documentos Electrónicos».
- **Art. 2°, num. 7:** CDC: «conformado por cuarenta y cuatro (44) dígitos numéricos que permiten identificar, de manera única, un documento electrónico». **Num. 21:** «KuDE: Es la representación gráfica de un Documento Tributario Electrónico, en formato físico o digital.»
- **Art. 12:** la nota de crédito electrónica debe estar «asociada a una Factura Electrónica mediante la información de su Código de Control (CDC)». Entre facturadores electrónicos, requiere el evento de consentimiento del receptor. Sirve también para documentar un incobrable.
- **Art. 13:** la nota de débito electrónica, también asociada a una factura determinada.

**Manual Técnico SIFEN v150** (septiembre de 2019), campo C002 iTiDE: «1= Factura electrónica; 2= Factura electrónica de exportación (Futuro); 3= Factura electrónica de importación (Futuro); 4= Autofactura electrónica; 5= Nota de crédito electrónica; 6= Nota de débito electrónica; 7= Nota de remisión electrónica; 8= Comprobante de retención electrónico (Futuro)». Confianza: oficial leída. No revisé las 27 notas técnicas posteriores.

**Comprobantes preimpresos (boleta, ticket, factura de imprenta):** se rigen por el Decreto 6539/2005 y sus modificaciones (citado en el Decreto 3107, art. 5°). **No lo leí.** Para la EAS importa solo del lado de las compras: si se inscribió desde el 01-04-2025, únicamente emite electrónicos (RG DNIT 21/2024, art. 9°, ya en `TRIBUTACION_PY.md` §6).

### 4.2 Timbrado y numeración

- **Timbrado:** 8 dígitos. Especificación del registro, campo 7 («NUM 8»), y Manual Técnico, C004 dNumTim «N 8 … Debe coincidir con la estructura de timbrado». Confianza: oficial leída.
- **Número:** «Formato ###-###-#######» (especificación, campo 8) y «los comprobantes timbrados deben contener 13 dígitos» (presentación «Opción Importar»). La guía de 2026 de consulta como receptor dice «formato NNN-NNN-NNNNNNN (establecimiento, punto de expedición y numero de comprobante)». Confianza: oficial leída.
- **En electrónicos (Manual Técnico):** C005 establecimiento, 3, «Completar con 0 (cero) a la izquierda»; C006 punto de expedición, 3; C007 número, 7, «Debe empezar con 1 (uno) para un nuevo timbrado»; agotado el 9999999 se usa C010 dSerieNum (2 caracteres).

### 4.3 CDC

- **Manual Técnico v150, sección 10.1** (tabla «Conformación del CDC», leída en la imagen de la página 56):

| Campo | ID | Long. |
|---|---|---|
| Tipo de documento | C002 iTiDE | 2 |
| RUC del emisor (ceros a la izquierda hasta 8) | D101 dRucEm | 8 |
| DV del emisor | D102 dDVEmi | 1 |
| Establecimiento | C005 dEst | 3 |
| Punto de expedición | C006 dPunExp | 3 |
| Número de documento | C007 dNumDoc | 7 |
| Tipo de contribuyente | D103 iTipCont | 1 |
| Fecha de emisión AAAAMMDD | D002 dFeEmiDE | 8 |
| Tipo de emisión | B002 iTipEmi | 1 |
| Código de seguridad | B004 dCodSeg | 9 |
| Dígito verificador (módulo 11) | A003 dDVId | 1 |
| **Total** | | **44** |

- Ejemplo oficial: factura (01), RUC 44444401, DV 7, 001-001-0014528, tipo de contribuyente 2, 25-01-2017, emisión 1, código 587326098, DV 8. KuDE: «0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988».
- Código de seguridad (10.3): 9 dígitos aleatorios, no secuenciales, distinto del número del documento.

### 4.4 Dígito verificador del RUC

- **Proyecto de facturación (solo lectura):** `~/Escritorio/facturacion-sifen-zestia/packages/contracts/src/sifen.ts`, función `setCheckDigit`:

```ts
export function setCheckDigit(digits: string): number {
  if (!/^\d+$/.test(digits)) throw new Error('El dígito verificador se calcula sobre dígitos');
  let total = 0;
  let weight = 2;
  for (let i = digits.length - 1; i >= 0; i--) {
    total += Number(digits[i]) * weight;
    weight = weight === 11 ? 2 : weight + 1;
  }
  const rest = total % 11;
  return rest > 1 ? 11 - rest : 0;
}
```

  - Su prueba (`packages/contracts/src/sifen.test.ts`) usa el RUC del Manual: `setCheckDigit('44444401')` → 7. `buildCdc` en `FACTURACION_ELECTRONICA_SIFEN.md` arma el CDC con el mismo algoritmo.
- **Fuente oficial:** el Manual Técnico, sección 10.2, solo dice: «Para el cálculo del dígito verificador del código de control se debe utilizar el módulo 11». Remite a `https://www.set.gov.py/portal/PARAGUAY-SET/detail?content-id=/repository/collaboration/sites/PARAGUAY-SET/documents/herramientas/digito-verificador.pdf`, que hoy redirige a la portada de la DNIT. No encontré ese documento en dnit.gov.py.
- **Verificación empírica:** reimplementé el algoritmo y lo probé contra los ejemplos oficiales del Manual: RUC 44444401 → 7, CDC del ejemplo → 8, y los 2 CDC de 44 dígitos que aparecen en el texto del Manual → todos coinciden.
- **Confianza:** «módulo 11» oficial leída; los pesos (2 a 11 desde la derecha) y la regla del resto (0 si el resto es 0 o 1), **secundaria** (código del proyecto de facturación y sitios de terceros como yo-facturo.com), consistente con los ejemplos oficiales. Ver D-F4-10.

---

## 5. Feriados nacionales y días inhábiles

### 5.1 Ley N° 7544/2025

- **Fuente:** BACN, <https://www.bacn.gov.py/leyes-paraguayas/12908/ley-n-7544-2025> (PDF: <https://www.bacn.gov.py/descarga/12908/2025_7544.pdf>).
- **Fechas:** promulgación y publicación 03-09-2025 (ficha BACN). La Gaceta Oficial N° 200 del 3 de setiembre de 2025 la publica (copia alojada por un diario: <https://grupovierci.brightspotcdn.com/51/1e/94457a28442c9bc15eb7a0e9dd03/ley-7544-feriados-fijos-y-moviles-2025.pdf>).
- **Confianza:** oficial leída (texto de la BACN).
- **Deroga** las Leyes 08/1990, 715/1995, 1601/2000, 1723/2001 y 4531/2011 (art. 9°).

**Art. 1°:** «Determínase como días Feriados Nacionales de la República del Paraguay de cada año, además de los días domingos, los siguientes»:

- 1 de enero, Año Nuevo.
- 1 de marzo, Día de los Héroes de la Patria.
- «Jueves y Viernes, Semana Santa.»
- 1 de mayo, Día de los Trabajadores.
- 14 y 15 de mayo, Día de la Independencia Nacional.
- 12 de junio, Día de la Paz del Chaco.
- 20 de junio, Día de la Jura de la Constitución Nacional.
- 15 de agosto, Día de la Fundación de Asunción y, eventualmente, de la Transmisión del Mando Presidencial.
- 29 de setiembre, Día de la Batalla de Boquerón.
- 8 de diciembre, Día de la Virgen de Caacupé.
- 25 de diciembre, Navidad.

**Art. 2°: móviles:** 1 de marzo, 12 de junio, 20 de junio y 29 de setiembre. «Los demás feriados mencionados en el artículo 1° de la presente ley no serán móviles».

**Art. 3°:** el Poder Ejecutivo puede trasladarlos cada año, por decreto, «a los días lunes, anterior o siguiente al feriado que se traslada».

**Art. 4°:** puede fijar cada año, por decreto, «hasta un máximo de tres días adicionales de Feriados Nacionales», con «los mismos efectos que los demás Feriados Nacionales».

**Art. 7°: asuetos:** «Los asuetos serán considerados días hábiles y no tendrán los efectos de los Feriados Nacionales, salvo cuando fenezca algún plazo el día del asueto, el cual se trasladará al día siguiente hábil para su vencimiento.»

**Art. 8°:** los feriados no afectan la labor de los funcionarios de «comercio exterior y percepción de tributos». Ver D-F4-12.

**Semana Santa:** la ley no da fechas. Las calculé con el algoritmo gregoriano de Pascua: 2026, jueves 2 y viernes 3 de abril (coincide con el listado de BVPASA); 2027, 25 y 26 de marzo; 2028, 13 y 14 de abril.

### 5.2 Traslados y feriados adicionales conocidos

| Año | Fecha original | Pasa a | Norma | Confianza |
|---|---|---|---|---|
| 2025 | — | 05-09-2025 (adicional, clasificación al Mundial) | Decreto sin número visto | secundaria (hoy.com.py, 06-09-2025) |
| 2025 | — | 26-12-2025 (adicional, Navidad) | Decreto N° 5040/2025 | secundaria (copia del decreto en grupovierci) |
| 2026 | dom 01-03 | lun 02-03 | Decreto sin número visto | secundaria (ABC, BVPASA) |
| 2026 | sáb 20-06 | lun 22-06 | Decreto N° 6215/2026, art. 1° | secundaria (copia del decreto en grupovierci) |
| 2026 | — | mar 30-06-2026 (adicional, Mundial) | Decreto N° 6280/2026 | secundaria; el Poder Judicial se adhirió (pj.gov.py) |
| 2026 | mar 29-09 | lun 28-09 | Decreto N° 6601/2026 (20-08-2026) | secundaria (La Nación, ABC) |
| 2026 | vie 12-06 | sin traslado | — | secundaria (BVPASA) |
| 2027 | — | — | **ninguno publicado al 24-11-2026** | no encontrada |

- Listado secundario de 2026: Bolsa de Valores de Asunción, <https://www.bolsadevalores.com.py/wp-content/uploads/2026/01/Listado-de-Feriados-2026.pdf>.
- **No encontré los decretos en sitios oficiales** (Gaceta Oficial o Presidencia). Las copias de los Decretos 5040 y 6215 son escaneos alojados por un diario.
- El feriado del 30-06-2026 se decretó la víspera. La aplicación tiene que permitir agregar feriados tarde.

### 5.3 ¿La DNIT publica su propio calendario de días inhábiles?

- **No encontrado.** No hallé en dnit.gov.py un calendario de feriados o días inhábiles. La DNIT publica resoluciones de traslado excepcional (RG DNIT 48/2026, 55/2026 y 60/2026) y la prensa difunde cronogramas mensuales.
- **Regla de traslado (RG 38/2020, art. 3°, ya en `TRIBUTACION_PY.md` §3.1):** el vencimiento en día inhábil pasa al primer día hábil siguiente.
- **¿El sábado es inhábil?** La Ley 7544 solo habla de domingos. Indicios oficiales:
  - **RG DNIT 60/2026** (09-11-2026), art. 1°: lista como vencimiento «conforme RG n.° 38/2020» de la terminación 0 el **9 de noviembre** (lunes), aunque su día fijo es el 7 (sábado), y de la terminación 4 el 16 (lunes) en vez del 15 (domingo). Trata el sábado como inhábil. Fuente: <https://www.dnit.gov.py/documents/20123/2664257/RG+60+-+2026_firmado.pdf/cadc1f8b-47cd-7ec3-491a-42a0feb6265d?t=1794273017967>. Oficial leída.
  - **RG DNIT 48/2026** (23-03-2026): corre al 24-03-2026 los vencimientos de las terminaciones 7 (listado como «21 de marzo de 2026», sábado) y 8 («23 de marzo de 2026») por la caída de Marangatu del 23 de marzo; y la DJI de la terminación 7 («22 de marzo», domingo). Aquí lista la fecha fija sin correrla. Fuente: <https://www.dnit.gov.py/web/portal-institucional/w/resoluci%C3%B3n-general-dnit-n%C2%B0-48/26>. Oficial leída.
  - Ver D-F4-11.

---

## 6. Contradicciones y dudas para el contador

**D-F4-1. ¿Coma o punto y coma en el CSV?**

- La especificación dice «.CSV (delimitado por comas)», pero su propio ejemplo usa `;`.
- Excel en español guarda los «CSV» con punto y coma.
- **¿Cuál acepta Marangatu hoy?** Probar con un archivo de una línea antes de usar la exportación. Mientras tanto, el TXT con tabulaciones evita la duda.

**D-F4-2. Columna «IMPUTA AL IRE» para una EAS en el IRE General.**

- La especificación dice «IMPUTA IRE» sin distinguir régimen.
- Las guías de la DNIT de 2022 y 2026 dicen que esa imputación es «aplicable únicamente para el IRE SIMPLE» y que, para el IRE General, se marca «No imputar».
- **Si la EAS está en el IRE General, ¿las compras van con IVA = S, IRE = N?** ¿Y las compras sin IVA que solo sirven para el IRE (por ejemplo, exentas), se registran con «No imputar» o no se registran?
- Se cruza con D-1 y D-2 de `TRIBUTACION_PY.md` (régimen del IRE de la EAS).

**D-F4-3. Importar después de confirmar el talón.**

- La guía de 2021 dice que, confirmado el talón, solo queda la carga manual.
- El art. 9° de la RG 90/2021 (texto RG DNIT 12/2024) permite importar después del talón.
- Asumo que rige la resolución. **¿Lo confirma en la práctica?**

**D-F4-4. Notas de crédito: ¿en ventas o en compras?**

- La guía de registro manual: las NC **recibidas** van en VENTAS y las **emitidas** en COMPRAS.
- Es contrario a la intuición (una NC recibida de un proveedor reduce el crédito de una compra). Coincide con el Formulario 120: la NC recibida reduce el crédito como «débito» (Rubro 1, inc. h a j: «devoluciones realizadas, descuentos obtenidos») y la emitida da «crédito» (Rubro 3, inc. e).
- **¿Es así como lo registra usted?** Define cómo la app arma el archivo y el borrador.

**D-F4-5. Plazo para computar el crédito de comprobantes de meses anteriores.**

- La ley (art. 88) habla de compras «realizadas en el mes». No encontré una norma que permita, o prohíba, computar una factura atrasada en un mes posterior, ni hasta cuándo.
- **¿Qué criterio usa la DNIT?** ¿Hay que rectificar la DJ del mes de la factura?

**D-F4-6. Casillas del Formulario 120 para la EAS.**

- **¿La EAS usa la casilla 151/157 (5% «otros bienes y servicios») o la 150/156 (productos agrícolas)?** Depende de la actividad.
- **¿Las compras se cargan como «directas» (32/35/38) o «indistintas» (33/36/39)?** Si la EAS solo tiene operaciones gravadas, ¿todo es directo?
- **¿Las retenciones (casilla 52) las trae Marangatu** («Ver retenciones recibidas») o las carga el contribuyente?

**D-F4-7. Redondeo.**

- El formulario va «sin céntimos». El registro pide montos enteros con IVA incluido.
- **¿El IVA del mes se calcula sobre la suma de las bases, o se suma el IVA redondeado de cada comprobante?** La diferencia es de pocos guaraníes, pero puede no cuadrar con lo que calcula Marangatu.

**D-F4-8. Tipo de cambio.** El Decreto 3107, art. 13, permite «comprador o vendedor» del BCP del día anterior, o la cotización del comprobante. **¿Cuál se usa para compras y cuál para ventas?**

**D-F4-9. Compras no deducibles.** Fuera de los requisitos del art. 89, **¿hay una lista de gastos cuyo IVA nunca es crédito para una persona jurídica** (por ejemplo, gastos personales del accionista, vehículos)? No la encontré para el IVA.

**D-F4-10. Dígito verificador del RUC.**

- El algoritmo del proyecto de facturación coincide con todos los ejemplos oficiales del Manual Técnico, pero no encontré el documento oficial que lo describe.
- Sitios de terceros dicen que hay RUC antiguos que terminan en letra y que la letra se reemplaza por su código ASCII. La implementación actual rechaza letras.
- **¿Hace falta aceptar RUC con letra** en proveedores o clientes?

**D-F4-11. ¿Los sábados son inhábiles para la DNIT?**

- La RG DNIT 60/2026 los trata como inhábiles (pasa del sábado 7 al lunes 9). La RG DNIT 48/2026 lista un sábado como fecha de vencimiento sin correrla.
- **¿Un vencimiento que cae en sábado pasa al lunes?**

**D-F4-12. Feriados y vencimientos.**

- La Ley 7544, art. 8°, mantiene trabajando a los funcionarios de «percepción de tributos» en los feriados.
- **¿Un feriado nacional corre los vencimientos de la DNIT** (como dice la RG 38/2020 para el «día inhábil»), aunque el personal de recaudación trabaje? ¿Y un asueto? (el art. 7° dice que sí corre el plazo).
- ¿Los bancos cobran impuestos ese día?

**D-F4-13. Imputación automática de las ventas electrónicas.**

- La RG DNIT 12/2024 permite que el facturador informe la obligación (211) al emitir, y Marangatu imputa solo.
- **¿Conviene que el proyecto de facturación informe siempre el código de la obligación?** ¿Qué código o códigos corresponden a la EAS?

**D-F4-14. Prorrateo para una EAS nueva.**

- El Decreto 3107, art. 18, da un período transitorio de 5 meses a «quien se constituya en contribuyente desde la vigencia del presente Decreto».
- **¿Aplica a una EAS inscripta años después?** Si solo tiene operaciones gravadas, no cambia nada.

---

## 7. Lo que no se pudo verificar

| Tema | Situación |
|---|---|
| **Algoritmo del DV publicado por la DNIT** | El Manual Técnico remite a un PDF de set.gov.py que ya no existe. Solo «módulo 11» es oficial; los pesos y la regla del resto salen del proyecto de facturación y de terceros, probados contra ejemplos oficiales. |
| **Decreto 6539/2005** (reglamento de timbrado) y sus modificaciones | No lo encontré en dnit.gov.py ni lo leí. Contiene los requisitos formales de facturas, boletas y tickets preimpresos. |
| **Estructura del archivo de imputación** que genera Marangatu para electrónicos | Solo la describe la guía; no hay especificación publicada. |
| **Plazo para computar crédito de meses anteriores** | No encontrado (D-F4-5). |
| **Regla de redondeo del IVA** | No encontrada (D-F4-7). |
| **Notas técnicas del MT v150** (27) | No las revisé. Pueden cambiar tipos de documento, fórmulas o campos. |
| **Versión del Formulario 120 dentro de Marangatu** | Solo vi la página web (v4). No pude ver el formulario dentro de Marangatu. |
| **Textos de RG 131/2023 y RG DNIT 07/2024** | Solo títulos o resúmenes de la DNIT. No parecen tocar el formato. |
| **Fecha de publicación de la RG DNIT 12/2024** | Necesaria para saber desde cuándo rige la imputación automática. |
| **Fecha exacta del Decreto 872/2023** | El texto extraído no deja leer el día y el mes. |
| **Decretos de feriados de 2025 y 2026 en sitios oficiales** | Solo copias de prensa (5040, 6215) o noticias (6280, 6601, traslado del 1 de marzo). |
| **Feriados y traslados de 2027** | Ningún decreto publicado al 24-11-2026. |
| **Calendario de días inhábiles de la DNIT** | No encontrado. |
| **Si los sábados son inhábiles** | Indicios contradictorios (D-F4-11). |
| **Modificaciones del Decreto 3107/2019** | Solo vi por título los Decretos 8175/2022 y 5584/2021. No hice un rastreo completo. |

---

## 8. Índice de fuentes

Todas abiertas el 2026-11-24.

| Norma o documento | Fecha | URL |
|---|---|---|
| Especificación técnica de importación, v1 | 06-2021 | <https://www.dnit.gov.py/documents/20123/203596/Especificaciones+T%C3%A9cnicas+para+registro+de+comprobantes+en+Marangatu.pdf/fca12623-f680-a630-e624-8c825db31b7d?t=1684176028356> |
| Ídem, otra URL (mismo PDF) | 06-2021 | <https://www.dnit.gov.py/documents/44828/0/Especificaciones+T%C3%A9cnicas+para+registro+de+comprobantes+en+Marangatu.pdf/fd50732c-4232-750a-b253-5b14843cdccb?t=1682430005384.pdf> |
| Modelo de planilla XLSX | 2021, mod. 2022 | <https://www.dnit.gov.py/documents/44828/0/Modelo+de+Planilla+para+Registro+de+Comprobantes+en+Marangatu.xlsx/3012e5a2-57d7-86b4-db8b-6212d39c81f3?t=1682441199202> |
| Página «Registro de Comprobantes» (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/registro-de-comprobantes> |
| Guía de importación | 07-2021 | <https://www.dnit.gov.py/documents/20123/203596/Guia+Paso+a+Paso+-+Registro+de+comprobantes+a+trav%C3%A9s+de+Importaci%C3%B3n.pdf/c0d1917c-8952-79e5-9e72-a64777916fa8?t=1684165228356.pdf> |
| Presentación «Opción Importar» | 08-2021 | <https://www.dnit.gov.py/documents/47797/47809/Registro+de+comprobantes+en+el+Marangatu+-+Opci%C3%B3n+Importar.pdf/67b5cd0a-b20c-a25a-d368-c4df072ee84d?t=1681834631316> |
| Guía de registro manual | 09-2022 | <https://www.dnit.gov.py/documents/44828/0/Guia+Paso+a+Paso-+Registro+manual+de+comprobantes+a+trav%C3%A9s+del+sistema+Marangatu.pdf/5dc720af-2425-187a-ff92-0bbfbbfbb578?t=1682441119323> |
| Guía «Cómo obtener comprobantes electrónicos y virtuales» | 05-2026 | <https://www.dnit.gov.py/documents/20123/437212/Gu%C3%ADa+Paso+a+Paso+-+C%C3%B3mo+obtener+comprobantes+electr%C3%B3nicos+y+virtuales.pdf/31a43846-a0e3-9ad9-7003-bc19bc5bc92d?t=1778092596059> |
| Guía «Consultar comprobantes declarados como receptor» | 08-2026 | <https://www.dnit.gov.py/documents/20123/437212/Gu%C3%ADa+Paso+a+Paso+-+Consultar+Comprobantes+Declarados+como+Receptor.pdf/a8235dd9-bf2c-fa67-665a-b776150a251b?t=1785787535836> |
| RG 94/2021 | 06-08-2021 | <https://www.dnit.gov.py/documents/20123/199761/RG_+94+Medidas+administrativas+RG+N%C2%B0+90.pdf/05c1be35-52d5-9ade-5cdf-d08d83854851?t=1682697830526> |
| RG 104/2021 | 09-12-2021 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-104-21-1> |
| Res. DNIT 730/2023 | 29-12-2023 | <https://www.dnit.gov.py/documents/20123/267216/29_12+Resol+DNIT+N%C2%B0+730_23+RG+90.pdf/4d63bcf9-8fb3-e29d-81a3-19bcd0433863?t=1703894983451> |
| RG 131/2023 (solo título y noticia) | 06-06-2023 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-131-23-> |
| RG DNIT 12/2024 | 31-05-2024 | <https://www.dnit.gov.py/documents/20123/796215/Res.+General+DNIT+N%C2%B0+12_2024.pdf/06555b22-920e-f0ac-74d9-f5b6aa50329f?t=1717201434815> |
| RG 33/2020 | 07-01-2020 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-33-20> |
| Formulario 120 v4 | 2020 | <https://www.dnit.gov.py/documents/44828/89027/Formulario+N%C2%B0+120+IVA+Versi%C3%B3n+4.pdf/ced4ba56-a201-5126-29ea-c233d01ed6a4?t=1680627132264> |
| Instructivo del Formulario 120 v4 | 04-01-2020 | <https://www.dnit.gov.py/documents/47797/47809/Instructivo+del+Formulario+N%C2%B0+120+IVA+Versi%C3%B3n+4.pdf/63799cd8-6212-3c22-779b-51b2f97a136b?t=1680624028092.pdf> |
| Formularios e instructivos (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/formularios-instructivos> |
| Ley 6380/2019, arts. 85 a 96 | 25-09-2019 | <https://www.dnit.gov.py/web/portal-institucional/w/d-ley-n-6380-19> |
| Decreto 3107/2019 (IVA) | 19-12-2019 | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3107-19.pdf/d723b322-e502-e34b-18bc-3df7bfd0f785?t=1681423809891> |
| Decreto 3107/2019, transcripción (solo para ubicar artículos) | — | <https://impuestospy.com/impuestos/decreto-n-3-107-2019/> |
| Decretos (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/decretos> |
| Cartilla IVA | 06-08-2024 | <https://www.dnit.gov.py/documents/20123/224724/IVA+Cartilla+6.08.24.pdf/c23f9d9f-8747-815f-28c2-4d0c1fa9e6d6?t=1722964877639.pdf> |
| Decreto 872/2023 (SIFEN) | 2023 | <https://www.dnit.gov.py/documents/20123/559197/Decreto+N%C2%B0+872-23.pdf/c86edb49-54e2-367c-8626-13390cea60b1?t=1704212315637> |
| Manual Técnico SIFEN v150 | 09-2019 | <https://www.dnit.gov.py/documents/20123/420592/Manual+T%C3%A9cnico+Versi%C3%B3n+150.pdf> |
| Documentación técnica e-Kuatia | — | <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica> |
| Ley 7544/2025 (BACN) | 03-09-2025 | <https://www.bacn.gov.py/leyes-paraguayas/12908/ley-n-7544-2025> |
| Ley 7544/2025, Gaceta Oficial N° 200 (copia de prensa) | 03-09-2025 | <https://grupovierci.brightspotcdn.com/51/1e/94457a28442c9bc15eb7a0e9dd03/ley-7544-feriados-fijos-y-moviles-2025.pdf> |
| Decreto 5040/2025 (copia de prensa) | 12-2025 | <https://grupovierci.brightspotcdn.com/23/0b/b887cf2b40b0ad71ec3245a1e6c5/decreto5040.PDF> |
| Decreto 6215/2026 (copia de prensa) | 2026 | <https://grupovierci.brightspotcdn.com/39/cd/808fd5cf4b2a91e60a5b066dcbd0/decreto-6215-traslado-feriado-20-al-22-de-junio.pdf> |
| Feriado del 30-06-2026 (Poder Judicial) | 30-06-2026 | <https://www.pj.gov.py/notas/30118-poder-judicial-se-adhiere-al-feriado-nacional-del-martes-30-de-junio> |
| Traslado del 29-09-2026 (La Nación) | 24-08-2026 | <https://www.lanacion.com.py/politica/2026/08/24/batalla-de-boqueron-ultimo-feriado-movil-se-traslada-al-28-de-setiembre/> |
| Feriados 2026 (ABC) | 2025-11-13, actualizada | <https://www.abc.com.py/nacionales/2025/11/13/estos-son-los-feriados-para-el-2026/> |
| Listado de feriados 2026 (BVPASA) | 01-2026 | <https://www.bolsadevalores.com.py/wp-content/uploads/2026/01/Listado-de-Feriados-2026.pdf> |
| Feriado adicional de setiembre de 2025 (Hoy) | 06-09-2025 | <https://www.hoy.com.py/nacionales/2025/09/06/pena-cuenta-lo-que-le-paso-por-la-cabeza-cuando-decreto-feriado-por-la-albirroja> |
| RG DNIT 48/2026 | 23-03-2026 | <https://www.dnit.gov.py/web/portal-institucional/w/resoluci%C3%B3n-general-dnit-n%C2%B0-48/26> |
| RG DNIT 60/2026 | 09-11-2026 | <https://www.dnit.gov.py/documents/20123/2664257/RG+60+-+2026_firmado.pdf/cadc1f8b-47cd-7ec3-491a-42a0feb6265d?t=1794273017967> |
| Proyecto de facturación (local, solo lectura) | — | `~/Escritorio/facturacion-sifen-zestia/packages/contracts/src/sifen.ts` |
