# Estado del proyecto

**Última actualización:** 2026-11-23 · **Fase actual:** 1B — Instalador para Windows 11

## Resumen

| Fase | Estado |
|---|---|
| 0 — Discovery y auditoría | ✅ Completa |
| 1 — Fundación | ✅ Funcional en navegador |
| 1B — Instalador Windows 11 | 🟡 Backend empaquetado y verificado en Linux; CI escrito (sin ejecutar); falta lanzador Rust e instalador |
| 2 a 8 | ⏳ No iniciadas |

**Destino definido por el propietario:** una PC con Windows 11, uso en una sola máquina (D-016). Desarrollo en esta PC Linux; instaladores generados en GitHub Actions.

## Funcionalidades operativas (probadas de punta a punta)

| Funcionalidad | UI | API | Persistencia | Validación | Permisos | Pruebas | Docs |
|---|---|---|---|---|---|---|---|
| Configuración inicial (empresa + propietario) | ✅ | ✅ | ✅ | ✅ | n/a (solo base vacía) | ✅ + E2E | ✅ |
| Ingreso / cierre de sesión / bloqueo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Cambio de contraseña | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Usuarios y roles | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Datos de la empresa + DV del RUC | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ + E2E | ✅ |
| Auditoría inmutable + verificación | ✅ | ✅ | ✅ | n/a | ✅ | ✅ + E2E | ✅ |
| Eventos de seguridad | ✅ | ✅ | ✅ | n/a | ✅ | ✅ + E2E | ✅ |
| Tema claro / oscuro / sistema | ✅ | n/a | preferencia local | n/a | n/a | E2E | ✅ |

## Pruebas ejecutadas (2026-11-23)
- Backend empaquetado (PyInstaller, Linux): migró una base vacía, configuración inicial e ingreso OK; usa psycopg binario.
- Ruedas para Windows + Python 3.14 verificadas para todas las dependencias del backend; zip de PostgreSQL 18.7 para Windows verificado (estructura `pgsql/bin|lib|share`).
- Backend: 28/28 pytest contra PostgreSQL 18.7; ruff y mypy estricto sin errores; `alembic check` sin diferencias; `downgrade base` → `upgrade head` OK.
- Frontend: 10/10 Vitest; `tsc -b` OK; build de producción OK (397 kB JS, 123 kB gzip).
- E2E en Chromium con base aislada: flujo completo sin errores de consola (ver `TESTING_STRATEGY.md`).

## Problemas conocidos / pendientes técnicos
| # | Pendiente | Motivo |
|---|---|---|
| P-1 | Tauri no compilado | Faltan Rust, `pkg-config`, `libwebkit2gtk-4.1-dev`, `librsvg2-dev`, `libssl-dev` (requieren `sudo`) |
| P-2 | CI escrito pero nunca ejecutado | Requiere el primer push; el repositorio de GitHub es **público** |
| P-7 | Advertencia de PyInstaller `psycopg_binary._uuid` | Inofensiva: la receta de psycopg menciona un módulo que no existe en 3.3.9; el ejecutable usa la implementación binaria (verificado) |
| P-3 | Script E2E fuera del repo | Se incorpora como `frontend/e2e/` con Playwright en fase 2 |
| P-4 | 2 advertencias de oxlint (`only-export-components`) | Hooks junto a sus providers; solo afecta la recarga en caliente |
| P-5 | El backend no lo lanza Tauri | Lanzador en fase 1B; hoy se levanta con `scripts/dev.sh` |
| P-6 | La política de contraseñas del frontend cuenta como "símbolo" las letras con tilde | El backend es quien decide (Unicode); solo cambia el aviso previo |

## Decisiones tomadas en esta sesión
D-001 a D-020 en `DECISIONS.md`. **D-007 (facturación como servicio Node) requiere tu confirmación.**

## Información requerida del propietario
0. **Repositorio GitHub:** hacerlo privado (recomendado) y autorizar el commit inicial y el push. Sin esto no se pueden generar instaladores de Windows.
1. **Confirmar D-007**: reutilizar el núcleo SIFEN como servicio Node (recomendado) en lugar de portarlo a Python.
2. **Repositorio original del CRM de Zestia** (el que contiene `@crm/contracts`, `test/helpers/certificate.ts`, etc.). El extracto no trae los helpers de prueba ni `contracts/invoicing.ts`; sin ellos hay que recrearlos.
3. **Constancia de RUC** de la EAS: RUC, DV, obligaciones inscriptas, actividades económicas, fecha de cierre del ejercicio.
4. **Facturación electrónica**: estado de la habilitación, timbrado de pruebas, certificado de firma (prestador habilitado), IdCSC/CSC de pruebas.
5. **Contador/a responsable** que validará las reglas tributarias (nombre/matrícula para el campo "revisado por").
6. **Bancos** con los que opera (para preparar los adaptadores de extractos) y un extracto de ejemplo anonimizado.
7. **Instalar las dependencias de Tauri** en esta PC (comandos en el README) para desarrollar el lanzador.
8. Revisar los hallazgos R-10 y R-11 de `DISCOVERY.md` (repositorio git en la carpeta personal con `.git-credentials`).

## Próximo objetivo recomendado
Fase 1B: primer push → CI verde en Windows → lanzador Rust → instalador NSIS instalado en la PC con Windows 11. Después, fase 2.
