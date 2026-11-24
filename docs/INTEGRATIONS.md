# Integraciones

## 1. Facturación electrónica SIFEN — informe de auditoría e integración

**Proyecto auditado:** `~/Escritorio/facturacion-sifen-zestia` (PC de desarrollo) (proporcionado por el propietario el 2026-11-23).
**Modo:** solo lectura. No se modificó ningún archivo del proyecto original.

### 1.1 Qué es

Un **extracto** del módulo de facturación electrónica del "CRM de ZESTIA" (extraído el 2026-11-11 según `FACTURACION_ELECTRONICA_SIFEN.md`). No es un proyecto ejecutable por sí solo: no tiene `package.json`, ni `schema.prisma`, ni configuración de TypeScript, y no es un repositorio git con historial.

| Parte | Contenido | Líneas aprox. |
|---|---|---|
| `apps/api/src/invoicing/sifen/` | **Núcleo SIFEN**: CDC, DV, código de seguridad, QR (`codes.ts`); XML del DE (`de-xml.ts`); firma XMLDSig (`signature.ts`); validación XSD (`xsd-validator.ts`); transporte SOAP 1.2 con TLS mutuo (`transport.ts`); mensajes y parseo de respuestas (`ws-messages.ts`); eventos de cancelación/inutilización (`event-xml.ts`); KuDE en PDF (`kude-data.ts`, `kude-pdf.ts`) | ~2.000 |
| `apps/api/src/invoicing/*.ts` | **Orquestación NestJS**: servicio de facturas, envíos con reintentos y reserva (`sifen-submissions.ts`), eventos, correo con KuDE, material de firma, controlador REST | ~2.400 |
| `apps/api/prisma/migrations/` | 8 migraciones SQL (perfil fiscal, puntos de expedición, facturas, eventos, rango de timbrado) | ~330 |
| `apps/api/sifen-xsd/` | 18 XSD oficiales v150/v141 con hashes MD5 documentados | — |
| `apps/api/test/` | 9 suites, ~130 casos con Vitest, un SIFEN falso y un servidor HTTPS con TLS mutuo | ~3.100 |
| `apps/dashboard/.../facturacion/page.tsx` | Pantalla Next.js de configuración | 464 |
| `packages/contracts/src/sifen.ts` | DV módulo 11 y patrón de email del XSD | 29 |
| `scripts/sifen-test-probe.ts` | Genera un XML firmado de prueba y opcionalmente lo envía al SIFEN de pruebas | 269 |
| `docs/FACTURACION.md`, `FACTURACION_ELECTRONICA_SIFEN.md` | Decisiones, fuentes y guía de implementación (muy completas) | 1.350 |

**Stack:** TypeScript, NestJS, Prisma, PostgreSQL. Librerías: `node-forge`, `xml-crypto`, `@xmldom/xmldom`, `xmllint-wasm`, `pdf-lib`, `uqr`.

### 1.2 Integración con SIFEN (qué resuelve)

| Capacidad | Estado en el proyecto | Verificado contra |
|---|---|---|
| CDC de 44 dígitos, DV módulo 11, código de seguridad | Completo | Ejemplos del Manual Técnico v150 |
| XML del DE (factura tipo 1, nota de crédito tipo 5) | Completo | XSD oficiales `DE_v150.xsd`, `siRecepDE_v150.xsd` |
| Firma XMLDSig (RSA-SHA256, C14N, enveloped + exc-c14n) | Completo | XSD + pruebas con certificado autofirmado |
| Certificado `.p12`: validación de vigencia, RSA 2048-4096, keyUsage, RUC del titular, defensa contra PKCS#12 con iteraciones abusivas | Completo | Pruebas |
| Secretos (clave privada, CSC) cifrados AES-256-GCM con AAD por empresa | Completo | Pruebas |
| QR del KuDE con `cHashQR` | Completo | Hash oficial del manual |
| Recepción síncrona `siRecepDE` y consulta por CDC | Completo | **SIFEN falso** |
| Reintentos con consulta previa por CDC y reserva anti-duplicado | Completo | **SIFEN falso** |
| Cancelación (48 h) e inutilización con eventos firmados | Completo | **SIFEN falso** |
| Notas de crédito electrónicas | Completo (desde devoluciones del CRM) | **SIFEN falso** |
| KuDE PDF y correo al comprador | Completo | Pruebas |
| Lote asíncrono | **No implementado** (decisión: hasta que haga falta volumen) | — |
| Notas de débito, autofactura, nota de remisión | **No implementado** | — |
| Eventos del receptor (conformidad, disconformidad, desconocimiento) | **No implementado** | — |
| Facturas recibidas (de proveedores) | **No aplica**: el proyecto solo emite | — |

**Ambientes:** `test` (`sifen-test.set.gov.py`) y `production` (`sifen.set.gov.py`) por empresa (`fiscal_profiles.environment`). La transmisión se enciende con `SIFEN_TRANSMISSION=on|off`, apagada por defecto fuera de producción.

### 1.3 Funcionalidades incompletas y puntos "por confirmar"
Documentados por el propio proyecto (`docs/FACTURACION.md`) y confirmados en la auditoría:

1. **Nunca se probó contra el SIFEN de pruebas real.** Todo el flujo de red se probó con un SIFEN falso.
2. Rutas de los WSDL (`/de/ws/sync/recibe.wsdl`, `/de/ws/consultas/consulta.wsdl`, `/de/ws/eventos/evento.wsdl`) **sin fuente oficial encontrada**.
3. Códigos de consulta `0422`/`0420` y detección de "CDC duplicado" y "ya cancelado" **por texto del mensaje**.
4. Si hace falta enviar la cadena del certificado intermedio en el TLS.
5. Formato del `serialNumber` del certificado real de un prestador habilitado.
6. Evento pendiente sin salida si el SIFEN responde siempre algo ilegible (límite conocido).
7. Aviso de facturas que se acercan a las 72 h sin aprobar.

### 1.4 Deuda técnica y riesgos

| Hallazgo | Impacto para CONTADOR AI |
|---|---|
| **Acoplado al CRM:** la orquestación importa 30+ módulos ausentes (`database/db-context`, `tenancy`, `jobs/job-queue`, `mail`, `storage`, `audit`, `config`, `generated/prisma/client`) y toma los datos de **pedidos** y **devoluciones** de una tienda | La orquestación no se puede reutilizar tal cual: hay que adaptarla para que la factura nazca de una solicitud de facturación, no de un pedido |
| **Faltan los helpers de prueba** (`test/helpers/certificate.ts`, `pdf.ts`, `app.ts`, `db.ts`, `auth.ts`) y `packages/contracts/src/invoicing.ts`, `orders.ts` | Las ~130 pruebas no corren hoy. El helper de certificado es necesario para las pruebas del núcleo |
| El tipo `Billing` (datos del comprador) vive en `contracts/invoicing.ts`, ausente (está transcripto en el `.md`) | Se recrea desde la documentación |
| Código Prisma generado incluido (`src/generated/prisma/models/*.ts`, 8.600 líneas) | Ruido; no se copia |
| Notas de crédito atadas a "devoluciones" del CRM | En CONTADOR AI la nota de crédito nace de una factura y un motivo |
| Sin lote asíncrono ni notas de débito | Requeridas por el PRD de CONTADOR AI (notas de débito) |

**Calidad general:** alta. Las decisiones están documentadas con fuente, las reglas críticas tienen pruebas, los secretos están bien protegidos y el diseño anticipa los fallos de red (reserva, consulta previa, "pudo haber llegado"). Coincide con la regla del proyecto de **no reimplementar SIFEN**.

### 1.5 Integración propuesta (adaptador desacoplado)

```
┌──────────────── CONTADOR AI (escritorio) ───────────────────┐
│ Frontend React ──HTTP──► Backend FastAPI (Python)            │
│                          │ billing.adapter (puerto)          │
│                          ▼                                   │
│                 SifenServiceClient (HTTP local + token)      │
│                          │                                   │
│                          ▼                                   │
│   Servicio SIFEN (Node, ejecutable único, 127.0.0.1:8766)    │
│     • núcleo sifen/* copiado TAL CUAL del proyecto original  │
│     • orquestación adaptada: solicitudes de emisión,         │
│       envío/reintentos, eventos, KuDE                        │
│     • esquema `billing` propio en la misma PostgreSQL        │
└──────────────────────────────────────────────────────────────┘
                           │ SOAP 1.2 + TLS mutuo
                           ▼
                SIFEN (DNIT): pruebas / producción
```

- **Por qué un servicio Node y no un port a Python:** el núcleo resuelve firma, XSD, TLS mutuo y KuDE con decisiones ya probadas; reescribirlo en Python reintroduciría el riesgo que el proyecto ya eliminó. Ver DECISIONS D-007.
- **Contrato del adaptador** (Python, `backend/app/integrations/billing/`): `issue_document(request) -> BillingDocumentRef`, `get_status(id)`, `resend(id)`, `cancel(id, reason)`, `disable(id, reason)`, `get_xml(id)`, `get_kude(id)`. CONTADOR AI nunca habla SOAP.
- **Trazabilidad:** cada documento emitido tiene `billing_documents.id`; el asiento contable (fase 3) y la obligación de IVA (fase 4) guardan esa referencia. Un documento solo genera asiento **definitivo** cuando el SIFEN lo aprueba (`approved` u `observed`), nunca al generarse o enviarse.
- **Ambiente:** CONTADOR AI arranca siempre en `test`; pasar a `production` es una acción del propietario, con permiso propio y auditada.

### 1.6 Plan de trabajo (fase 5)
1. Pedir el repositorio original del CRM (para los helpers de prueba y `contracts/invoicing.ts`). Si no está disponible, recrearlos.
2. Copiar `sifen/*`, XSD y sus pruebas unitarias a `services/sifen/`; hacer pasar las pruebas **sin cambios en el núcleo**.
3. Escribir la orquestación desacoplada (sin NestJS ni Prisma: Fastify + `pg` o el ORM que se decida en esa fase, con migraciones en Alembic para tener un solo historial de esquema).
4. Adaptador Python + pantallas de facturación.
5. Prueba contra el SIFEN de pruebas real con el timbrado y certificado de la empresa.
6. Notas de débito y lote asíncrono si el volumen lo justifica.

## 2. Claude API (fase 6)
Pendiente. Diseño en `docs/ARCHITECTURE.md § Asistente`. La API key irá al almacén seguro del SO; el frontend nunca la ve.

## 3. Bancos (fase 2)
Importación por archivos (CSV/XLSX) con adaptadores por banco. No hay integración en línea con bancos.
