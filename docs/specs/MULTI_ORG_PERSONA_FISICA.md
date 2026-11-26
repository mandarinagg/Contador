# Varias organizaciones y persona física: plan

Estado: **plan, 2026-11-25.** Decisión del propietario: además de las empresas, la app lleva
**personas físicas** (con RUC: IRP, IVA), y **una instalación lleva varias organizaciones** a la
vez, cada una con sus datos separados y un selector para elegir con cuál trabajar.

## Respuestas del propietario (2026-11-25)

1. **Unipersonal:** una sola organización por RUC. El IRE de la unipersonal es una obligación más
   de la persona física (a confirmar en la fuente oficial, F0).
2. **Finanzas personales:** lo tributario nunca lee el contexto personal (D-035). Los gastos
   deducibles del IRP se cargan como comprobantes de la organización persona física.
3. **Alta de organizaciones:** la crea el propietario de cualquier organización y queda como su
   propietario. Los demás usuarios se suman a cada una por separado (roles por organización,
   D-010). El setup sigue siendo solo con la base vacía (D-009).
4. **Bot de Marangatu:** una sola corrida en curso en toda la PC. Las demás esperan.
5. **Cuadre sin contabilidad:** si la persona física no lleva contabilidad, la condición 3 de la
   D-119 se cumple cuadrando al guaraní el borrador contra el registro de comprobantes. Cambia la
   D-119.

## Lo que ya existe

- La sesión lleva `organization_id`. `get_auth` comprueba la membresía.
- Los servicios filtran por organización. Las tablas de negocio tienen `organization_id` (las de
  `finance`, por medio de `context_id`). Hay FK compuestas `(id, organization_id)`.
- Las claves únicas ya son por organización.
- Reglas, feriados y excepciones de calendario son globales a propósito (D-084, D-108, D-114).

## Lo que falta

- Elegir y cambiar de organización (`identity/service.py::_primary_membership`).
- `POST /organizations`.
- Sumar a un usuario existente a otra organización: hoy el correo es único y da `EMAIL_TAKEN`.
- RUC único entre organizaciones: la clave de Marangatu es por RUC (D-128).
- El bot: hoy permite una corrida por organización (D-127). Los documentos no se separan por
  organización (D-131).
- Los eventos de seguridad sin organización se ven en todas (`audit/service.py`).
- Las reglas globales se verifican desde una organización sin avisar que afectan a todas.
- En el frontend: el selector, las claves de caché, los textos «empresa» y «Razón social», y
  `LegalForm` sin persona física.
- Persona física: identidad (nombres, apellidos, cédula), perfil (`ire_regime` sin `none` ni
  `resimple`), las reglas 715, 716, 956 y 702, y el registro de INGRESOS y EGRESOS del IRP-RSP con
  el archivo anual.

## Fases (cada una deja el CI verde)

| Fase | Qué | Depende de |
|---|---|---|
| F0 | Investigación del IRP, el RESIMPLE y la unipersonal: `docs/research/TRIBUTACION_PERSONA_FISICA.md` y las candidatas `pending` | — |
| M1 | Pruebas de aislamiento entre organizaciones en todos los módulos; los eventos de seguridad sin organización ya no se ven en todas | — |
| M2 | Backend: `GET /auth/organizations`, `POST /auth/switch` (un token nuevo), ingreso con organización, `POST /organizations`, sumar un usuario existente, migración 0008 con RUC único. **Hecho (2026-11-25):** además `POST /users/existing` y la 0009 (activo por organización); D-135 a D-139 | M1 |
| M3 | Frontend: selector, «Nueva organización», elección al ingresar y textos | M2 |
| M4 | Identidad de la persona física: migración con `PERSONA_FISICA`, nombres y apellidos; setup y alta con empresa o persona. **Hecho (2026-11-26):** migración 0011, `first_names` y `last_names`, «Actividad» en las finanzas; D-141 | M2 |
| M5 | Bot: una corrida en toda la PC, documentos por organización, 409 al cambiar el RUC con una clave guardada. **Hecho (2026-11-26):** migración 0010, `BOT_BUSY`, `MARANGATU_CREDENTIALS_EXIST`; D-140 | M2 |
| M6 | Perfil y calendario de la persona física: `ire_regime` con `none` y `resimple`, las reglas 715, 716, 956 y 702. **Hecho (2026-11-26):** migración 0012, coherencia por forma jurídica, día fijo del RESIMPLE; D-142 | F0, M4 |
| M7 | Registro de INGRESOS y EGRESOS y archivo anual 956. **Hecho (2026-11-26):** migración 0013, tipos 201 a 211 sin timbrado, anti duplicado sin número, `GET /tax/vouchers/export/annual`; D-143 | F0, M6 |
| M8 | Borrador de la declaración del IRP; reconocimiento del bot para persona física; cambio de la D-119 (respuesta 5) | F0, M7 |
