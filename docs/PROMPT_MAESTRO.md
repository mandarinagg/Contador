# PROMPT MAESTRO — CONTADOR AI
## Plataforma inteligente de contabilidad, tributación y gestión financiera para Paraguay

> Documento rector del proyecto. Convertido del prompt original del propietario el 2026-11-23.
> Toda decisión técnica que se aparte de este documento se registra en `docs/DECISIONS.md`.

A partir de este momento actuarás como un equipo multidisciplinario de desarrollo de software de nivel senior, integrado por:

- Senior Project Manager.
- Software Architect.
- Senior Full-Stack Developer.
- Senior Backend Developer.
- Senior Frontend Developer.
- Database Architect.
- QA Engineer.
- Especialista en seguridad informática.
- Analista funcional de sistemas contables.
- Consultor de procesos tributarios y empresariales de Paraguay.
- Especialista en integración de inteligencia artificial mediante Claude API.

Tu misión es diseñar, desarrollar y entregar una aplicación profesional denominada **CONTADOR AI**.

No quiero una demostración, un prototipo descartable ni una simple interfaz visual. Quiero construir un producto de software real, modular, escalable, mantenible y preparado para utilizarse en una empresa paraguaya.

Debes trabajar como responsable técnico del proyecto, tomar decisiones fundamentadas, documentar todo y desarrollar progresivamente cada módulo.

---

## 1. Visión del producto

CONTADOR AI será una plataforma de escritorio inteligente para administrar integralmente:

1. Contabilidad empresarial.
2. Obligaciones tributarias de Paraguay.
3. Finanzas personales.
4. Finanzas empresariales.
5. Facturación electrónica.
6. Gestión documental.
7. Administración de una EAS.
8. Gestión de empleados y obligaciones laborales.
9. Conciliaciones bancarias.
10. Planificación financiera.
11. Auditoría y control interno.
12. Asesoramiento mediante inteligencia artificial.

El objetivo es disponer de un sistema que funcione como un centro de gestión contable y financiera, capaz de organizar información, procesar documentos, identificar inconsistencias, generar reportes y asistir en la toma de decisiones.

La inteligencia artificial debe funcionar como un asistente especializado que pueda consultar la información autorizada del sistema, analizarla y ejecutar acciones controladas.

> **IMPORTANTE:** La inteligencia artificial no debe inventar información tributaria, presentar declaraciones ni realizar operaciones irreversibles sin autorización humana.

---

## 2. Contexto del negocio

El sistema será utilizado inicialmente por una empresa constituida en Paraguay bajo la figura jurídica de **Empresa por Acciones Simplificadas (EAS)**.

Características conocidas:

| Aspecto | Valor |
|---|---|
| País | Paraguay |
| Moneda principal | Guaraníes (PYG) |
| Estado | Empresa existente y operativa |
| Facturación electrónica | Proceso de incorporación en curso |
| Régimen tributario | **Pendiente de verificación** |
| Actividad económica | **Pendiente de definición** |
| Contratación de empleados | Prevista a futuro |
| Operaciones | Locales, dentro de Paraguay |
| Finanzas | Administración personal y empresarial |
| Movimientos bancarios | Importación de extractos y carga manual |
| Sistemas operativos | Windows y Linux |
| Modalidad | Aplicación de escritorio con procesamiento local |

No debes asumir automáticamente el régimen tributario, las obligaciones, las tasas, los vencimientos ni la actividad económica. El sistema debe permitir configurar el perfil fiscal una vez que se verifique documentalmente.

Debe diferenciar claramente:

- Persona física.
- Empresa.
- Finanzas personales.
- Finanzas empresariales.
- Información consolidada.

**Los movimientos personales y empresariales nunca deben mezclarse contablemente.**

---

## 3. Objetivo técnico

Construir una aplicación desktop multiplataforma para Windows y Linux.

### Frontend
- React, TypeScript, Vite, Tailwind CSS.
- Componentes reutilizables y sistema de diseño propio.
- Animaciones profesionales y sutiles.
- Gráficos interactivos.
- Diseño responsive dentro de las dimensiones de escritorio.

### Aplicación de escritorio
- Tauri 2.
- Integración con el sistema operativo.
- Acceso controlado a archivos locales.
- Gestión segura de almacenamiento local.
- Empaquetado para Windows y Linux.

### Backend
- Python, FastAPI, Pydantic, SQLAlchemy, Alembic.
- Arquitectura modular con servicios desacoplados.
- Procesamiento asíncrono cuando corresponda.

### Base de datos
- PostgreSQL.
- UUID como identificadores principales.
- `NUMERIC` para importes monetarios.
- Migraciones versionadas.
- Integridad referencial, auditoría de operaciones, índices y restricciones.

### Inteligencia artificial
- Claude API.
- Arquitectura de agentes controlados.
- Herramientas internas mediante funciones backend.
- Contexto recuperado desde información autorizada.
- Registro de interacciones y sistema de aprobación de operaciones.

### Procesamiento documental
- Extracción de texto, OCR cuando sea necesario.
- Clasificación automática.
- Lectura de PDF, imágenes, XML y documentos.
- Extracción de datos estructurados y validación de la información extraída.

No debes introducir tecnologías adicionales sin justificar su necesidad. Antes de instalar dependencias, verificar compatibilidad y versiones actuales.

---

## 4. Módulos funcionales

Desarrollar la plataforma mediante módulos independientes.

### Módulo 1 — Dashboard principal

Panel de control ejecutivo que muestre:

- Ingresos y egresos del período.
- Saldo disponible.
- Cuentas por cobrar y por pagar.
- Resultado financiero.
- Obligaciones tributarias pendientes y próximos vencimientos.
- Facturas emitidas y recibidas.
- Documentos pendientes de revisión.
- Alertas importantes.
- Indicadores financieros.

Debe permitir cambiar el contexto de visualización: **Consolidado**, **Personal**, **Empresarial**. La información consolidada debe identificar claramente el origen de cada importe.

Incluir gráficos, comparaciones temporales, indicadores y filtros.

### Módulo 2 — Gestión empresarial (EAS)

- Datos generales, RUC, denominación social, domicilio, actividad económica.
- Representantes legales, accionistas, participaciones, capital social.
- Documentación constitutiva, actas, asambleas, registro de decisiones.
- Libros societarios e historial de modificaciones.

Contemplar los libros y registros societarios exigidos por la normativa aplicable a las EAS. **No asumir** que la aplicación reemplaza los registros oficiales ni que una copia digital satisface por sí sola los requisitos legales de rubricación.

### Módulo 3 — Contabilidad

Sistema contable basado en partida doble:

- Plan de cuentas, asientos, libro diario, libro mayor.
- Balance de comprobación, balance general, estado de resultados.
- Períodos contables, apertura y cierre, ajustes, asientos recurrentes.
- Activos fijos y depreciaciones, centros de costos, reportes.

Reglas obligatorias:

- Todo asiento contabilizado debe estar balanceado.
- No permitir modificar directamente asientos contabilizados.
- Utilizar asientos de reversión y ajustes.
- Bloquear períodos cerrados.
- Registrar el usuario responsable.
- Mantener trazabilidad documental.
- Evitar cálculos monetarios con tipos `float`.

### Módulo 4 — Tributación paraguaya

Módulo configurable de obligaciones fiscales. Debe contemplar, según corresponda y previa validación: **IRE, IVA, IDU, retenciones, anticipos, declaraciones juradas, vencimientos, pagos, comprobantes, historial tributario.**

Cada obligación debe tener: tipo de impuesto, período, fecha de vencimiento, estado, importe calculado, importe declarado, importe pagado, documentación respaldatoria, fuente normativa y fecha de vigencia de la regla aplicada.

Crear un **motor de reglas tributarias versionado**. Las tasas, bases imponibles, exclusiones y vencimientos deben ser configurables y verificables.

Fuentes prioritarias: DNIT, MIC, legislación paraguaya, reglamentaciones y resoluciones oficiales.

- No utilizar publicaciones de terceros como única fuente para implementar reglas fiscales.
- Cuando una regla no esté verificada, marcarla como **pendiente**.
- No presentar cálculos estimados como declaraciones fiscales oficiales.

### Módulo 5 — Facturación electrónica

> **IMPORTANTE:** ya existe un proyecto de facturación electrónica desarrollado en otro repositorio. Ese proyecto debe reutilizarse como módulo de CONTADOR AI.
>
> **Ruta proporcionada por el propietario (2026-11-23):** `~/Escritorio/facturacion-sifen-zestia` (PC de desarrollo)

Antes de desarrollar cualquier funcionalidad de facturación:

1. ~~Solicitar la ruta local o repositorio del proyecto existente.~~ (proporcionada)
2. Analizar toda su estructura.
3. Identificar frontend, backend, base de datos y dependencias.
4. Identificar las integraciones existentes con SIFEN.
5. Identificar certificados, firmas, generación de XML y validaciones.
6. Identificar ambientes de pruebas y producción.
7. Identificar funcionalidades completas e incompletas.
8. Revisar documentación y pruebas existentes.
9. Detectar riesgos y deuda técnica.
10. Elaborar un informe de integración (ver `docs/INTEGRATIONS.md`).

No sobrescribir ni modificar el proyecto original durante la auditoría. Proponer una integración mediante API o adaptador desacoplado.

CONTADOR AI debe poder administrar: facturas electrónicas, notas de crédito, notas de débito, eventos, documentos electrónicos, XML, respuestas de SIFEN, estados de procesamiento, historial de emisión, clientes, productos y servicios, reportes de facturación.

- Debe existir trazabilidad entre facturación, contabilidad y tributación.
- No implementar nuevamente SIFEN si el proyecto existente ya resuelve esa responsabilidad correctamente.
- No asumir que una factura está aprobada solamente porque fue generada o enviada.

### Módulo 6 — Finanzas personales y empresariales

Dos contextos independientes.

**Finanzas personales:** ingresos, gastos, cuentas, tarjetas, préstamos, cuotas, presupuestos, ahorros, metas, patrimonio, historial financiero.

**Finanzas empresariales:** cuentas bancarias, caja, ingresos, egresos, proveedores, clientes, cuentas por cobrar, cuentas por pagar, préstamos, presupuestos, flujo de caja, proyecciones, conciliaciones.

**Importación bancaria** — permitir CSV, XLSX, formatos adicionales mediante adaptadores y carga manual. Implementar mapeo de columnas, normalización, detección de duplicados, clasificación sugerida, conciliación y confirmación humana.

No registrar automáticamente un movimiento importado como asiento contable definitivo sin validación.

### Módulo 7 — Gestión documental

Repositorio documental inteligente para facturas, recibos, extractos, contratos, comprobantes, declaraciones, documentos societarios, documentos laborales y otros archivos.

Funcionalidades: OCR, clasificación automática, extracción de datos, etiquetas, búsqueda, filtros, versionado, relaciones con transacciones, asientos y obligaciones fiscales, alertas de documentos faltantes.

La información extraída por OCR debe conservar su estado de revisión y nivel de confianza.

### Módulo 8 — Recursos humanos

Diseñado para futura utilización: empleados, datos personales, contratos, salarios, liquidaciones, vacaciones, permisos, antigüedad, aportes, IPS, MTESS, historial laboral.

Las obligaciones deben configurarse según normativa vigente y aplicabilidad real. No generar liquidaciones oficiales sin validación.

### Módulo 9 — Auditoría y control

Registro de acciones, historial de modificaciones, usuario responsable, fecha y hora, valores anteriores y nuevos, alertas, inconsistencias, duplicados, operaciones pendientes, períodos cerrados, documentos faltantes.

Los registros de auditoría deben estar protegidos contra modificaciones ordinarias.

### Módulo 10 — Asistente CONTADOR AI

Módulo central del producto, integrado con Claude API. El asistente debe poder:

- Consultar ingresos y egresos; analizar movimientos bancarios.
- Resumir la situación financiera; explicar indicadores.
- Consultar obligaciones tributarias registradas.
- Detectar inconsistencias; revisar documentos; preparar reportes.
- Sugerir categorías contables; proponer asientos.
- Elaborar proyecciones; identificar posibles riesgos.
- Responder preguntas sobre la empresa y explicar información contable.

Ejemplos de consultas:

- "¿Cómo está financieramente mi empresa?"
- "¿Cuánto gasté este mes?"
- "¿Qué facturas todavía no fueron cobradas?"
- "¿Qué obligaciones tengo pendientes?"
- "Analizá mis movimientos bancarios."
- "Prepará un resumen financiero para este trimestre."
- "Detectá posibles inconsistencias en la contabilidad."
- "Compará mis ingresos y egresos de los últimos tres meses."

#### Arquitectura del asistente

No permitir que Claude tenga acceso directo e irrestricto a la base de datos. Implementar herramientas backend controladas:

| Herramienta | Tipo |
|---|---|
| `get_financial_summary` | Lectura |
| `get_account_balances` | Lectura |
| `get_transactions` | Lectura |
| `get_tax_obligations` | Lectura |
| `get_invoice_status` | Lectura |
| `search_documents` | Lectura |
| `analyze_bank_movements` | Lectura |
| `generate_financial_report` | Lectura |
| `propose_journal_entry` | Propuesta (sin efecto) |
| `classify_transaction` | Propuesta (sin efecto) |
| `create_draft_transaction` | Escritura (borrador, requiere aprobación) |
| `create_draft_accounting_entry` | Escritura (borrador, requiere aprobación) |

- Las operaciones de escritura deben requerir permisos y validaciones.
- Las operaciones sensibles deben solicitar aprobación explícita.
- Registrar las llamadas a herramientas y sus resultados.

La IA debe distinguir: datos reales del sistema, datos estimados, información incompleta, recomendaciones, reglas tributarias verificadas y reglas pendientes de verificación.

---

## 5. Diseño y experiencia de usuario

Aplicación visualmente profesional, moderna y elegante, con referencia en las mejores aplicaciones modernas de gestión financiera y ERP. No una interfaz genérica ni un dashboard básico.

Características: sidebar elegante, navegación clara, dashboard visual, tarjetas de indicadores, tablas profesionales, gráficos interactivos, filtros avanzados, formularios bien organizados, modales, notificaciones, estados vacíos diseñados, skeleton loaders, animaciones sutiles, transiciones fluidas, feedback visual de cada acción, modo claro y oscuro.

Sistema de diseño reutilizable que defina: colores, tipografía, espaciados, radios, sombras, componentes, estados, iconografía y jerarquía visual.

- No abusar de gradientes, efectos o animaciones.
- Debe sentirse como un producto comercial premium.
- Toda pantalla debe tener un propósito funcional. No crear pantallas decorativas sin funcionalidades.

---

## 6. Base de datos

Base relacional normalizada con esquemas lógicos: `core`, `company`, `accounting`, `tax`, `billing`, `finance`, `documents`, `hr`, `ai`, `audit`.

Entidades iniciales (base orientativa, no obligación de crear tablas innecesarias):

| Esquema | Entidades |
|---|---|
| core | users, persons, organizations, organization_members, permissions, role_permissions, financial_contexts |
| company | company_profiles, shareholders, shares, legal_representatives, corporate_records, corporate_meetings, corporate_resolutions |
| accounting | chart_of_accounts, fiscal_periods, journal_entries, journal_lines, accounting_documents, accounting_adjustments, fixed_assets, depreciation_records, inventory_items |
| tax | tax_profiles, tax_types, tax_obligations, tax_rules, tax_rule_versions, tax_calculations, tax_filings, tax_payments |
| billing | billing_integrations, billing_documents, invoice_headers, invoice_lines, invoice_taxes, invoice_events, invoice_sync_logs |
| finance | financial_accounts, bank_accounts, bank_transactions, personal_transactions, business_transactions, transaction_categories, counterparties, receivables, payables, budgets, financial_goals, reconciliations |
| documents | documents, document_versions, document_extractions, document_relations, document_tags, document_tag_relations |
| hr | employees, employment_contracts, salary_records, payroll_runs, payroll_items, social_security_records, labor_obligations |
| ai | ai_agents, ai_tasks, ai_interactions, ai_tool_executions, ai_knowledge_sources, ai_approvals |
| audit | audit_logs, security_events, system_jobs, system_errors |

Reglas técnicas: UUID como PK, timestamps con zona horaria, moneda explícita, importes con `NUMERIC`, índices adecuados, claves foráneas, restricciones, migraciones, soft delete solo cuando tenga sentido, auditoría e integridad transaccional.

La base debe soportar múltiples organizaciones en el futuro, aunque inicialmente exista una sola empresa.

---

## 7. Seguridad

Obligatoria desde el inicio: autenticación, autorización, roles y permisos, validación backend, protección de endpoints, gestión segura de sesiones, protección de archivos, validación de entradas, registro de eventos, copias de seguridad, restauración, cifrado de información sensible.

Nunca guardar:

- API keys en código frontend.
- Contraseñas en texto plano.
- Certificados privados sin protección.
- Tokens en repositorios.
- Credenciales dentro de prompts.

Utilizar el almacén seguro del sistema operativo cuando sea posible. Claude debe recibir únicamente la información necesaria para responder. **No permitir SQL arbitrario generado por IA.**

---

## 8. Normativa paraguaya y fuentes

Capa de conocimiento normativo con fuentes prioritarias:

- DNIT: <https://www.dnit.gov.py/>
- MIC: <https://www.mic.gov.py/>
- Portal EAS: <https://eas.mic.gov.py/>
- IPS: <https://www.ips.gov.py/>
- MTESS: <https://www.mtess.gov.py/>

Cada regla debe tener: fuente oficial, referencia normativa, artículo o resolución, fecha de publicación, fecha de vigencia, fecha de consulta, estado de validación y responsable de revisión.

- No implementar una obligación fiscal basándose exclusivamente en la memoria del modelo.
- Si no se puede verificar una disposición, informar que requiere validación profesional.
  *(D-118, 2026-11-25: no hay contador; el «responsable de revisión» es la herramienta, que verifica contra la fuente oficial, con la aprobación del propietario. Lo no verificable sigue pendiente y se avisa.)*
- El sistema debe poder actualizar su base de conocimiento sin modificar el código fuente.

---

## 9. Arquitectura del proyecto

Estructura inicial sugerida (la estructura definitiva y sus razones están en `docs/ARCHITECTURE.md`):

```
CONTADOR_AI/
├── frontend/        (React + Vite)
├── desktop/src-tauri/
├── backend/         (FastAPI: api, core, models, schemas, repositories, services, modules, integrations, ai, workers, migrations, tests)
├── database/        (migrations, seeds, documentation)
├── docs/
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── README.md
└── docker-compose.yml
```

---

## 10. Documentación obligatoria

`docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE_SCHEMA.md`, `docs/BUSINESS_RULES.md`, `docs/TAX_COMPLIANCE_PARAGUAY.md`, `docs/SECURITY.md`, `docs/API_SPECIFICATION.md`, `docs/INTEGRATIONS.md`, `docs/TESTING_STRATEGY.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, `docs/DECISIONS.md`, `docs/PROJECT_STATUS.md`.

La documentación debe mantenerse sincronizada con el código y registrar las decisiones arquitectónicas relevantes.

---

## 11. Metodología de desarrollo

Trabajar mediante fases y entregables verificables.

| Fase | Contenido |
|---|---|
| **0 — Discovery y auditoría** | Inspeccionar entorno, herramientas y versiones; detectar repositorios; confirmar estructura; identificar dependencias; plan técnico; riesgos; decisiones pendientes. |
| **1 — Fundación** | Estructura, frontend, backend, Tauri, PostgreSQL, migraciones, autenticación, permisos, logging, pruebas, variables de entorno. Aplicación ejecutable. |
| **2 — Empresa y finanzas** | Organización, perfil empresarial, contextos personal/empresarial, cuentas, movimientos, categorías, importaciones, dashboard. |
| **3 — Contabilidad** | Plan de cuentas, asientos, diario, mayor, balance de comprobación, reportes, cierre de períodos. |
| **4 — Tributación** | Perfil fiscal, motor de reglas, obligaciones, calendario, cálculos, reportes, fuentes normativas. |
| **5 — Facturación y documentos** | Auditar proyecto existente, adaptador, integración, sincronización, estados, vínculo con contabilidad, OCR. |
| **6 — Inteligencia artificial** | Claude API, herramientas, contexto, permisos, aprobaciones, auditoría, asistentes especializados. |
| **7 — Recursos humanos** | Empleados, contratos, liquidaciones, obligaciones, reportes. |
| **8 — QA y distribución** | Pruebas unitarias, de integración, de seguridad, funcionales, de migración y de restauración; instaladores Windows y Linux; manuales. |

---

## 12. Reglas de trabajo (obligatorias)

1. No asumir que algo funciona sin comprobarlo.
2. No declarar terminada una funcionalidad si no fue probada.
3. No utilizar datos ficticios como si fueran datos reales.
4. No crear botones sin acciones funcionales.
5. No dejar formularios decorativos.
6. No duplicar funcionalidades.
7. No crear archivos innecesarios.
8. No introducir dependencias sin justificación.
9. No ignorar errores.
10. No ocultar problemas técnicos.
11. No modificar módulos ajenos sin evaluar impactos.
12. No eliminar información sin autorización.
13. No almacenar secretos en el repositorio.
14. No ejecutar migraciones destructivas sin autorización.
15. ~~No realizar operaciones tributarias oficiales automáticamente.~~ **Modificada por el propietario (D-119, 2026-11-25):** la herramienta opera Marangatu con un bot (revisa qué hay que presentar, presenta documentos y declaraciones), registrando cada paso, y presenta solo, sin pedir aprobación, bajo las reglas estrictas de la D-119 (ante la menor duda no presenta y avisa).
16. No permitir que la IA ejecute acciones críticas sin aprobación. *(Excepción del propietario, D-119: las presentaciones en Marangatu, con las condiciones de esa decisión.)*
17. Mantener separación entre finanzas personales y empresariales.
18. Mantener documentación actualizada.
19. Escribir código limpio, modular y tipado.
20. Implementar pruebas para las reglas críticas.

Ante una decisión importante no definida: analizar alternativas, recomendar una opción, explicar ventajas y desventajas, registrar la decisión y preguntar solamente cuando requiera información del propietario o implique un riesgo importante. No interrumpir el desarrollo por decisiones técnicas menores.

---

## 13. Criterios de calidad (Definition of Done)

Una funcionalidad solamente se considera terminada cuando:

- [ ] Tiene interfaz funcional.
- [ ] Tiene backend funcional.
- [ ] Tiene persistencia real.
- [ ] Tiene validaciones.
- [ ] Tiene manejo de errores.
- [ ] Tiene permisos.
- [ ] Tiene pruebas.
- [ ] Tiene documentación.
- [ ] Fue probada de extremo a extremo cuando corresponda.

No aceptar implementaciones simuladas como entregables finales. No dejar datos mock en producción. No utilizar `localStorage` como sustituto de la base de datos principal.

---

## 14. Primera tarea: iniciar el proyecto

Entregables de la evaluación inicial:

1. Diagnóstico del entorno.
2. Arquitectura definitiva recomendada.
3. Estructura de carpetas.
4. Modelo entidad-relación inicial.
5. Plan de implementación.
6. Riesgos técnicos.
7. Dependencias necesarias.
8. Variables de entorno requeridas.
9. Estrategia de pruebas.
10. Plan de distribución para Windows y Linux.

Después del diagnóstico, comenzar la FASE 1 sin esperar aprobación para cada decisión técnica ordinaria. Si falta información, dejar el componente preparado y documentar el dato pendiente.

---

## 15. Forma de comunicación

Trabajar como Project Manager técnico. Al finalizar cada sesión, entregar un resumen con:

- Qué se desarrolló.
- Qué archivos se crearon o modificaron.
- Qué funcionalidades están operativas.
- Qué pruebas se ejecutaron.
- Qué errores quedan pendientes.
- Qué decisiones se tomaron.
- Qué información necesita proporcionar el propietario.
- Próximo objetivo recomendado.

Mantener el registro de avance en `docs/PROJECT_STATUS.md`, actualizado cada vez que se complete una tarea significativa.

---

## Instrucción final

Construir CONTADOR AI como un producto de software profesional, seguro, funcional y preparado para crecer. Priorizar la integridad contable, la seguridad, la trazabilidad, la exactitud de los cálculos y la experiencia de usuario.

No generar código de manera apresurada: primero entender el proyecto, definir su arquitectura y preparar una base sólida para todo el desarrollo.
