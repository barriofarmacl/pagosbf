#!/usr/bin/env bash
# Fail if barriofarma_app Python tree imports pagosbf directly (boundary).
# Usage: from pagosbf repo root, with bench sibling apps:
#   BARRIOFARMA_APP_ROOT=../barriofarma_app ./scripts/check_no_pagosbf_imports_barriofarma.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BF_ROOT="${BARRIOFARMA_APP_ROOT:-${ROOT}/../barriofarma_app}"
PAT='^\s*(from|import)\s+pagosbf\b'
PATHS=()
if [[ -d "${BF_ROOT}/barriofarma_app" ]]; then
	PATHS+=("${BF_ROOT}/barriofarma_app")
fi
if [[ ${#PATHS[@]} -eq 0 ]]; then
	echo "SKIP: barriofarma_app not found at ${BF_ROOT} (set BARRIOFARMA_APP_ROOT)"
	exit 0
fi
if command -v rg >/dev/null 2>&1; then
	if rg --line-number --glob '*.py' "${PAT}" "${PATHS[@]}"; then
		echo "ERROR: direct imports from pagosbf are forbidden under ${PATHS[*]}" >&2
		exit 1
	fi
else
	if grep -RIn --include='*.py' -E "${PAT}" "${PATHS[@]}"; then
		echo "ERROR: direct imports from pagosbf are forbidden under ${PATHS[*]}" >&2
		exit 1
	fi
fi
echo "OK: no forbidden pagosbf imports under ${PATHS[*]}"
