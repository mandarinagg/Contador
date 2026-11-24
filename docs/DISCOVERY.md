# Fase 0 — Discovery y auditoría

Fecha: 2026-11-23. Responsable: Claude (rol de responsable técnico).

## 1. Diagnóstico del entorno

| Herramienta | Versión encontrada | Estado | Uso en el proyecto |
|---|---|---|---|
| Ubuntu | 26.04.1 LTS, x86_64, 8 núcleos, 10 GiB RAM | OK | Desarrollo y empaquetado Linux |
| Disco | 34 GiB libres (85 % usado) | **Atención** | Rust + Tauri + PostgreSQL embebido ocupan varios GB |
| Node.js / npm | 24.18.0 / 11.16.0 | OK | Frontend, Tauri CLI, servicio SIFEN |
| pnpm | 12.21.0 | Disponible | No se usa (npm alcanza; ver DECISIONS D-011) |
| Python | 3.14.4 (+ venv) | OK | Backend. Stack verificado en 3.14 |
| uv / poetry | — | No instalados | No hacen falta (venv + pip con versiones fijas) |
| Docker / Compose | 29.8.0 / v5.5.1 | OK | Solo PostgreSQL de **desarrollo** |
| PostgreSQL (cliente) | — | No instalado | Se usa por Docker (`postgres:18-alpine`, 18.7) |
| Rust / cargo | — | **Faltan** | Necesarios para compilar Tauri |
| pkg-config, libwebkit2gtk-4.1-dev, librsvg2-dev, libssl-dev | — | **Faltan** (solo está el runtime de webkit) | Necesarios para compilar Tauri en Linux |
| Tesseract | — | No instalado | OCR, fase 5 |
| Git | 2.53.0 | OK | |

### Repositorios detectados

| Ruta | Estado | Observación |
|---|---|---|
| `~/Escritorio/proyectos/Contador/Contador` | Clon de `github.com/mandarinagg/Contador`, rama `main`, sin commits | **Repositorio de trabajo** |
| `~/Escritorio/proyectos/Contador` | `git init` sin remoto ni commits, contiene el clon | Repositorio anidado accidental. Ver riesgo R-10 |
| `~/` (carpeta personal) | Es un repositorio git sin commits | Ver riesgo R-11: `.git-credentials` y otros archivos sensibles aparecen como "no rastreados" |
| `~/Escritorio/facturacion-sifen-zestia` | Sin commits ni `package.json` | Extracto del módulo de facturación (auditado, no modificado) |
| `~/Escritorio/proyectos/delivery/zestia-delivery` | Monorepo Zestia Delivery | **No** contiene el código SIFEN en ninguna rama local |

### Servicios activos que conviven
- `zestia-delivery-postgres-1` en `127.0.0.1:55432` y `mailpit`. CONTADOR AI usa `127.0.0.1:55433` para no chocar.

## 2. Arquitectura recomendada
Ver `docs/ARCHITECTURE.md`. Resumen: app Tauri 2 que lanza un backend FastAPI local (sidecar) contra PostgreSQL local; el módulo SIFEN existente se reutiliza como servicio Node separado detrás de un adaptador.

## 3. Estructura de carpetas
Ver `docs/ARCHITECTURE.md § Estructura`.

## 4. Modelo entidad-relación inicial
Ver `docs/DATABASE_SCHEMA.md` (implementado en fase 1 + modelo objetivo de fases 2 a 7).

## 5. Plan de implementación
Ver `docs/ROADMAP.md`.

## 6. Riesgos técnicos

| ID | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R-01 | PostgreSQL en una app de escritorio: instalar y operar una base de datos en la PC del usuario | Alta | Alto | Binarios portables oficiales de PostgreSQL 18.7 para Windows (verificados) administrados por la app. Adelantado a la fase 1B (D-017) y probado en CI sobre Windows real. |
| R-02 | Dos runtimes empaquetados (Python + Node para SIFEN) | Media | Medio | Backend con PyInstaller y servicio SIFEN como ejecutable único de Node (SEA). Se mide el tamaño del instalador en fase 8. |
| R-03 | El módulo SIFEN no corre fuera del CRM de Zestia (faltan 30+ archivos de infraestructura y los helpers de prueba) | Cierta | Alto | Reutilizar el núcleo `sifen/*` tal cual y reescribir solo la orquestación desacoplada de pedidos. Pedir el repositorio original del CRM. Ver `INTEGRATIONS.md`. |
| R-04 | Rutas y códigos del SIFEN marcados "por confirmar" en el proyecto original; nunca se probó contra el SIFEN de pruebas real | Cierta | Alto | Prueba contra `sifen-test.set.gov.py` con timbrado de prueba y certificado real antes de producción. |
| R-05 | Régimen tributario y actividad económica sin verificar | Cierta | Alto | Motor de reglas versionado con estado "pendiente"; ninguna obligación se activa sin verificación (BUSINESS_RULES BR-TAX-*). |
| R-06 | Python 3.14 y TypeScript 7 son versiones recientes; alguna dependencia puede no soportarlas | Media | Medio | Versiones fijas y verificadas (pyproject, package.json exactos). CI con la misma versión. |
| R-07 | Pérdida de datos local (disco, borrado, ransomware) | Media | Muy alto | Copias de seguridad cifradas programadas y prueba de restauración (fase 8, pero el diseño de datos ya lo contempla). |
| R-08 | Fuga de datos hacia la API de Claude | Media | Alto | Herramientas backend con permisos, minimización del contexto, registro de cada llamada, nunca SQL generado por IA (fase 6). |
| R-09 | Compilación de Tauri bloqueada por dependencias del sistema | Cierta hoy | Medio | El propietario instala Rust y las librerías (comandos en README). Mientras tanto se desarrolla con el navegador. |
| R-10 | Repositorio git anidado en `proyectos/Contador` | Cierta | Bajo | Trabajar solo en `Contador/Contador`. El propietario decide si borra el `.git` externo. |
| R-11 | La carpeta personal es un repositorio git (incluye `.git-credentials` sin rastrear) | Cierta | Alto | Un `git add .` accidental en `~` subiría credenciales. Recomendación: eliminar `~/.git` si no es intencional. No se tocó. |
| R-12 | Disco al 85 % | Media | Medio | Liberar espacio antes de instalar Rust/targets (≈ 3-5 GB). |

## 7. Dependencias necesarias
Ver `docs/ARCHITECTURE.md § Dependencias` (cada una con su justificación y versión fija).

## 8. Variables de entorno
Ver `.env.example` y `docs/SECURITY.md § Secretos`.

## 9. Estrategia de pruebas
Ver `docs/TESTING_STRATEGY.md`.

## 10. Plan de distribución
Ver `docs/ARCHITECTURE.md § Distribución`.

## Decisiones pendientes del propietario
Ver `docs/PROJECT_STATUS.md § Información requerida`.
