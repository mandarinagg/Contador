# Investigación tributaria: persona física con RUC

> **Estado: investigación. Ninguna regla está verificada.**
> Lo armó un asistente de IA leyendo fuentes oficiales el **2026-11-25**, después de que el propietario decidiera que la aplicación también atienda a **personas físicas** y a varias organizaciones por instalación. No hay contador (D-118): verifica CONTADOR AI contra la fuente oficial, con la aprobación del propietario (D-120). Todas las reglas derivadas quedan en `pending` (ver `tax_rules_candidatas.yaml`, sección «PERSONA FÍSICA»).
> No es asesoramiento tributario. Completa a [`TRIBUTACION_PY.md`](TRIBUTACION_PY.md) (§2.6) y a [`TRIBUTACION_FASE4.md`](TRIBUTACION_FASE4.md): lo que ya está ahí no se repite.

**Fecha de consulta de todas las fuentes:** 2026-11-25. **Niveles de confianza:** los de `TRIBUTACION_PY.md`.

**Documentos escaneados:** los Decretos 3184/2019, 7047/2022, 4661/2020 y 3182/2019 son escaneos con una capa de texto OCR. Los leí desde esa capa. Donde el OCR rompe una palabra, la cito igual que el resto del artículo, que sí se lee bien. **No se leen bien:** el día y el mes de los Decretos 7047/2022 y 4661/2020. La fecha del Decreto 3184 (30-12-2019) sale de la RG 69/2020, art. 1°, y coincide con la fecha de creación del PDF.

---

## Índice

1. [RUC de la persona física y dígito verificador](#1-ruc-de-la-persona-física-y-dígito-verificador)
2. [Empresa unipersonal frente a la persona física](#2-empresa-unipersonal-frente-a-la-persona-física)
3. [IVA de la persona física que presta servicios](#3-iva-de-la-persona-física-que-presta-servicios)
4. [IRP-RSP: servicios personales (obligación 715)](#4-irp-rsp-servicios-personales-obligación-715)
5. [IRP-RGC: rentas y ganancias del capital (obligación 716)](#5-irp-rgc-rentas-y-ganancias-del-capital-obligación-716)
6. [IRE RESIMPLE (obligación 702)](#6-ire-resimple-obligación-702)
7. [Libros, registro de comprobantes y registro anual 956](#7-libros-registro-de-comprobantes-y-registro-anual-956)
8. [Verificado, no verificado y no se pudo leer](#8-verificado-no-verificado-y-no-se-pudo-leer)
9. [Dudas abiertas (D-PF)](#9-dudas-abiertas-d-pf)
10. [Índice de fuentes](#10-índice-de-fuentes)

---

## 1. RUC de la persona física y dígito verificador

**RG N° 79/2021** (20-01-2021), art. 6° con el texto de la **RG N° 133/2023** (14-07-2023), art. 1°. Confianza: oficial leída.

- «El Identificador RUC será numérico». Para las personas físicas paraguayas y las extranjeras con residencia que tengan cédula paraguaya, «será el que corresponda al número de dicho documento» (inc. a).
- Las personas físicas extranjeras con constancia de solicitud de refugio reciben un número de la serie 50.000.000 (inc. b).
- «Personas Jurídicas, […] EAS, Empresas Individuales de Responsabilidad Limitada (EIRL) y sucesiones indivisas»: serie 80.000.000 (inc. c).
- **Art. 7°:** «El DV no forma parte del Identificador, pero deberá escribirse o digitarse al final del mismo, separado por un guión». Lo asigna la SET al aprobar la inscripción.
- La **RG DNIT N° 30/2025** cita la Ley 2421/2004, art. 37: el RUC de las personas físicas «corresponderá con el número de su cédula de identidad paraguaya». La ley no la leí (oficial citada por terceros).

**Conclusión:** RUC de la persona física = número de cédula + «-» + DV. La terminación que usa el calendario perpetuo es el último dígito de la cédula, sin el DV.

**Algoritmo del DV: hay una publicación oficial.** La DNIT publica «Cálculo del Dígito Verificador» en su página «Otras herramientas». Es un PDF de 3 páginas con la misma función en PL/SQL, Visual Basic y C, creado el 20-11-2013 según sus metadatos.

- Fuente: <https://www.dnit.gov.py/documents/20123/224893/D%C3%ADgito+Verificador.pdf/fb9f86c8-245d-9dad-2dc1-ac3b3dc307a7?t=1683354226554.pdf>, enlazado desde <https://www.dnit.gov.py/web/portal-institucional/otras-herramientas>. Confianza: oficial leída.
- Función `Pa_Calcular_Dv_11_A(p_numero, p_basemax DEFAULT 11)`:
  1. Todo carácter que no sea un dígito del 0 al 9 se reemplaza por su código ASCII, en mayúscula: «Cambia la ultima letra por ascii en caso que la cedula termine en letra».
  2. De derecha a izquierda, cada dígito se multiplica por un peso `k` que empieza en 2, sube de a uno y vuelve a 2 cuando pasa de `basemax` (11).
  3. `resto = total MOD 11`; «IF v_resto > 1 THEN v_digit := 11 - v_resto; ELSE v_Digit := 0».
- **Coincide** con la implementación de la regla `RUC-DV-MODULO11` (pesos de 2 a 11, cíclicos desde la derecha; 0 si el resto es 0 o 1).
- **Resuelve el caso de los RUC con letra** (D-F4-10): la letra se reemplaza por su código ASCII. Por ejemplo, «A» pasa a «65».
- La regla `RUC-DV-MODULO11` sigue en `confidence: secundaria`: no la modifiqué. Pasarla a versión 2 con esta fuente es la duda D-PF-14.

---

## 2. Empresa unipersonal frente a la persona física

**Ley 6380/2019** (texto en la DNIT). Confianza: oficial leída.

- **Art. 2°, num. 1:** son contribuyentes del IRE «Las Empresas Unipersonales».
- **Art. 3°:** la empresa unipersonal es «toda unidad productiva perteneciente a una persona física», organizada y habitual, con preponderancia del capital. La ley enumera 17 actividades: comercio, transporte, construcción, restaurantes, reparación, etc.
  - Si los bienes de la persona física «estén registrados en la contabilidad de la empresa unipersonal», su enajenación, cesión y arrendamiento quedan en el IRE.
  - Para la ley, la EIRL es empresa unipersonal.
- **Art. 1°:** el IRE excluye «aquellas rentas gravadas por el IRP». Los servicios personales y profesionales (art. 62) van al IRP-RSP, no al IRE.

**¿Mismo RUC?** Lo que se lee en la norma:

- La RG 79/2021, art. 6°, da una serie propia (80.000.000) a la EIRL, pero **no menciona a la empresa unipersonal**.
- La guía DNIT de inscripción de personas físicas (2022) muestra que en la misma inscripción se eligen las obligaciones y el mes de cierre («Abril/Junio/Diciembre»).

**Inferencia:** la empresa unipersonal que no es EIRL usa el RUC de su dueño. Las obligaciones IRE (700, 701 o 702) se suman a las del IRP (715, 716) y del IVA (211) en ese mismo RUC. No encontré una norma que lo diga con todas las letras (D-PF-1).

**Cómo conviven el IRE de la unipersonal y el IRP del dueño:**

- **Ley, art. 53:** el IRP se liquida por separado por categoría; no se pasan gastos ni ganancias de una a otra.
- **Ley, art. 68, num. 5:** en el IRP-RSP no son deducibles «Los egresos realizados por las personas físicas en su condición de propietarios de empresas unipersonales».
- **Ley, art. 26, último párrafo:** la unipersonal que liquida por el SIMPLE «no será contribuyente del IDU».
- **Decreto 3184, art. 18:** «Los rendimientos que perciba el dueño de una empresa unipersonal que liquide el IRE por el SIMPLE o RESIMPLE, no estarán alcanzados por el IRP».
- **IRE General:** la utilidad que pasa al dueño paga IDU (art. 40: «dueños»). Para el residente persona física es «pago único y definitivo» (art. 41).
- **Inmuebles:**
  - La ley, art. 30, manda que la compra y venta de inmuebles del dueño de la unipersonal siga las reglas del IRP, y el art. 31 hace lo mismo con su arrendamiento.
  - El Decreto 3184, art. 13, dice: «Cuando dichos bienes formen parte del activo de una empresa unipersonal estarán afectados a las disposiciones relativas al IRE RG».
  - La ley (art. 3°) y el decreto coinciden en este caso, pero el art. 31 parece decir lo contrario (D-PF-2).

---

## 3. IVA de la persona física que presta servicios

**Ley 6380/2019.** Confianza: oficial leída.

- **Art. 80, num. 2:** el IVA grava «La prestación de servicios, excluidos los de carácter personal que se presten en relación de dependencia».
- **Art. 81, num. 2, inc. f):** «El ejercicio de profesiones, de artes o de oficios» es servicio.
- **Art. 82, num. 1:** son contribuyentes las personas físicas:
  - «a) Por la prestación de servicios personales o profesionales que no estén en relación de dependencia y por el arrendamiento de inmuebles.»
  - «b) Por la explotación de una empresa unipersonal […]».
- **Umbral:** el art. 82 **no fija ningún monto mínimo** (D-PF-3). El tope de ₲ 80.000.000 del IRP-RSP es solo del IRP.
- **Art. 88:** quien presta servicios personales puede deducir «hasta el 30%» del IVA crédito por la compra de autovehículos.
- **Art. 27, último párrafo:** la unipersonal del RESIMPLE «no será contribuyente del IVA».
- **Cartilla IVA DNIT (06-08-2024):** repite el art. 82 y lista los rubros de IVA crédito admitidos a la persona física que presta servicios. Entre ellos, alimentos «hasta el treinta por ciento (30 %)», salud personal, capacitación, oficina y vestimenta profesional. Cita el **Decreto 8175/2022**, art. 1°, que no leí (D-PF-4).
- **Efecto en la aplicación:** la persona física con IVA usa la misma obligación 211 y el mismo Formulario 120 que la EAS. Las reglas `IVA-*` ya cargadas se aplican. Lo que cambia es qué compras dan crédito (Decreto 8175/2022).

---

## 4. IRP-RSP: servicios personales (obligación 715)

### 4.1 Ley 6380/2019 (Título III)

- **Art. 52:** el ejercicio «coincidirá con el año civil». Ingresos por lo percibido; gastos por lo «efectivamente realizado».
- **Art. 62:** queda alcanzada la persona física cuyos ingresos brutos gravados del año, desde el 1 de enero, sean «superior a G. 80.000.000».
  - El primer año liquida sobre todos los ingresos, menos los egresos realizados «a partir del día siguiente en que resulte alcanzada».
  - Los años siguientes, desde el 1 de enero.
- **Art. 63:** de la renta bruta se excluyen los aportes del trabajador a la jubilación o la seguridad social y el seguro médico pagado directamente por el empleador.
- **Art. 64, deducibles:**
  - Egresos de la actividad, si están documentados y son reales; incluye muebles, equipos y la oficina.
  - Egresos personales y de familiares a cargo realizados en el país: alimentación, vestimenta, alquiler y mantenimiento de la vivienda, mobiliario y electrodomésticos, esparcimiento en el país.
  - Salud y educación, en el país y en el exterior.
  - Un autovehículo cada 3 años.
  - Vivienda, según el art. 66.
  - Aporte patronal a la seguridad social y aportes a un sistema privado de seguridad social.
  - Donaciones, hasta el límite del Poder Ejecutivo.
  - **Condición:** el egreso tiene que estar pagado con ingresos gravados del año, con préstamos de entidades o con el remanente de los 5 ejercicios anteriores.
  - **Sin arrastre de pérdidas**, salvo la vivienda.
- **Art. 65:** familiares a cargo. El cónyuge, si no es contribuyente del IRE, del IDU ni del IRP. Hijos y hermanos menores. Hijos estudiantes, padres, abuelos y suegros con ingresos de hasta ₲ 30.000.000. Personas con derecho a alimentos.
- **Art. 66:** vivienda, una cada 5 años. Al contado, la pérdida se compensa hasta el 20% de la renta neta de los 5 ejercicios siguientes.
- **Art. 68, no deducibles:** el propio impuesto, multas, egresos pagados con ingresos no gravados, liberalidades, los egresos del dueño de una unipersonal (§2) y el IVA usado como crédito o como gasto en otro impuesto.
- **Art. 69, tasas progresivas por tramo:**

| Renta neta | Tasa |
|---|---|
| Hasta ₲ 50.000.000 | 8% |
| De ₲ 50.000.001 a ₲ 150.000.000 | 9% |
| Desde ₲ 150.000.001 | 10% |

- **Art. 69, último párrafo:** con ingresos de hasta ₲ 80.000.000 el contribuyente «deberá cumplir las obligaciones formales […] pero no estará obligado al pago del impuesto».
- **Anticipos:** la ley no prevé anticipos del IRP. El art. 24 es solo del IRE y el Título III no tiene un equivalente. Lectura propia.

### 4.2 Decreto N° 3184/2019 (reglamento del IRP)

Oficial leída (escaneo con OCR). Modificado por el **Decreto 7047/2022** (arts. 9°, 31, 40 y 54) y el **Decreto 4661/2020** (arts. 16 y 50).

- **Art. 55:** el esparcimiento en el exterior solo es deducible si se compró a una agencia de viajes radicada en el país. La RG 69/2020, art. 26, lo excluye si se pagó en el exterior.
- **Art. 56:** salud y educación en el exterior se deducen si se pagaron con tarjeta de una entidad del país, con transferencia o giro, o en efectivo con legalización consular.
- **Art. 57:** cuotas, aportes y donaciones, «hasta un monto que no supere en conjunto el cinco por ciento (5%) de la renta bruta gravada».
- **Art. 59:** con préstamos obtenidos ya siendo contribuyente, el capital amortizado no se deduce. Sí se deducen los intereses, las comisiones y los recargos de las tarjetas de crédito.
- **Art. 60:** inscripción dentro de los **30 días hábiles** de superar los ₲ 80.000.000.
- **Art. 61:** la declaración jurada se presenta en «el tercer mes siguiente al cierre del ejercicio fiscal».
- **Art. 62:** si en **dos ejercicios consecutivos** no se superan los ₲ 80.000.000, cesa la obligación de declarar desde el ejercicio siguiente. La RG 69, art. 29, cuenta el primer ejercicio de la inscripción.
- **Arts. 63 y 64:** retención especial al servicio diplomático y consular, con pago único. No aplica al caso general.

### 4.3 RG N° 69/2020 (05-11-2020)

Reglamenta el IRP y aprueba los formularios. Oficial leída.

- **Art. 11:** el primer ejercicio va desde el día siguiente a superar el monto no alcanzado (MNA, ₲ 80.000.000) hasta el 31 de diciembre. «Cuando los ingresos gravados de los ejercicios fiscales siguientes no superen el MNA, el contribuyente deberá presentar igualmente la Declaración Jurada».
- **Art. 13:** los familiares a cargo se informan en la declaración jurada anual.
- **Arts. 17 a 20:** se admiten el esparcimiento en el país (deporte, cultura, turismo, mascotas, etc.), la movilidad, las pólizas de seguros con comprobante de una aseguradora del país y la medicina prepaga.
- **Art. 26, no deducibles:** esparcimiento o turismo pagados en el exterior, pagos en cumplimiento de sanciones, lo imputado a otro impuesto y el capital de los préstamos posteriores a la inscripción.
- **Art. 27, documentos.** La lista importa para el registro de comprobantes (§7).
  - Ingresos: liquidación de salario, facturas preimpresas, virtuales o electrónicas.
  - Egresos:
    - boleta Resimple;
    - facturas;
    - autofacturas;
    - comprobantes de ingresos de entes públicos;
    - «Extracto de Cuenta del empleador emitido por el Instituto de Previsión Social»;
    - boletas de venta, entradas, pasajes, tiques y boletos;
    - «Extractos de tarjetas de crédito o débito emitidas por entidades radicadas en el país o comprobantes de transferencia o giros bancarios […] así como los comprobantes del exterior con legalización consular», solo para salud y educación;
    - recibo de donación;
    - despacho de importación;
    - documentos de la prestación alimentaria (art. 15);
    - extracto del billetaje electrónico.
- **Art. 28:**
  - La declaración jurada se presenta todos los años, «aun cuando en el Ejercicio Fiscal no hayan percibido rentas […] o estos fueran inferiores al MNA».
  - **Formulario N° 515**, «hasta el día del vencimiento del tercer mes después de finalizado el ejercicio fiscal».
  - Pago con la obligación **715-IRP RSP**.
- **Art. 30:** el contribuyente del IRP-RSP retiene el INR solo si paga servicios similares a un no residente.
- **Art. 32:** «deberá registrar sus operaciones en los libros de ingresos y de egresos utilizando los mecanismos dispuestos por la Administración Tributaria». Hoy ese mecanismo es la RG 90/2021 (§7).
- **Art. 40:** formularios **515 versión 1 (obligación 715, IRP-RSP)** y **516 versión 1 (obligación 716, IRP-RGC)**, disponibles desde el 01-12-2020.

### 4.4 Vencimiento

- RG 38/2020, art. 2°: IRP «hasta el día del vencimiento del tercer mes después de finalizado el ejercicio fiscal».
- Con el ejercicio igual al año civil (art. 52), vence en **marzo**, en el día de `CAL-PERPETUO-DJ` según la terminación de la cédula.
- La página IRP de la DNIT dice «Anual (Marzo)». Coincide.

### 4.5 Formulario 515 versión 1

Casillas leídas del formulario y de su instructivo. Oficial leída.

| Rubro | Casillas |
|---|---|
| Encabezado | 01 original, 02 rectificativa, 03 número que rectifica, 04 año, 05 clausura |
| 1 Ingresos (col. I exonerados, col. II gravados) | 10 y 12 ingresos propios (art. 62); 11 y 13 como padre, tutor o curador; **14** total de ingresos gravados |
| 2 Egresos deducibles | **15** actividad; **16** personales y familiares en el país; **17** salud y educación en el exterior; **18** autovehículo cada 3 años; **19** aporte patronal; **20** seguridad social privada; **21** donaciones (hasta el 5%); **22** suma de 15 a 21 (sin arrastre); **23** vivienda al contado cada 5 años; **24** = 22 + 23 |
| 3 Resultado | 25 = 14; 26 = 22, limitada a 25; 27 = 25 − 26; 28 = 23, limitada a 27; **29** subtotal de renta neta; 30 préstamos o remanente usados (Anexo, casilla 102); 31 pérdida no arrastrable; 32 pérdida arrastrable |
| 4 Pérdida por vivienda | 33 a 39 (arrastre de 5 años; compensación de hasta el 20% de la casilla 29 en la 38) |
| 5 Liquidación (col. I contribuyente, col. II fisco) | **45** renta neta imponible = 29 − 38; **46** 8%; **47** 9%; **48** 10%; 40 saldo a favor anterior; 41 retenciones; 42 percepciones; 49 multa; 43 y 50 subtotales; **44** saldo a favor; **51** saldo a ingresar |
| Anexo, Cuadro 1 | 52 a 102: préstamos y remanentes (RUC de la entidad, fecha, monto total, monto usado) |

- El instructivo dice que los ingresos se consignan «de acuerdo con lo declarado en el Libro de Ingresos». Es decir, desde el registro de comprobantes.
- Solo encontré la **versión 1** del 515 en la página de formularios de la DNIT (D-PF-13).

---

## 5. IRP-RGC: rentas y ganancias del capital (obligación 716)

### 5.1 Qué rentas y cómo se miden

**Ley 6380/2019:**

- **Art. 57:** alcanza, entre otras rentas:
  - dividendos y utilidades «excluidas las rentas gravadas por el IDU»;
  - intereses;
  - regalías;
  - la venta de acciones y cuotas;
  - el arrendamiento o la venta de inmuebles;
  - la venta de bienes muebles;
  - premios;
  - el incremento patrimonial no justificado.
- **Art. 56, exoneradas:**
  - num. 3: ventas de bienes muebles que en el año no superen ₲ 20.000.000;
  - num. 12: «Los intereses, comisiones o rendimientos por depósitos o colocaciones de capitales en entidades bancarias y financieras en el país […] así como en Cooperativas y Mutuales»;
  - nums. 9 y 10: títulos de la bolsa.
- **Art. 59, renta neta:**
  - En ventas, la menor entre el 30% del precio y la diferencia real documentada.
  - En arrendamientos, a opción del contribuyente, el 50% del precio o el precio menos el impuesto inmobiliario y los gastos documentados.
  - En regalías, intereses y dividendos no alcanzados por el IDU, «El monto total percibido».
- **Art. 60:** tasa del **8%**.
- **Art. 61:** retención con pago único en premios de juegos de azar, venta de inmuebles y regalías.

**Decreto 3184:**

- **Art. 15:** en el arrendamiento rige la menor entre el 50% del precio y el precio menos los gastos «documentados a nombre del propietario».
- **Art. 16 (texto del Decreto 4661/2020):** la administradora de inmuebles retiene el IRP.
- **Art. 17:** los dividendos y utilidades son ingreso gravado del IRP «siempre y cuando no hayan abonado el IDU por tales rentas».
- **Art. 40 (texto del Decreto 7047/2022):** inscripción dentro de los 30 días hábiles. No hace falta si la renta tuvo retención con pago único y definitivo.
- **Art. 41:** se declaran solo las rentas que no tuvieron retención con pago único. Las enumera: rentas vitalicias y seguros, arrendamiento, excedentes de cooperativas y mutuales, regalías del exterior, venta de muebles y venta de acciones, cuotas y derechos. Se presenta «en el tercer mes siguiente al cierre del ejercicio fiscal».

**RG 69/2020:**

- **Art. 3°:** en el arrendamiento se toman las cuotas «efectivamente cobradas en el ejercicio fiscal, excluido el IVA».
- **Art. 7°:** cómo se documenta cada renta. El arrendamiento, con comprobante de venta (factura). Los dividendos no alcanzados por el IDU, con comprobante de retención. Los intereses, con el extracto de la entidad.
- **Art. 8°:** alta de la obligación **716-IRP RGC** con la actividad 99999. Para alquileres, la actividad **68100** y la inscripción «al momento de iniciar dicha actividad».
- **Art. 9°:** **Formulario N° 516** en el plazo del IRP (RG 38/2020, art. 2°, num. 2), con la planilla de cálculo auxiliar. Pago con la obligación 716.
- **Art. 10:** si en el año anterior no hubo rentas, se puede pedir la baja de la obligación 716 dentro de los 30 días hábiles del nuevo ejercicio. Pasado ese plazo hay multa.

### 5.2 Relación con el IDU (dividendos de una EAS)

- **Ley, art. 41:** el IDU retenido a una persona física residente «tendrá carácter de pago único y definitivo».
- **Ley, art. 57, num. 1, y Decreto 3184, art. 17:** el dividendo que pagó IDU no entra en el IRP.

**Para la aplicación:** el dueño de la EAS que cobra dividendos con IDU retenido (8%, obligación 726 de la EAS) **no** los declara en el 516. Tampoco tiene que inscribirse en el 716 por ellos (Decreto 7047, art. 40). Lectura conjunta de las normas citadas.

### 5.3 Formulario 516 versión 2

**RG N° 121/2022** (06-10-2022), art. 1°: aprueba el «516 - Versión 2», obligación 716, «correspondiente al Ejercicio Fiscal 2022 en adelante», disponible en Marangatu desde el 01-01-2023. Oficial leída.

| Rubro | Casillas |
|---|---|
| 1 Enajenación de muebles, inmuebles a plazo, acciones, cuotas y derechos (col. I precio de venta sin IVA, II costo más gastos, III renta neta real, IV presunta 30%, V la menor) | muebles 10-12 / 24-26 / 38-40 / 50-52 / 62-64; inmuebles a plazo 133-147; acciones 15-17 … 67-69; cuotas 18-20 … 70-72; derechos 21-23 … 73-75; **76** total |
| 2 Arrendamiento y subarrendamiento (col. I precio sin IVA, II gastos, III real, IV presunta 50%, V la menor) | arrendamiento 77-79 … 101-103; subarrendamiento 80-82 … 104-106; **107** total |
| 3 Rescate de acciones o cuotas no alcanzado por el IDU | 108-119; **120** total |
| 4 Otras rentas sin retención | 122 regalías (70%); 124 incorporación de dinero; 126 seguros de vida y rentas vitalicias; 127 otros; **128** total |
| 5 Liquidación | **129** = 76 + 107 + 120 + 128; **130** = 8% de 129; 131 multa; **132** saldo a ingresar |

- La versión 2 no tiene casillas de retenciones ni de saldo a favor: lo retenido con pago único no se declara.

---

## 6. IRE RESIMPLE (obligación 702)

### 6.1 Quién puede

- **Ley 6380, art. 27:** «destinado a aquellas empresas unipersonales que realicen actividades gravadas por el IRE», con ingresos brutos devengados del ejercicio anterior «iguales o inferiores a G. 80.000.000».
- **Ley, art. 28:** importadores y exportadores, al Régimen General. El encabezado del Formulario 502 lo repite: «NO APLICABLE A IMPORTADORES Y EXPORTADORES».
- **Decreto 3182/2019, art. 81:** la unipersonal obligada por la Ley 1034/1983 «Del Comerciante» a llevar «una contabilidad ordenada y regular» **no puede** liquidar por el RESIMPLE (D-PF-11).
- **No es contribuyente del IVA** (art. 27, último párrafo).

### 6.2 Cuotas

**Ley, art. 27:** suma mensual fija según los ingresos del ejercicio anterior.

| Ingresos brutos del ejercicio anterior | Cuota mensual |
|---|---|
| Hasta ₲ 20.000.000 | ₲ 20.000 |
| De ₲ 20.000.001 a ₲ 40.000.000 | ₲ 40.000 |
| De ₲ 40.000.001 a ₲ 60.000.000 | ₲ 60.000 |
| De ₲ 60.000.001 a ₲ 80.000.000 | ₲ 80.000 |

**Decreto 3182, art. 80:**

- Declaración jurada informativa anual «dentro del segundo mes del cierre».
- El pago mensual se hace «en forma trimestral, en los meses de marzo, junio, setiembre y diciembre».
- La declaración jurada sin movimiento lleva a pagar ₲ 20.000 por mes el año siguiente.
- El RESIMPLE no paga anticipos ni sufre retenciones.

**RG N° 61/2020** (13-08-2020):

- **Art. 12:**
  - Formulario N° 502 con los ingresos del ejercicio anterior.
  - Las cuotas se imputan en la cuenta corriente tributaria.
  - «La presentación de la declaración jurada deberá efectuarse **hasta el 26 de febrero** después de finalizado el ejercicio fiscal.»
  - El pago, con la obligación 702, «hasta el día de vencimiento del mes de marzo, junio, setiembre y diciembre» del Calendario Perpetuo.
- **Art. 13:** si no la presenta, la SET genera la declaración jurada «el día 27 del mes de febrero», tomando ingresos de hasta ₲ 20.000.000.
- **Art. 14:** al cesar, clausurar o cambiar de régimen se presenta el 502 en carácter de clausura. Se debe la cuota de los meses transcurridos hasta el mes anterior.
- **Art. 15:** si supera el tope, la SET lo traslada de oficio al SIMPLE o al Régimen General desde el 1 de enero siguiente. El traslado voluntario requiere 3 ejercicios en el régimen.
- **Art. 22:** **deroga el literal «i»** del art. 2°, num. 1, inc. c) de la RG 38/2020, que decía «segundo mes» para la declaración jurada del RESIMPLE. Desde entonces rige la fecha fija del 26 de febrero. La página de la RG 38/2020 en la DNIT todavía muestra el texto anterior (D-PF-8).

**Cartilla RESIMPLE DNIT (08-2024)** y noticia DNIT del 22-02-2024 («el 26 de febrero vence el plazo»): coinciden con la RG 61/2020.

**Ojo:** la página RESIMPLE de la DNIT dice «Vencimiento: Mensual» (D-PF-9).

### 6.3 Formulario 502 versión 1

| Rubro | Casillas |
|---|---|
| 1 Ingresos brutos devengados del ejercicio | **10** |
| 2 Cuotas del ejercicio **siguiente** | 11-14 fechas de vencimiento (marzo, junio, setiembre, diciembre); **15-18** monto de cada trimestre; **19** total del año |
| 3 Clausura o traslado | 20 fecha (último día del mes de presentación); 21 monto único |

- **Inferencia:** el monto de cada trimestre sería 3 veces la cuota mensual. El formulario lo calcula solo; no encontré la fórmula escrita (D-PF-9).

### 6.4 Comprobante

- **Boleta Resimple** (tipo 104 en el registro de comprobantes), preimpresa con timbrado. Para el comprador es deducible en los impuestos a la renta (cartilla DNIT, que cita la RG 32/2020; no leí la RG 32).
- **RG 69/2020, art. 27:** es egreso válido para el IRP-RSP.

---

## 7. Libros, registro de comprobantes y registro anual 956

**¿Contabilidad por partida doble o solo el registro?**

- **IRP (RSP y RGC):** la RG 69/2020, art. 32, pide «libros de ingresos y de egresos utilizando los mecanismos dispuestos por la Administración Tributaria». No pide libro diario, inventario ni mayor. Ese mecanismo es la RG 90/2021: su art. 2° dice que el registro electrónico «conformarán […] los libros de ingresos y egresos de los contribuyentes del IRP-RSP».
- **IVA:** libros de compras y ventas, también por la RG 90/2021.
- **IRE SIMPLE:** el Decreto 3182, art. 79, pide libros de ingresos y egresos.
- **IRE General (unipersonal):** el Decreto 3182, art. 64, remite a la Ley 1034/1983 (libro diario, inventario, mayor). Ver `TRIBUTACION_PY.md` §2.2.
- **RESIMPLE:** no figura entre los obligados al registro (RG 90/2021, art. 3°: IVA, IRP-RSP e IRE SIMPLE). Tampoco es contribuyente del IVA. Debe emitir la boleta, respaldar sus compras y presentar el 502 (Ley, art. 27). Lectura propia: no lleva registro de comprobantes.
- **Conclusión para la aplicación:** a la persona física con IRP o RESIMPLE no se le exige contabilidad por partida doble. La contabilidad completa solo se le exige si es una unipersonal en el Régimen General o si la Ley 1034 la obliga (D-PF-11). Igual, la aplicación puede llevarla como herramienta interna.

**RG 90/2021 y RG DNIT 12/2024: obligaciones 955 y 956.** Oficial leída (texto original de la RG 90 en el PDF DNIT y texto vigente del art. 7° en la RG DNIT 12/2024).

- **Art. 7° vigente:** «956-REG. ANUAL COMPROB. — Registro anual de comprobantes — 715-IRP RSP — Hasta el segundo mes de cerrado el ejercicio fiscal, conforme al calendario de vencimiento DJI».
  - Con el cierre al 31 de diciembre, vence en **febrero**, en el día de `CAL-PERPETUO-DJI`.
  - La investigación anterior (`TRIBUTACION_PY.md` §4.1) citó el plazo sin la frase «conforme al calendario de vencimiento DJI».
- **Mismo artículo:** «El contribuyente que se encuentre obligado al IVA e IRP-RSP, o al IVA e IRE SIMPLE estará afectado a la obligación 955-REG. MENSUAL COMPROB.».
  - **Con IVA no hay 956:** todo va al registro mensual 955.
- **Art. 12:** la SET da de alta la 955 o la 956 según corresponda.
- **Art. 13:** se confirma aunque no haya habido ingresos ni egresos.
- **Art. 14 (texto original):** si el contribuyente del IRP-RSP empieza una actividad con IVA, en enero del año siguiente la SET da de baja la 956 y da de alta la 955. La RG 132/2023 reescribió este artículo y no leí el texto nuevo (D-PF-7).
- **Sujetos (art. 3°):** IVA, IRP-RSP e IRE SIMPLE. **El IRP-RGC no figura** (D-PF-6).

**Formato del archivo para la 956** (especificación técnica de junio de 2021, ya transcripta en `formato_registro_comprobantes.yaml`):

- Nombre `<RUC sin DV>_REG_AAAA_<id de hasta 5>`; ejemplo `80000000_REG_2021_E0001.zip`.
- **INGRESOS: 15 columnas** y **EGRESOS: 18 columnas**. Ya están completas en el YAML, con orden, tipo, longitud y obligatoriedad. **No hizo falta ampliar el YAML.**
- Los comprobantes con timbrado (factura 109, boleta Resimple 104, tique 112, etc.) van en COMPRAS o VENTAS con «Imputa IRP-RSP = S». EGRESOS e INGRESOS son para los documentos **sin timbrado**. Entre los errores frecuentes, la DNIT lista «facturas cargadas como egresos» (`TRIBUTACION_FASE4.md` §1.3).

**Qué comprobantes sin timbrado cuentan como egreso del IRP-RSP.** Se cruzan los tipos de la Tabla 4 de la especificación con los documentos de la RG 69/2020, art. 27:

| Tipo | Nombre (Tabla 4) | Respaldo en la RG 69/2020, art. 27 |
|---|---|---|
| 201 | Comprobante de egresos por compras a crédito | factura a crédito vinculada a sus recibos (art. 19, párr. 2, para seguros) |
| 202 | Comprobante del exterior legalizado | «comprobantes del exterior con legalización consular» (salud y educación) |
| 204 | Comprobante de ingresos de entidades públicas, religiosas o de beneficio público | «Comprobantes de Ingresos de Entes Públicos»; recibo de donación |
| 205 | Extracto de cuenta, billetaje electrónico | extracto de las empresas del billetaje electrónico |
| 206 | Extracto de cuenta de IPS | «Extracto de Cuenta del empleador emitido por el Instituto de Previsión Social» |
| 207 | Extracto de cuenta TC/TD | extractos de tarjetas de entidades del país (salud y educación). Es el único tipo de egreso que admite «Imputa IVA = S» |
| 208 | Liquidación de salario | ingreso en relación de dependencia; también egreso (aporte) |
| 209 | Otros comprobantes de egresos | p. ej., documentos de la prestación alimentaria (art. 15) |
| 211 | Transferencias o giros bancarios, boleta de depósito | «comprobantes de transferencia o giros bancarios» (salud y educación en el exterior) |

- La correspondencia fila por fila es **lectura propia**: la especificación no cita la RG 69.
- La guía de registro para el IRP-RSP (webinar DNIT de 2025, 97 páginas) es una presentación escaneada sin texto: **no se pudo leer** con herramientas de texto.

---

## 8. Verificado, no verificado y no se pudo leer

«Verificado» quiere decir: texto oficial leído y citado aquí. No reemplaza la aprobación del propietario (D-120). Las reglas siguen en `pending`.

| Tema | Estado | Fuente |
|---|---|---|
| RUC de la persona física = cédula; el DV va aparte, con guion | verificado | RG 79/2021, arts. 6° y 7° (texto RG 133/2023) |
| Algoritmo del DV (módulo 11, pesos 2-11, letras por su ASCII) | verificado | PDF DNIT «Dígito Verificador» (2013) |
| EIRL con RUC propio (serie 80.000.000) | verificado | RG 79/2021, art. 6°, inc. c) |
| Unipersonal (no EIRL) con el mismo RUC que su dueño | no verificado (inferencia) | RG 79/2021, art. 6°; guía de inscripción de personas físicas |
| Ley 2421/2004, art. 37 (RUC = cédula) | no verificado (citado por la DNIT) | RG DNIT 30/2025, considerandos |
| Persona física con servicios o alquileres = contribuyente del IVA | verificado | Ley 6380, art. 82, num. 1 |
| Ningún umbral de ingresos para el IVA de la persona física | no verificado (la ley no lo fija; el decreto no lo revisé) | Ley 6380, art. 82; Decreto 3107/2019 sin revisar en ese punto |
| Rubros de IVA crédito de la persona física | no verificado (citado por la cartilla) | Decreto 8175/2022, art. 1° |
| IRP-RSP: umbral, deducciones, tasas, declaración aunque no haya ingresos, cese a los 2 años | verificado | Ley 6380, arts. 62-69; Decreto 3184, arts. 55-62; RG 69/2020, arts. 11, 28 y 29 |
| IRP sin anticipos | no verificado (lectura propia: no hay norma que los cree) | Ley 6380, art. 24 (solo el IRE) |
| Formulario 515 v1 y sus casillas | verificado | Formulario 515 e instructivo (DNIT) |
| IRP-RGC: alquileres, intereses, dividendos, tasa del 8%, Formulario 516 | verificado | Ley 6380, arts. 56-61; Decreto 3184, arts. 15, 17, 40 y 41; RG 69/2020, arts. 3° y 7°-10 |
| Formulario 516 v2 (desde el ejercicio 2022) y sus casillas | verificado | RG 121/2022, art. 1°; formulario e instructivo v2 |
| Dividendo con IDU fuera del IRP | verificado | Ley 6380, arts. 41 y 57; Decreto 3184, art. 17 |
| IRP: vence en el tercer mes (marzo) | verificado | RG 38/2020, art. 2°; RG 69/2020, art. 28; Decreto 3184, arts. 41 y 61 |
| RESIMPLE: quién, escala, cuotas trimestrales, 502, declaración jurada de oficio | verificado | Ley 6380, art. 27; Decreto 3182, arts. 80-82; RG 61/2020, arts. 12-15 y 22; Formulario 502 e instructivo |
| RESIMPLE: declaración jurada hasta el 26 de febrero (fecha fija) | verificado, con una contradicción de página (D-PF-8) | RG 61/2020, arts. 12 y 22 |
| Monto trimestral del RESIMPLE = 3 cuotas | no verificado (inferencia) | Formulario 502, casillas 15-18 |
| Boleta Resimple (RG 32/2020) | no verificado (citado por la cartilla) | Cartilla RESIMPLE DNIT 2024 |
| Registro anual 956: plazo, asociación con la 715, paso a la 955 si hay IVA | verificado | RG 90/2021, arts. 3°, 12 y 13; art. 7° según RG DNIT 12/2024 |
| RG 90/2021, art. 14, texto vigente (RG 132/2023) | no verificado | — |
| Columnas de INGRESOS y EGRESOS | verificado (ya estaba) | Especificación técnica v1, junio de 2021 |
| Ley 1034/1983: quién debe llevar contabilidad | no verificado | — |
| Decretos 7047/2022 y 4661/2020: día y mes | no se pudo leer | escaneo |
| Webinars DNIT de 2025 y 2026 (IRP-RSP, registro para el IRP-RSP, RESIMPLE, llenado del 516) | no se pudo leer (presentaciones escaneadas sin texto) | página «Materiales utilizados» de la DNIT |

---

## 9. Dudas abiertas (D-PF)

**D-PF-1. ¿La empresa unipersonal usa el RUC de su dueño?**

- Ninguna norma leída lo dice con todas las letras. Lo sugiere la RG 79/2021, art. 6°: solo la EIRL recibe una serie propia.
- **Mirar la constancia de RUC** de cada persona física: ¿figuran ahí sus obligaciones 700, 701 o 702?

**D-PF-2. Inmuebles del dueño de una unipersonal.**

- La Ley 6380, art. 31, manda el alquiler al IRP.
- La misma ley, art. 3°, y el Decreto 3184, art. 13, lo mandan al IRE RG si el bien está en el activo o en la contabilidad de la unipersonal.
- **¿Qué criterio aplica la aplicación?** Propuesta: el IRE si el bien está en el activo, el IRP si no.

**D-PF-3. ¿Hay un umbral para que la persona física que presta servicios sea contribuyente del IVA?**

- La ley no fija ninguno.
- No revisé la parte del Decreto 3107/2019 que trata de los contribuyentes.

**D-PF-4. IVA crédito de la persona física.** Leer el Decreto 8175/2022 (rubros admitidos y tope del 30% en alimentos) antes de aplicar las reglas `IVA-CREDITO-*` a una persona física.

**D-PF-5. Retenciones del IRP-RSP.** ¿Qué retenciones generales se computan hoy en la casilla 41 del 515? Solo encontré los regímenes especiales: el del servicio diplomático y el INR que retiene el propio contribuyente.

**D-PF-6. ¿El IRP-RGC registra comprobantes?**

- La RG 69/2020, art. 32, habla del «contribuyente de este impuesto», es decir, de todo el IRP.
- La RG 90/2021, art. 3°, solo nombra al IRP-RSP.
- **Propuesta:** el RGC sin IVA no tiene 955 ni 956. El RGC con alquileres sí es contribuyente del IVA y va a la 955.

**D-PF-7. RG 90/2021, art. 14.** Leer el texto de la RG 132/2023 sobre el paso de la 956 a la 955 cuando aparece el IVA.

**D-PF-8. Fecha de la declaración jurada del RESIMPLE.**

- La RG 61/2020 fija el 26 de febrero y deroga el «segundo mes» de la RG 38/2020. La página de la RG 38 en la DNIT no lo refleja.
- **Propuesta:** fecha fija, 26 de febrero. Si ese día es inhábil, ¿se corre? Ninguna norma leída lo dice.

**D-PF-9. Pagos del RESIMPLE.**

- La página DNIT dice «Mensual».
- La norma (Decreto 3182, art. 80; RG 61/2020, art. 12) y el 502 dicen trimestral: marzo, junio, setiembre y diciembre.
- **¿El monto trimestral es 3 cuotas mensuales?** Inferencia, sin texto expreso.

**D-PF-10. Primer año del RESIMPLE.** El art. 80 del Decreto 3182 solo regula la transición de 2020 a 2021. ¿Qué paga quien se inscribe a mitad de año? ¿Desde cuándo?

**D-PF-11. Ley 1034/1983 «Del Comerciante».**

- ¿Qué persona física o unipersonal está obligada a llevar contabilidad? Eso la excluye del RESIMPLE (Decreto 3182, art. 81) y define si la aplicación le exige partida doble.
- No leí la ley.

**D-PF-12. Modificaciones de la Ley 6380 en el IRP.** No rastreé las leyes que la modifican (pendiente desde `TRIBUTACION_PY.md` §11). El texto de la DNIT que leí no muestra cambios en los arts. 47-70.

**D-PF-13. Versión del Formulario 515.**

- Solo encontré la v1 (RG 69/2020). Confirmar que no hay otra.
- El 516 ya está en la v2 (RG 121/2022).

**D-PF-14. Regla `RUC-DV-MODULO11`.**

- Ya hay una fuente oficial leída (§1).
- **¿Se pasa a la versión 2** con `confidence: oficial_leida`, la URL del PDF DNIT y el reemplazo de las letras por su código ASCII? Resolvería la D-F4-10.
- No la modifiqué: cambiaría una regla que ya está cargada (misma salvedad que la D-121).

**D-PF-15. Multa por presentar tarde el 515, el 516 o el 502** (casillas 49 y 131) y por confirmar tarde la 956 (RG 90/2021, art. 8°). No encontré el monto (igual que la D-11).

**D-PF-16. Deducciones que la aplicación no puede saber sola.** El familiar a cargo (cónyuge no contribuyente, ingresos de hasta ₲ 30.000.000), el autovehículo cada 3 años y la vivienda cada 5 años dependen de datos del contribuyente. ¿Se piden en el perfil de la persona física?

---

## 10. Índice de fuentes

Todas abiertas el 2026-11-25.

| Norma o documento | Fecha | URL |
|---|---|---|
| Ley 6380/2019 (texto en la DNIT) | 25-09-2019 | <https://www.dnit.gov.py/web/portal-institucional/w/d-ley-n-6380-19> |
| Decreto 3184/2019 (IRP) | 30-12-2019 | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3184-19.pdf/6eaa47e9-504b-fc0b-6a03-4dc2b267e2a8?t=1681424323603> |
| Decreto 7047/2022 (modifica los arts. 9°, 31, 40 y 54) | 2022 (ilegible) | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+7047-2022.pdf/abf71f71-2cbd-04f3-b44c-a44caee6e547?t=1681411840312> |
| Decreto 4661/2020 (modifica los arts. 16 y 50) | 31-?-2020 | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+4661-2020.pdf/de9af38f-36bd-f4dc-db1b-cab69d903163?t=1681422917008> |
| Decreto 3182/2019 (IRE), arts. 79-82 | 2019 | <https://www.dnit.gov.py/documents/47797/47809/Decreto+N%C2%B0+3182-19.pdf/ee6adbdb-f9c2-7a3f-877d-96a0bbbc0a3d?t=1681424260226.pdf> |
| RG 69/2020 (IRP) | 05-11-2020 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-69-20> |
| RG 121/2022 (516 v2) | 06-10-2022 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-121-22> |
| RG 61/2020 (IRE; RESIMPLE) | 13-08-2020 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-61-20> |
| RG 38/2020 (calendario) | 05-02-2020 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-38-20> |
| RG 90/2021 (PDF original) | 07-05-2021 | <https://www.dnit.gov.py/documents/20123/199761/RG+N%C2%B0+90+Registro+de+comprobantes+de+ingresos%2C+ventas%2C+egresos+y+compras_07_05_2021.pdf/79409903-d18f-1a9d-97a6-0ee840345395?t=1682697830527> |
| RG DNIT 12/2024 (art. 7° vigente) | 31-05-2024 | <https://www.dnit.gov.py/documents/20123/796215/Res.+General+DNIT+N%C2%B0+12_2024.pdf/06555b22-920e-f0ac-74d9-f5b6aa50329f?t=1717201434815> |
| RG 79/2021 (RUC) | 20-01-2021 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-n-79-21-1> |
| RG 133/2023 (modifica el art. 6° de la RG 79) | 14-07-2023 | <https://www.dnit.gov.py/web/portal-institucional/w/rg-133/23> |
| RG DNIT 30/2025 (cita la Ley 2421/2004) | 2025 | <https://www.dnit.gov.py/web/portal-institucional/w/resolucion-general-dnit-30/25> |
| «Cálculo del Dígito Verificador» (DNIT) | 20-11-2013 (metadatos) | <https://www.dnit.gov.py/documents/20123/224893/D%C3%ADgito+Verificador.pdf/fb9f86c8-245d-9dad-2dc1-ac3b3dc307a7?t=1683354226554.pdf> |
| Página «Otras herramientas» (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/otras-herramientas> |
| Guía de inscripción en el RUC de personas físicas | 08-09-2022 (metadatos) | <https://www.dnit.gov.py/documents/20123/199761/Gu%C3%ADa+Paso+a+Paso+-+Inscripci%C3%B3n+en+el+RUC+Personas+F%C3%ADsicas.pdf/c66a1a36-9c77-d56b-7be9-fe14986bd090?t=1682697830491.pdf> |
| Formulario 515 v1 | 2020 | <https://www.dnit.gov.py/documents/47797/47809/Formulario+N%C2%B0+515+-+IRP+-+Rentas+derivadas+de+la+prestaci%C3%B3n+de+Servicios+Personales+-+Versi%C3%B3n+1.pdf/1ce752c2-a872-3a46-cef3-8b9a549fe9bd?t=1680733732205> |
| Instructivo del 515 v1 | 2020 | <https://www.dnit.gov.py/documents/47797/47809/Instructivo+del+Formulario+N%C2%B0+515+-+IRP+Rentas+Prov.+de+Servicios+Personales+-+Versi%C3%B3n+1.pdf/65ca3664-e43a-099c-692f-d19f87494e5c?t=1680634973558> |
| Formulario 516 v2 | 09-2022 (metadatos) | <https://www.dnit.gov.py/documents/47797/47809/Formulario+N%C2%B0+516+-+Versi%C3%B3n+2.pdf/62caef07-8f07-050d-b3dd-9ab8c27be852?t=1680733896736> |
| Instructivo del 516 v2 | 09-2022 (metadatos) | <https://www.dnit.gov.py/documents/47797/47809/Instructivo+del+Formulario+N%C2%B0+516+Versi%C3%B3n+2.pdf/13950f98-3456-2140-b0dc-9dadf7339e25?t=1680735132170> |
| Formulario 502 v1 | 2020 | <https://www.dnit.gov.py/documents/47797/47809/Formulario+N%C2%B0+502+-+IRE+RESIMPLE+Versi%C3%B3n+1.pdf/1d8e1e72-0f5f-cf09-cb87-d68b9741c0bb?t=1680733598164> |
| Instructivo del 502 v1 | 2020 | <https://www.dnit.gov.py/documents/47797/47809/Instructivo+Formulario+N%C2%B0+502+IRE+RESIMPLE+Versi%C3%B3n+1+%281%29.pdf/039c61eb-a186-3ce0-0aa5-cbe048534287?t=1681325201043> |
| Página IRP (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/irp> |
| Cartilla IRP-RSP | 06-08-2024 | <https://www.dnit.gov.py/documents/20123/233435/IRP+RSP+Cartilla+6.08.24.pdf/bb45c6ef-0c98-771a-c530-ac893db6bce2?t=1722965031873.pdf> |
| Página RESIMPLE (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/ire-simple> |
| Cartilla RESIMPLE | 08-2024 | <https://www.dnit.gov.py/documents/20123/216504/IRE+Resimple+Cartilla+6.08.24.pdf/a0586c49-bc45-a6df-377d-562d771ddcf1?t=1722964955242.pdf> |
| Cartilla IVA | 06-08-2024 | <https://www.dnit.gov.py/documents/20123/224724/IVA+Cartilla+6.08.24.pdf/c23f9d9f-8747-815f-28c2-4d0c1fa9e6d6?t=1722964877639.pdf> |
| Formularios e instructivos (DNIT) | — | <https://www.dnit.gov.py/web/portal-institucional/formularios-instructivos> · <https://www.dnit.gov.py/web/portal-institucional/declaraciones-juradas> |
| Materiales utilizados (webinars) | — | <https://www.dnit.gov.py/web/portal-institucional/materiales-utilizados> |
