# Hoja de ruta

Cada fase termina con un entregable ejecutable que cumple la *Definition of Done* del prompt maestro (§13).

| Fase | Objetivo | Entregables verificables | Depende de | Estado |
|---|---|---|---|---|
| 0 | Discovery y auditoría | `DISCOVERY.md`, auditoría SIFEN (`INTEGRATIONS.md`), arquitectura, riesgos | — | ✅ 2026-11-23 |
| 1 | Fundación | Backend, migraciones, autenticación, roles, auditoría inmutable, logging, frontend con sistema de diseño, configuración inicial, Tauri configurado | — | ✅ Funcional en navegador; la compilación de escritorio pasa a 1B |
| 1B | Instalador Windows | Backend empaquetado (✅ verificado en Linux), CI con prueba de humo en Windows (escrito, sin ejecutar), lanzador Rust (PostgreSQL portable + backend + secretos), instalador NSIS descargable, copia de seguridad/restauración básica | Push a GitHub autorizado | 🟡 En curso |
| 2 | Empresa y finanzas | Contextos personal/empresarial, cuentas, movimientos, categorías, contrapartes, importación CSV/XLSX con mapeo y duplicados, dashboard con gráficos, E2E en CI | Fase 1 | ⏳ |
| 3 | Contabilidad | Plan de cuentas (modelo base paraguayo a validar con el contador), períodos, asientos con partida doble y reversión, diario, mayor, balance de comprobación, estados contables, cierre | Fase 2 | ⏳ |
| 4 | Tributación | Perfil fiscal verificado, motor de reglas versionado, obligaciones y calendario, estimaciones de IVA/IRE con fuente | Fase 3 + datos fiscales del propietario | ⏳ |
| 5 | Facturación y documentos | Servicio SIFEN reutilizado, adaptador, emisión/consulta/eventos, prueba en SIFEN de pruebas, vínculo con contabilidad, repositorio documental, OCR | Fases 3-4, repositorio CRM original, certificado y timbrado de pruebas | ⏳ |
| 6 | Inteligencia artificial | Asistente con herramientas controladas, aprobaciones, registro de interacciones | Fases 2-5 | ⏳ |
| 7 | Recursos humanos | Empleados, contratos, liquidaciones (borrador), IPS/MTESS con reglas verificadas | Fase 4 (motor de reglas) | ⏳ |
| 8 | QA y distribución | Actualizador automático, copias programadas, firma de código, manual de usuario, pruebas de restauración y de migración entre versiones | Todas | ⏳ |

## Próximos pasos inmediatos
1. Hacer privado el repositorio y autorizar el primer push → el CI valida el backend en Windows real.
2. Instalar Rust y las librerías de Tauri en la PC de desarrollo para escribir y probar el lanzador.
3. Lanzador Rust + job de CI que genera el instalador NSIS → primera instalación en la PC con Windows 11.
4. Fase 2: contextos financieros y cuentas (cada entrega llega a Windows como instalador nuevo).

## Fuera de alcance por ahora
- Integración en línea con bancos.
- Presentación automática de declaraciones (prohibido por el prompt: siempre manual).
- Versión web multiusuario en servidor.
