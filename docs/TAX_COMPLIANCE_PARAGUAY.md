# Cumplimiento tributario — Paraguay

> **Estado: ninguna regla tributaria está implementada ni verificada todavía.**
> Este documento define cómo se incorporan. Nada de lo que sigue es asesoramiento tributario.

## Investigación preliminar (2026-11-24): pendiente de revisión del contador

Hay una primera investigación con fuentes oficiales leídas. **Todo está en `pending`; nada está `verified`.**

| Documento | Contenido |
|---|---|
| [`research/TRIBUTACION_PY.md`](research/TRIBUTACION_PY.md) | EAS (Ley 6480 y Decreto 3998), IVA, IRE, IDU, IRP, anticipos, calendario por RUC, registro de comprobantes, estados financieros, SIFEN y laboral. Cada punto con cita, enlace, fecha y nivel de confianza. Incluye contradicciones, dudas y lo no verificado. |
| [`research/tax_rules_candidatas.yaml`](research/tax_rules_candidatas.yaml) | 25 reglas candidatas con el formato de `tax_rule_versions`. Todas con `validation_status: pending` y `reviewed_by: null`. |
| [`research/PLAN_DE_CUENTAS_PY.md`](research/PLAN_DE_CUENTAS_PY.md) | No hay un plan de cuentas oficial obligatorio. Explica el modelo de estados financieros de la RG 49/2014. |
| [`research/plan_de_cuentas_propuesto.yaml`](research/plan_de_cuentas_propuesto.yaml) | Plan propuesto de 159 cuentas, basado en los códigos de la RG 49/2014. Es una propuesta para validar. |

### Resumen del estado

Ninguna fila está verificada. Todas dependen de la revisión del contador y de la constancia de RUC.

| Tema | Hallazgo (pendiente) | Confianza | Bloqueante para validar |
|---|---|---|---|
| IVA General (211) | Mensual, tasas 10% y 5%, vence según la terminación del RUC | oficial leída | Constancia de RUC |
| Registro de comprobantes (955) | Mensual, calendario DJI del mes subsiguiente | oficial leída | Formato de importación no encontrado |
| IRE (700 o 701) | 10%. Régimen General anual, 4.º mes. SIMPLE anual, 3.er mes | oficial leída | **Duda D-1/D-2: ¿la EAS puede ir al SIMPLE?** |
| Anticipos IRE (735/736) | 4 cuotas; promedio de 3 ejercicios; no aplican hasta ₲ 10 M | oficial leída | Duda D-4 (contradicción entre fuentes) |
| Estados financieros (948) | IRE General, 4.º mes, modelo RG 49/2014 | oficial leída | Duda D-10 (¿SIMPLE?) |
| IDU (726 y 954) | 8% a residente; retención al distribuir; DJI en el 6.º mes | oficial leída / citada | **Duda D-3: distribución presunta en la EAS unipersonal** |
| SIFEN | Persona jurídica inscripta en el RUC desde el 01-04-2025: solo documentos electrónicos | oficial leída | Fecha de inscripción en el RUC |
| Libros | Diario, inventario, actas y registro de acciones, rubricados; atraso de 90 días es infracción | oficial leída / citada | Duda D-7 (digital o rubricado) |
| IPS / MTESS | 9% + 16,5%; salario mínimo G. 3.044.000 desde el 01-07-2026; planillas anuales | oficial leída | Solo con empleados; vencimiento IPS no encontrado |
| Patente municipal, beneficiarios finales | — | no encontrada | Investigar |

Hasta que un contador marque `verified`, la aplicación sigue sin generar obligaciones ni cálculos tributarios (BR-TAX-01).

## Principios

1. **Fuente oficial obligatoria.** Una regla solo pasa a `verified` con una fuente de DNIT, MIC, IPS, MTESS o la legislación publicada (Ley, Decreto, Resolución General), con artículo y fecha de vigencia.
2. **La memoria del modelo no es fuente.** Lo que Claude "sepa" sobre impuestos paraguayos se trata como hipótesis hasta verificarlo en la fuente.
3. **Pendiente por defecto.** Lo no verificado se muestra como "pendiente de verificación profesional" y no genera obligaciones ni cálculos.
4. **Estimación ≠ declaración.** El sistema calcula estimaciones internas para planificar; la declaración se presenta en el sistema de la DNIT (Marangatu) por una persona.
5. **Datos, no código.** Las reglas se cargan como versiones en la base (`tax_rule_versions`), así se actualizan sin cambiar el código.

## Ficha de cada regla

| Campo | Ejemplo de formato |
|---|---|
| Impuesto | IVA / IRE / IDU / retención / anticipo |
| Descripción | Qué calcula o qué vencimiento define |
| Parámetros | Tasa, base, exclusiones, fórmula de vencimiento (ej. por terminación de RUC) |
| Fuente oficial (URL) | Página de dnit.gov.py o documento oficial |
| Referencia normativa | Ley N.º, Decreto N.º, RG N.º, artículo |
| Fecha de publicación / vigencia desde / hasta | |
| Fecha de consulta | Cuándo se leyó la fuente |
| Estado | `pending` · `verified` · `deprecated` |
| Revisado por | Persona responsable (contador/a matriculado/a) |

## Perfil fiscal de la empresa (pendiente)

| Dato | Valor | Fuente que lo acredita |
|---|---|---|
| RUC y DV | Pendiente | Constancia de RUC (DNIT) |
| Régimen / obligaciones inscriptas | **Pendiente de verificación** | Constancia de RUC / Marangatu |
| Actividad económica principal y secundarias | **Pendiente de definición** | Constancia de RUC |
| Fecha de cierre del ejercicio | Pendiente | Estatuto / DNIT |
| Calendario de vencimientos | Pendiente | Calendario oficial DNIT |
| Facturación electrónica: timbrado, establecimientos, puntos | En incorporación | Marangatu / e-Kuatia |

## Fuentes a relevar en la fase 4

- DNIT: <https://www.dnit.gov.py/> — impuestos, calendario de vencimientos, resoluciones generales, e-Kuatia.
- Documentación técnica SIFEN: <https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica> (ya usada por el proyecto de facturación: Manual Técnico v150 y notas técnicas).
- MIC / Portal EAS: <https://eas.mic.gov.py/> — obligaciones societarias de las EAS.
- IPS: <https://www.ips.gov.py/> y MTESS: <https://www.mtess.gov.py/> — obligaciones laborales (fase 7).

## Qué ya está verificado en otro proyecto
El módulo de facturación reutilizado (ver `INTEGRATIONS.md`) basó sus reglas de **documentos electrónicos** (CDC, DV, XML, firma, QR, plazos de 72/48/360 h) en el Manual Técnico SIFEN v150 y los XSD oficiales. Esas son reglas de **formato de documentos**, no de liquidación de impuestos.
