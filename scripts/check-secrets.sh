#!/usr/bin/env bash
# Busca secretos con gitleaks (vía Docker). El repositorio es PÚBLICO.
#   scripts/check-secrets.sh            → cambios preparados (git add); lo usa el hook pre-commit
#   scripts/check-secrets.sh --all      → todo el historial
# Instalar el hook:  scripts/check-secrets.sh --install
set -euo pipefail

# El repositorio es el del directorio actual (git ejecuta los hooks en la raíz del árbol
# de trabajo), no el del script: así funciona también en worktrees adicionales.
ROOT="$(git rev-parse --show-toplevel)"
# En un worktree, `.git` es un archivo que apunta al directorio git común: hay que montarlo.
GIT_COMMON="$(cd "$ROOT" && cd "$(git rev-parse --git-common-dir)" && pwd)"
IMAGE="ghcr.io/gitleaks/gitleaks:v8.30.1"

if [[ "${1:-}" == "--install" ]]; then
  ln -sf ../../scripts/check-secrets.sh "$GIT_COMMON/hooks/pre-commit"
  echo "Hook pre-commit instalado: cada commit se revisa con gitleaks."
  exit 0
fi

if ! command -v docker >/dev/null; then
  echo "ERROR: hace falta Docker para revisar secretos. Commit cancelado." >&2
  exit 1
fi

args=(git "$ROOT" --config "$ROOT/.gitleaks.toml" --redact --no-banner)
[[ "${1:-}" == "--all" ]] || args+=(--pre-commit --staged)

# Se montan con la misma ruta que en el equipo para que el archivo `.git` de un worktree
# siga apuntando a un lugar válido. safe.directory: el contenedor corre con otro usuario.
mounts=(-v "$ROOT:$ROOT")
[[ "$GIT_COMMON" == "$ROOT/.git" ]] || mounts+=(-v "$GIT_COMMON:$GIT_COMMON")
if ! docker run --rm "${mounts[@]}" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0='*' \
  "$IMAGE" "${args[@]}"; then
  echo "" >&2
  echo "gitleaks encontró posibles secretos: el repositorio es PÚBLICO, el commit se canceló." >&2
  echo "Si es un falso positivo de pruebas, agregalo a .gitleaks.toml." >&2
  exit 1
fi
