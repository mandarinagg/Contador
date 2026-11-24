# Estrategia de pruebas

## Pirámide

| Nivel | Herramienta | Qué cubre | Dónde |
|---|---|---|---|
| Unitarias backend | pytest | Reglas puras (DV del RUC, política de contraseñas, cálculos monetarios y tributarios) | `backend/tests` |
| Integración backend | pytest + `TestClient` + **PostgreSQL real** | Endpoints, permisos, transacciones, triggers, migraciones | `backend/tests` |
| Unitarias frontend | Vitest + jsdom | Lógica de UI (DV, política de contraseñas, cliente HTTP) | `frontend/src/**/*.test.ts` |
| E2E web | Playwright (navegador real contra backend real y base aislada) | Flujos completos | `frontend/e2e/`, en CI (job `e2e`) |
| E2E escritorio | WebDriver de Tauri | Arranque de sidecars, instalación, actualización | Fase 8 |
| Migraciones | Alembic `upgrade` → `downgrade` → `upgrade` + `alembic check` | Reversibilidad y que el modelo coincida con la base | Antes de cada release |
| Restauración | `pg_dump` → base nueva → verificación de cadena de auditoría y totales contables | Copias útiles de verdad | Fase 8 |
| Seguridad | Pruebas de permisos por endpoint, `pip-audit`, `npm audit` | | Permisos ya en fase 1; auditorías de dependencias en CI |

## Reglas
- **Sin mocks de base de datos** (D-013). Cada prueba corre dentro de una transacción que se revierte; los `commit()` del código se vuelven SAVEPOINTs.
- Toda regla de `BUSINESS_RULES.md` marcada "Implementada" cita su prueba.
- Las reglas contables y tributarias críticas (fases 3-4) llevan pruebas de propiedades (ej. "todo asiento contabilizado suma cero") además de casos fijos.
- Un bug corregido entra con la prueba que lo reproduce.
- Lo que depende de varias conexiones a la vez (candados, carreras) no se puede probar dentro de la transacción revertida: esas pruebas usan una base propia confirmada (`<base de pruebas>_conc`, que el fixture crea y borra), hilos y una sesión por pedido (`tests/test_finance_import_concurrency.py`, D-034).
- Las consultas de resumen se prueban contra un cálculo de referencia simple en Python (`tests/test_finance_summary_reference.py`); el rendimiento (`@pytest.mark.slow`) imprime medianas con `pytest -s`.

## Cómo correrlas

```bash
docker compose -p contador up -d                 # PostgreSQL de desarrollo
cd backend && .venv/bin/pytest                   # crea contador_test y migra solo
.venv/bin/ruff check . && .venv/bin/mypy app     # lint y tipos estrictos
cd ../frontend && npm test && npm run typecheck && npm run lint
```

## E2E (Playwright)

`@playwright/test` (versión fija en `frontend/package.json`), solo Chromium, en `frontend/e2e/`.

**Qué levanta solo** (`frontend/playwright.config.ts`, `webServer`):
- La API (`python -m app` con `backend/.venv`) en `127.0.0.1:8794`, sobre la base `contador_e2e`. Antes de arrancar, `e2e/reset-db.ts` la **borra y la crea vacía**; la API aplica `alembic upgrade head` al iniciar. Por seguridad, el script solo recrea bases cuyo nombre empieza con `contador_e2e`.
- El frontend: `npm run build` + `vite preview` en `127.0.0.1:5174`, apuntando a esa API (`VITE_API_URL`).

Puertos y base distintos a los de la app (8765 / 5173) para poder correrlo con la app abierta.

**Local:**

```bash
docker compose -p contador up -d                              # PostgreSQL de desarrollo (55433)
cd backend && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # una vez
cd ../frontend && npm ci && npx playwright install chromium   # una vez
npm run e2e                                                   # corre todo y deja playwright-report/
npm run e2e:ui                                                # modo interactivo
npx playwright show-report                                    # reporte HTML de la última corrida
```

Variables opcionales: `CONTADOR_E2E_DB_NAME` (base, por defecto `contador_e2e`), `CONTADOR_E2E_DB_HOST` (`127.0.0.1:55433`), `CONTADOR_E2E_DB_CREDENTIALS` (`contador:contador_dev`).

**En CI:** job `e2e` de `.github/workflows/ci.yml` (Ubuntu, servicio PostgreSQL 18 como el job `test`, Python 3.14, Node 24, `npx playwright install --with-deps chromium`). Si falla, sube `playwright-report/` y `test-results/` (trazas y capturas) como artefacto. No depende del job `windows`.

**Convenciones:**
- Los flujos comparten una base y corren **en orden** (un solo worker): cada uno parte de lo que dejó el anterior (`e2e/flujos.spec.ts`).
- Se localiza por rol y etiqueta accesible (`getByRole`, `getByLabel`), nunca por CSS; si algo no se puede localizar así, es un problema de accesibilidad de la interfaz.
- `e2e/fixtures.ts` hace fallar cualquier prueba con `console.error` o `pageerror`. Un error de consola esperado (el 401 de un ingreso fallido, el corte de red simulado) se declara de forma explícita en la prueba con `test.use({ expectedConsoleErrors: /.../ })`.

- `e2e/finanzas.spec.ts` corre después de `flujos.spec.ts` (proyecto `finanzas` con `dependencies: ['chromium']` en `playwright.config.ts`) y parte de su empresa y usuarios; si se corre solo con la base vacía, los crea por la API.
- `e2e/contabilidad.spec.ts` corre después de `finanzas.spec.ts` (proyecto `contabilidad` con `dependencies: ['finanzas']`): usa las cuentas «Banco E2E» y «Dólares E2E» de la empresa y crea por la API un usuario Administrador. Los flujos que provocan 409/422 esperados los declaran con `expectedConsoleErrors`; los largos van con `test.slow()`.
- Puertos configurables con `CONTADOR_E2E_API_PORT` y `CONTADOR_E2E_WEB_PORT` (por defecto 8794 / 5174), para correr varias copias a la vez.

**Flujos cubiertos:** configuración inicial (empresa + propietario) -> inicio; cierre de sesión y nuevo ingreso; ingreso con contraseña incorrecta sin revelar si el email existe; RUC con DV erróneo y correcto (`44444401` -> `7`); alta de usuarios con rol Contador y Consulta; permisos de cada rol al ingresar; auditoría con cadena íntegra; tema claro/oscuro; servicio local caído ("Iniciando Contador AI…").

**Finanzas** (`finanzas.spec.ts`): alta de cuentas en PYG y USD con saldo inicial en formato paraguayo; contexto en la URL tras recargar; alta manual de salida y entrada; anulación que exige motivo, queda tachada y deja de sumar; transferencia (dos movimientos enlazados, sin categoría); importación de un CSV con títulos del banco, un duplicado contra la base y una fila con fecha inválida (nada se crea hasta confirmar; se omite una fila; los importados quedan sin revisar); `IMPORT_NEW_DUPLICATES` cuando aparece un movimiento igual entre el análisis y la confirmación; resumen con un bloque por moneda sin mezclar ₲ y US$ y consolidado; privacidad del contexto personal (el Contador recibe "no existe" en la interfaz y 404 en la API; Consulta lee la empresa sin botones de escritura y opera su propio espacio).

**Contabilidad** (`contabilidad.spec.ts`): carga del plan propuesto (159 cuentas) con el aviso «sin validar» en el plan y en el resto de las pantallas, búsqueda por código y cuenta de resultados del ejercicio; ejercicio 2026 con 12 períodos; asiento manual desbalanceado (se ve la diferencia y no se contabiliza), balanceado y contabilizado como N° 1, y revertido (N° 2, enlaces en los dos sentidos); asiento propuesto desde un movimiento de la empresa configurando en el momento las cuentas contables del banco y de la categoría, contabilizado como N° 3, enlace al movimiento de origen, y el movimiento ya no se puede anular (aviso con enlace al asiento); movimiento en dólares con cotización y elección de redondeo; libro diario, mayor, balance de comprobación, balance general y estado de resultados con totales conocidos; período con borradores que no cierra (lista con enlace), descarte con motivo, cierre, asiento en el período cerrado que no se contabiliza, reapertura con motivo y contabilización; el Administrador guarda borradores pero no ve «Contabilizar» ni «Marcar como validado»; Consulta solo lee; validación del plan con nombre y matrícula y reportes sin aviso.

**Unitarias de contabilidad** (Vitest, `src/modules/accounting/*.test.ts`): sumas y restas de importes con BigInt, producto exacto con la cotización, lectura de cotizaciones en formato paraguayo; balance en vivo del editor, línea nueva con la diferencia, armado del cuerpo con errores por línea; árbol del plan, orden por código, búsqueda y código sugerido para una subcuenta; cuándo se puede proponer un asiento y cuándo un asiento contabilizado bloquea el movimiento.

**Unitarias de finanzas** (Vitest): formato y lectura de importes (`lib/money.test.ts`), DV del RUC, cliente HTTP con `FormData` y `qs`, lectura de CSV y mapeo de columnas (`importMapping.test.ts`), lectura mínima de XLSX con un ZIP armado en la prueba (`xlsxPreview.test.ts`) y conteo/filtros de filas importadas (`importRows.test.ts`).

## Estado actual (2026-11-24, interfaz de contabilidad)
- Frontend: **90 pruebas** Vitest pasan (36 de contabilidad); `tsc -b` sin errores; oxlint con las mismas 2 advertencias de antes.
- E2E: **27 pruebas** (10 de `flujos.spec.ts` + 8 de `finanzas.spec.ts` + 9 de `contabilidad.spec.ts`), dos corridas seguidas en verde (52 y 62 s).
- No tiene E2E (probado a mano): cierre del ejercicio con refundición, alta y edición de subcuentas, archivo de cuentas, vuelta del plan a «sin validar».

## Estado anterior (2026-11-24, interfaz de finanzas)
- Frontend: **53 pruebas** Vitest pasan; `tsc -b` sin errores; oxlint con las mismas 2 advertencias de antes.
- E2E: **18 pruebas** (10 de `flujos.spec.ts` + 8 de `finanzas.spec.ts`), ~30 s por corrida.

## Estado anterior (2026-11-23)
- Backend: **28 pruebas** pasan; ruff y mypy (`strict`) sin errores; `alembic check` sin diferencias; migración reversible.
- Frontend: **10 pruebas** pasan; `tsc -b` sin errores; oxlint con 2 advertencias de recarga en caliente (hooks junto a sus providers), sin errores.
- E2E: **10 pruebas** de Playwright en `frontend/e2e/` (ver arriba), Chromium con base aislada, sin errores de consola; corren en el job `e2e` del CI.
