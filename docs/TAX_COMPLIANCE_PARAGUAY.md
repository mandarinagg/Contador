# Cumplimiento tributario — Paraguay

> **Estado: ninguna regla tributaria está implementada ni verificada todavía.**
> Este documento define cómo se incorporan. Nada de lo que sigue es asesoramiento tributario.

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
