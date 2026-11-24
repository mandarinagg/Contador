#!/usr/bin/env bash
# Busca secretos con gitleaks (vía Docker). El repositorio es PÚBLICO.
#   scripts/check-secrets.sh            → cambios preparados (git add); lo usa el hook pre-commit
#   scripts/check-secrets.sh --all      → todo el historial
# Instalar el hook:  scripts/check-secrets.sh --install
set -euo pipefail

ROOT="$(git -C "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" rev-parse --show-toplevel)"
IMAGE="ghcr.io/gitleaks/gitleaks:v8.30.1"

if [[ "${1:-}" == "--install" ]]; then
  ln -sf ../../scripts/check-secrets.sh "$ROOT/.git/hooks/pre-commit"
  echo "Hook pre-commit instalado: cada commit se revisa con gitleaks."
  exit 0
fi

if ! command -v docker >/dev/null; then
  echo "ERROR: hace falta Docker para revisar secretos. Commit cancelado." >&2
  exit 1
fi

args=(git /repo --config /repo/.gitleaks.toml --redact --no-banner)
[[ "${1:-}" == "--all" ]] || args+=(--pre-commit --staged)

# safe.directory: el contenedor corre con otro usuario que el dueño del repositorio.
if ! docker run --rm -v "$ROOT:/repo" \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/repo \
  "$IMAGE" "${args[@]}"; then
  echo "" >&2
  echo "gitleaks encontró posibles secretos: el repositorio es PÚBLICO, el commit se canceló." >&2
  echo "Si es un falso positivo de pruebas, agregalo a .gitleaks.toml." >&2
  exit 1
fi
