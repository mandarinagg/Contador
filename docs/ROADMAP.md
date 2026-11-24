# Hoja de ruta

Cada fase termina con un entregable ejecutable que cumple la *Definition of Done* del prompt maestro (§13).

| Fase | Objetivo | Entregables verificables | Depende de | Estado |
|---|---|---|---|---|
| 0 | Discovery y auditoría | `DISCOVERY.md`, auditoría SIFEN (`INTEGRATIONS.md`), arquitectura, riesgos | — | ✅ 2026-11-23 |
| 1 | Fundación | Backend, migraciones, autenticación, roles, auditoría inmutable, logging, frontend con sistema de diseño, configuración inicial, Tauri configurado | — | ✅ Funcional en navegador; la compilación de escritorio pasa a 1B |
| 1B | Instalador Windows | Backend empaquetado ✅, CI en Windows real ✅, lanzador Rust ✅ (probado en Linux), instalador NSIS (en CI), primera instalación en la PC del propietario, copia de seguridad/restauración básica | — | 🟡 En curso |
| 2 | Empresa y finanzas | Contextos personal/empresarial, cuentas, movimientos, categorías, contrapartes, importación CSV/XLSX con mapeo y duplicados, dashboard con gráficos, E2E en CI | Fase 1 | ✅ 2026-11-24 (falta probar con extractos reales del propietario) |
| 3 | Contabilidad | Plan de cuentas (modelo base paraguayo a validar con el contador), períodos, asientos con partida doble y reversión, diario, mayor, balance de comprobación, estados contables, cierre | Fase 2 | ✅ 2026-11-24, núcleo y 3B (activos fijos, depreciación, centros de costos, recurrentes, XLSX/PDF). Falta que el contador valide el plan de cuentas y las vidas útiles |
| 4 | Tributación | Perfil fiscal verificado, motor de reglas versionado, obligaciones y calendario, estimaciones de IVA/IRE con fuente | Fase 3 + datos fiscales del propietario | ⏳ |
| 5 | Facturación y documentos | Servicio SIFEN reutilizado, adaptador, emisión/consulta/eventos, prueba en SIFEN de pruebas, vínculo con contabilidad, repositorio documental, OCR | Fases 3-4, repositorio CRM original, certificado y timbrado de pruebas | ⏳ |
| 6 | Inteligencia artificial | Asistente con herramientas controladas, aprobaciones, registro de interacciones | Fases 2-5 | ⏳ |
| 7 | Recursos humanos | Empleados, contratos, liquidaciones (borrador), IPS/MTESS con reglas verificadas | Fase 4 (motor de reglas) | ⏳ |
| 8 | QA y distribución | Actualizador automático, copias programadas, firma de código, manual de usuario, pruebas de restauración y de migración entre versiones | Todas | ⏳ |

## Próximos pasos inmediatos
1. CI verde del job `windows` → descargar el instalador e instalarlo en la PC con Windows 11.
2. Copia de seguridad y restauración desde la app (`pg_dump` a una carpeta elegida por el propietario).
3. Fase 2: contextos financieros y cuentas (cada entrega llega a Windows como instalador nuevo).

## Fuera de alcance por ahora
- Integración en línea con bancos.
- Presentación automática de declaraciones (prohibido por el prompt: siempre manual).
- Versión web multiusuario en servidor.
