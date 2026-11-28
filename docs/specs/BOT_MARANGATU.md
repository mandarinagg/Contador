# Bot de Marangatu: diseño (D-119, D-126)

Estado: **diseño, 2026-11-25; B1 (la base) construido** (D-127 a D-133). Investigación previa en
`docs/research/BOT_MARANGATU.md`.

## 1. Qué hace

La herramienta maneja Marangatu sola, con un navegador que hace los clics:

- revisa si hay algo para presentar: obligaciones, vencimientos, estado de cuenta y el buzón
  Marandu;
- presenta el registro de comprobantes, con el archivo que ya genera la fase 4 (`exports.marangatu_file`);
- hace las declaraciones juradas (primero el F120 de IVA; después el IRE y las demás del perfil);
- descarga las constancias y los acuses, y los guarda como documento respaldatorio;
- marca la obligación como presentada y avisa con el resumen.

Presenta sin pedir aprobación (D-119), solo si se cumplen **las 12 condiciones** de la D-119.
Ante la menor duda no presenta: se detiene y avisa.

A pedido, genera la **guía paso a paso** de la misma presentación (D-126), para hacerla a mano.

Lo que **no** hace:

- **No paga.** Informa el importe y el vencimiento, y como mucho genera la boleta de pago. Falta
  confirmarlo con el propietario.
- No resuelve captchas.
- Si el ingreso falla, no reintenta.
- No presenta rectificativas sin una regla propia para cada caso.

## 2. Piezas

| Pieza | Dónde | Qué hace |
|---|---|---|
| Motor | `backend/app/modules/marangatu/` (módulo nuevo) | Tareas, condiciones, catálogo de pantallas y registro. |
| Trabajador | Proceso aparte (`python -m app.modules.marangatu.worker`; en el ejecutable empaquetado, `contador-backend.exe marangatu-worker`), lanzado por el backend (D-127) | Maneja el navegador. Si se cuelga o se cae, no tumba la API. No toca la base: cuenta los pasos en líneas JSON y el backend los escribe. |
| Navegador | Playwright para Python. En Windows, el **Microsoft Edge** del sistema (`channel="msedge"`), que Windows 11 trae siempre, así que no se empaquetan 150 MB de Chromium. En Linux y en el CI, el Chromium de Playwright. | Ventana visible por defecto (la persona ve lo que hace). Sin ventana solo en las pruebas. |
| Credenciales | Almacén de credenciales de Windows (DPAPI, por usuario) con `keyring`. Entrada `ContadorAI/Marangatu/<RUC>`. | El backend solo informa si hay clave guardada. Nunca la devuelve. No va al repositorio, la base, la auditoría ni los registros. |
| Catálogo de pantallas | `docs/research/marangatu_pantallas.yaml`, con su copia empaquetada (`pantallas.py`) y la prueba de igualdad, como las reglas | Cada pantalla conocida y lo que se puede hacer en ella. |
| Portal simulado | `backend/tests/marangatu_fake/`: HTML local que imita las pantallas del catálogo | Las pruebas y el CI nunca tocan el portal real. |

### Credenciales

- La clave se escribe una vez en la app: Impuestos → Marangatu → «Guardar la clave». Viaja una
  sola vez al backend local (127.0.0.1), que la pasa a `keyring`.
- El cuerpo de ese pedido se excluye de los registros y de la auditoría. La auditoría guarda solo
  «clave de Marangatu guardada» o «borrada».
- El trabajador la lee de `keyring` justo antes de escribirla en el formulario de ingreso y no la
  conserva.
- Las capturas de la pantalla de ingreso se toman **antes** de escribir la clave.
- Prueba obligatoria: después de una corrida, la clave no aparece en la base, en los registros ni
  en los archivos de captura (se busca el texto exacto).

## 3. Catálogo de pantallas

Cada pantalla del catálogo tiene:

```yaml
- id: f120_casillas_debito
  version: 1
  provisoria: true     # hasta confirmarla en el portal real
  reconoce:            # todo tiene que estar; si falta algo, pantalla desconocida
    url: "/eset/.../formulario"        # expresión regular que se busca en la URL
    titulo: "Formulario 120"           # el título de la página lo contiene
    textos: ["Rubro 1", "Casilla 10"]
    campos: ["#casilla10", "#casilla11"]
  detiene: null        # o un código de §8: al ver esta pantalla, se detiene (gana sobre las demás)
  acciones:            # lo único que el bot puede hacer en esta pantalla
    - llenar: {casilla: 10, campo: "#casilla10"}
    - clic: {boton: "Siguiente", campo: "#siguiente", va_a: [f120_casillas_credito], final: false}
  capturada_en: "2026-12-..."   # cuándo se registró, en el reconocimiento
```

- `final` va en la acción (`clic`), no en la pantalla: es `true` solo para el clic que presenta
  (D-129). Si coinciden varias pantallas normales, es pantalla desconocida.

- El bot solo avanza por las pantallas del catálogo y solo hace sus acciones (condición 7). Ante
  una pantalla, un texto, un mensaje o un error que no estén en el catálogo, **se detiene sin
  presentar** y guarda la captura.
- Una acción `final: true` (el clic que presenta) solo se ejecuta si la tarea está habilitada y
  pasaron las 12 condiciones en ese momento.
- **El catálogo se arma con el portal real.** Hoy no conozco las pantallas de Marangatu por dentro.
  - La primera corrida es un **reconocimiento** con la clave del propietario: ingresa, recorre los
    menús de consulta y abre los formularios, **sin llenar ni presentar nada**.
  - De cada pantalla guarda la captura y la estructura (títulos, campos, botones).
  - En el recorrido solo sigue enlaces del mismo sitio, abriendo su dirección: nunca hace clic en
    botones ni envía formularios, y salta los enlaces con palabras como «Presentar», «Enviar»,
    «Confirmar» o «Pagar», las descargas y el de salir. Una pantalla desconocida no lo detiene en
    el recorrido (es lo que viene a conocer), pero sí en el ingreso (D-132).
  - **Ingreso e inicio (D-145):** la pantalla de ingreso del catálogo es la página real (formulario
    `loginForm`, botón «Acceder»). Después del clic, una pantalla desconocida solo se toma como
    **inicio provisorio** si no tiene campo de clave, no pide captcha y no es la del ingreso; si
    sigue el campo de clave, se detiene con `UNKNOWN_SCREEN` y no se reintenta. Si no se encuentra
    el enlace de salir, lo anota y la sesión se cierra al cerrar el navegador.
  - **Pantallas reales y espera (D-146):** el catálogo trae el inicio (`/eset/`) y cuatro pantallas
    reales, reconocidas solo por dirección y título (sin textos: pueden ser datos personales). Se
    sale con el enlace «Salir» (`/eset/logout`), que el recorrido nunca sigue. Antes de leer cada
    página espera, con tope, la red quieta y que desaparezcan los textos de «cargando»
    (`meta.cargando`), porque el menú lo arma JavaScript.
  - Deja un borrador del catálogo (`catalogo_borrador.yaml`) para revisar a mano: reconoce por
    dirección, título y campos, sin textos ni encabezados (D-146).
  - Con eso se escribe el catálogo y el portal simulado.
- El portal puede cambiar sin aviso (Res. 568/2006, art. 13). Entonces se detiene, y el siguiente
  reconocimiento actualiza el catálogo (con `version` + 1).

## 4. Tareas

Una corrida es una tarea de un tipo. Cada tipo pasa por tres etapas, y nunca se saltea una:

1. `reconocimiento`: solo navega y captura.
2. `ensayo`: llena todo y lee de vuelta, **sin el clic final** (condición 11).
3. `habilitada`: presenta sola.

El cambio de `ensayo` a `habilitada` es automático después de **3 ensayos seguidos sin
diferencias** del mismo tipo, en períodos distintos. El propietario puede volver un tipo a
`ensayo` cuando quiera. Hay además un interruptor general: «Bot apagado» frena todo.

| Tipo | Qué hace | Orden de construcción |
|---|---|---|
| `consulta` | Ingresa, verifica el perfil (RUC, DV, nombre, obligaciones) y lee obligaciones pendientes, vencimientos, estado de cuenta y buzón Marandu. Lo compara con el calendario de la herramienta. | 1 |
| `registro_comprobantes` | Sube el ZIP del registro de comprobantes del mes y descarga el acuse. | 2 |
| `f120` | Llena el Formulario 120 con el borrador (D-097, D-122), lo lee de vuelta, lo presenta y descarga la constancia. | 3 |
| `constancias` | Descarga las constancias de lo ya presentado que falten en la herramienta. | con 1 |
| `ire`, otras | Igual que la `f120`, una por formulario. | después |

### Pasos de una presentación

1. **Preparar** (sin navegador): calcula la declaración y revisa las condiciones 1, 3, 4 y 8.
   - Condición 3 (cuadre): con contabilidad, contra el mayor (`vat._ledger_control` en el F120).
     Sin contabilidad (persona física sin IRE General; enmienda de la D-119 del 2026-11-26,
     D-144), contra el registro de comprobantes del período, al guaraní: `irp.condition_3` para
     el 515, que devuelve `matches` y `stop_code`. Si no cuadra o no se puede cuadrar,
     `LEDGER_MISMATCH`. Se vuelve a correr con las casillas leídas de vuelta (condición 6).
   - Si falla una, no abre el navegador.
   - La tarea queda `detenida`, con el motivo y lo que hay que hacer.
2. **Ingresar:** un solo intento. Ante «usuario o contraseña incorrectos», un captcha o cualquier
   pantalla desconocida, se detiene.
3. **Perfil** (condición 2): RUC, DV, razón social y obligaciones de Marangatu contra el perfil
   fiscal verificado. Cualquier diferencia lo detiene.
4. **Sin duplicados** (condición 5): consulta si el período ya está presentado. Si lo está, no
   presenta y trae la constancia.
5. **Llenar:** solo las acciones del catálogo.
6. **Leer de vuelta** (condición 6): lee cada casilla de la pantalla y la compara al guaraní con lo
   calculado. También compara los totales que calcula el propio Marangatu.
7. **Presentar:** el clic `final`, solo si la tarea está `habilitada` y las 12 condiciones se
   vuelven a evaluar en ese instante. En `ensayo`, la corrida termina acá y sale de Marangatu sin
   presentar.
8. **Acuse** (Res. 568/2006, art. 8): sin acuse inmediato, la presentación cuenta como **no
   hecha**.
   - La tarea queda `incierta`. Nunca se reintenta en esa corrida.
   - La siguiente corrida empieza por el paso 4, para saber si quedó presentada.
9. **Constancia** (condición 9): la descarga y comprueba el número, el período y los importes.
   - La guarda como documento respaldatorio.
   - Llama a `obligations.file` con el número, la fecha y los importes declarados.
   - Avisa con el resumen.
   - Si la constancia no coincide con lo calculado, abre una alerta de **rectificativa necesaria**
     (se prepara aparte).
10. **Salir** de Marangatu y cerrar el navegador, siempre, también al detenerse.

### Cuándo corre (condición 8)

- La app revisa al abrirse y cada 6 horas mientras está abierta. La PC del propietario puede estar
  apagada; no hay servidor.
- `consulta` corre una vez por día.
- Una presentación corre desde **5 días hábiles antes** del vencimiento (configurable, mínimo 2) y
  no el último día.
- Si el bot se detiene y faltan 2 días hábiles o menos, el aviso es urgente y ofrece la guía paso a
  paso.

## 5. Registro (condición 10; Res. 568/2006, art. 10)

- Tablas `marangatu.runs` (corrida: tipo, período, etapa, resultado, motivo) y `marangatu.steps`
  (paso: hora, pantalla reconocida, acción, valores sin la clave, resultado y captura).
- Las capturas y los archivos descargados se guardan en el almacén de documentos de la app, con su
  SHA-256. Mientras no exista ese almacén (fase 6), van a `<datos>/documentos/<organización>/marangatu/<corrida>/`
  (D-140; antes, sin la organización) y el paso guarda la ruta relativa y el SHA-256 (D-131).
- **Solo agregar:** un disparador rechaza `UPDATE` y `DELETE` en `steps`, como en los asientos
  contabilizados.
- Cada paso guarda el hash del anterior (cadena). Una verificación recorre la cadena y avisa si
  algo se modificó.
- Se conservan durante la prescripción. La bajada de la migración se niega si hay corridas (D-080).
- La verificación también vuelve a calcular el SHA-256 de cada archivo (D-133).

## 6. Guía paso a paso (D-126)

A pedido, o cuando el bot se detiene, la herramienta genera la guía de esa presentación:

- cada pantalla del catálogo, en orden, con la captura del último reconocimiento o ensayo;
- qué tocar en cada una: el menú, el botón y el campo;
- el importe de cada casilla, calculado y cuadrado;
- el archivo para subir, si corresponde;
- al final, cómo cargar la constancia en la herramienta: «Marcar presentada» con el número.

Es una página de la app que se puede imprimir. Sale del mismo catálogo, así que si el bot conoce
la pantalla, la guía también.

## 7. Estados que ve la persona

- Por obligación:
  - «El bot la presenta el 15/12»;
  - «En ensayo (2 de 3)»;
  - «Presentada por el bot, constancia N° …»;
  - «Detenida: <motivo>. [Ver guía] [Reintentar]»;
  - «Incierta: revisando si quedó presentada».
- Impuestos → Marangatu:
  - el interruptor general;
  - la clave guardada (sí o no);
  - la etapa de cada tipo de tarea;
  - las últimas corridas con sus pasos y capturas;
  - «Hacer un reconocimiento».

## 8. Motivos de detención (códigos)

`RULE_PENDING`, `PROFILE_MISMATCH`, `LEDGER_MISMATCH`, `DATA_INCOMPLETE`, `ALREADY_FILED`,
`READBACK_MISMATCH`, `UNKNOWN_SCREEN`, `LOGIN_FAILED`, `CAPTCHA`, `NO_RECEIPT`,
`RECEIPT_MISMATCH`, `TOO_LATE`, `BOT_OFF`, `NOT_ENABLED`, `NO_CREDENTIALS`, `BROWSER_ERROR`.

Cada uno tiene un texto para la persona que dice qué pasó y qué hacer.

## 9. Pruebas

- **Portal simulado:** las mismas pantallas del catálogo servidas en local. Casos:
  - camino feliz;
  - pantalla cambiada;
  - casilla que no se llena;
  - totales que difieren;
  - período ya presentado;
  - sin acuse;
  - constancia con otro importe;
  - ingreso fallido;
  - captcha.
- Cada motivo de la sección 8 tiene al menos una prueba que comprueba que **no** se hizo el clic
  final.
- La prueba de la clave (sección 2).
- La cadena del registro: si se modifica un paso a mano (saltando el disparador como superusuario),
  la verificación lo detecta.
- El CI nunca se conecta al portal real.

## 10. Orden de construcción

1. **B1 — Base:**
   - módulo, tablas y migración;
   - credenciales con `keyring`;
   - trabajador y navegador;
   - motor del catálogo;
   - registro con cadena;
   - interruptor;
   - portal simulado mínimo;
   - **modo reconocimiento**.
2. **Reconocimiento real (con el propietario):** una corrida con su clave, en su PC, para escribir
   el catálogo.
3. **B2 — `consulta` y `constancias`**, con la comparación con el calendario y el perfil.
4. **B3 — `registro_comprobantes`** (requisito previo de la D-119: primero uno o dos
   comprobantes).
5. **B4 — `f120`.**
6. **B5 — Guía paso a paso.**
7. Después, el IRE y los demás formularios del perfil.

## 11. Abierto

- Pagos: el bot no paga y como mucho genera la boleta (por confirmar con el propietario).
- RG 04/2007 sin leer (es un escaneo).
- Si el ingreso de Marangatu usa algo más que usuario y clave en la práctica: lo dirá el
  reconocimiento.
