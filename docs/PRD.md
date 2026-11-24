# PRD — CONTADOR AI

Documento de producto derivado de `PROMPT_MAESTRO.md` (fuente completa de requisitos).

## Problema
Una EAS paraguaya y su propietario administran contabilidad, impuestos, facturación electrónica y finanzas personales con herramientas separadas. La información queda dispersa, las obligaciones se siguen a mano y no hay trazabilidad entre una factura, su asiento y su impuesto.

## Usuarios
| Usuario | Necesidad principal |
|---|---|
| Propietario/a de la EAS | Ver la situación real de la empresa y de sus finanzas personales, sin mezclarlas; saber qué vence |
| Contador/a externo/a | Registrar y revisar la contabilidad, preparar información para declaraciones, con trazabilidad |
| Administración (futuro) | Cargar movimientos, documentos, facturas |

## Objetivos
1. Una sola fuente de verdad local, auditable, para contabilidad, finanzas y facturación.
2. Separación estricta entre finanzas personales y empresariales, con vista consolidada que muestra el origen.
3. Obligaciones tributarias configuradas solo con reglas verificadas y fuente oficial.
4. Reutilizar la facturación electrónica SIFEN existente.
5. Un asistente de IA que consulta y propone, nunca ejecuta lo irreversible sin aprobación.

## No objetivos
- Reemplazar libros rubricados ni registros oficiales.
- Presentar declaraciones o pagos de forma automática.
- Asesoramiento tributario sin validación profesional.

## Alcance por módulo
Los 10 módulos del prompt maestro (§4). Prioridad y orden en `ROADMAP.md`.

## Requisitos no funcionales
| Requisito | Criterio |
|---|---|
| Plataformas | Windows 10/11 x64, Linux x64 (Ubuntu/Debian, Fedora vía RPM, AppImage) |
| Funcionamiento sin internet | Todo salvo SIFEN y el asistente |
| Exactitud monetaria | Decimal de punta a punta; nunca `float` |
| Auditoría | Toda modificación con usuario, fecha, antes y después; inalterable |
| Seguridad | Ver `SECURITY.md` |
| Rendimiento | Pantallas habituales < 300 ms con 100.000 movimientos (a medir en fase 2) |
| Idioma | Español rioplatense/paraguayo; fechas y montos con formato `es-PY` |
| Accesibilidad | Navegación por teclado, foco visible, contraste AA, movimiento reducido |

## Métricas de éxito (a confirmar con el propietario)
- Conciliación bancaria mensual en menos de 1 hora.
- 0 asientos contabilizados descuadrados (garantizado por la base).
- 100 % de obligaciones con fuente y vencimiento antes de la fecha.

## Supuestos y datos pendientes
Ver `PROJECT_STATUS.md § Información requerida`.
