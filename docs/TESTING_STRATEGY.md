# Estrategia de pruebas

## Pirámide

| Nivel | Herramienta | Qué cubre | Dónde |
|---|---|---|---|
| Unitarias backend | pytest | Reglas puras (DV del RUC, política de contraseñas, cálculos monetarios y tributarios) | `backend/tests` |
| Integración backend | pytest + `TestClient` + **PostgreSQL real** | Endpoints, permisos, transacciones, triggers, migraciones | `backend/tests` |
| Unitarias frontend | Vitest + jsdom | Lógica de UI (DV, política de contraseñas, cliente HTTP) | `frontend/src/**/*.test.ts` |
| E2E web | Playwright (navegador real contra backend real y base aislada) | Flujos completos | Fase 1: script manual (ver abajo). Fase 2: `frontend/e2e/` en CI |
| E2E escritorio | WebDriver de Tauri | Arranque de sidecars, instalación, actualización | Fase 8 |
| Migraciones | Alembic `upgrade` → `downgrade` → `upgrade` + `alembic check` | Reversibilidad y que el modelo coincida con la base | Antes de cada release |
| Restauración | `pg_dump` → base nueva → verificación de cadena de auditoría y totales contables | Copias útiles de verdad | Fase 8 |
| Seguridad | Pruebas de permisos por endpoint, `pip-audit`, `npm audit` | | Permisos ya en fase 1; auditorías de dependencias en CI |

## Reglas
- **Sin mocks de base de datos** (D-013). Cada prueba corre dentro de una transacción que se revierte; los `commit()` del código se vuelven SAVEPOINTs.
- Toda regla de `BUSINESS_RULES.md` marcada "Implementada" cita su prueba.
- Las reglas contables y tributarias críticas (fases 3-4) llevan pruebas de propiedades (ej. "todo asiento contabilizado suma cero") además de casos fijos.
- Un bug corregido entra con la prueba que lo reproduce.

## Cómo correrlas

```bash
docker compose -p contador up -d                 # PostgreSQL de desarrollo
cd backend && .venv/bin/pytest                   # crea contador_test y migra solo
.venv/bin/ruff check . && .venv/bin/mypy app     # lint y tipos estrictos
cd ../frontend && npm test && npm run typecheck && npm run lint
```

## Estado actual (2026-11-23)
- Backend: **28 pruebas** pasan; ruff y mypy (`strict`) sin errores; `alembic check` sin diferencias; migración reversible.
- Frontend: **10 pruebas** pasan; `tsc -b` sin errores; oxlint con 2 advertencias de recarga en caliente (hooks junto a sus providers), sin errores.
- E2E (Playwright, Chromium 159, base `contador_e2e` aislada): configuración inicial → inicio → RUC con DV erróneo y correcto → alta de usuario → auditoría y eventos de seguridad → tema oscuro → cierre de sesión → ingreso con rol Contador (sin acciones de gestión) → ingreso fallido. **Sin errores de consola.** El script todavía no está en el repositorio: se incorpora a `frontend/e2e/` con CI en la fase 2.
