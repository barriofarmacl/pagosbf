#!/usr/bin/env bash
# Fail if pagosbf Python code imports barriofarma_app directly (SDD R2).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${ROOT}/pagosbf"
if command -v rg >/dev/null 2>&1; then
	if rg --line-number --glob '*.py' '^\s*(from|import)\s+barriofarma_app\b' "${TARGET}"; then
		echo "ERROR: direct imports from barriofarma_app are forbidden under pagosbf/ (use hooks or @frappe.whitelist API)." >&2
		exit 1
	fi
else
	# Portable fallback (dev containers may lack ripgrep)
	if grep -RIn --include='*.py' -E '^\s*(from|import)\s+barriofarma_app\b' "${TARGET}"; then
		echo "ERROR: direct imports from barriofarma_app are forbidden under pagosbf/ (use hooks or @frappe.whitelist API)." >&2
		exit 1
	fi
fi
echo "OK: no forbidden barriofarma_app imports under ${TARGET}"
