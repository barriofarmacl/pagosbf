#!/usr/bin/env bash
# Smoke suite: todos los test_*.py bajo pagosbf/tests (objetivo PR / verificacion local).
#
# Importante: `bench run-tests --module pagosbf.tests` (solo el paquete padre) puede no
# descubrir test_*.py como hace unittest discover; por eso se lanza un --module por archivo.
# Contrato de equipo: ver `.cursor/openspec/specs/testing/barriofarma-backend-tests.md`.
#
# Uso: desde frappe-bench: ./apps/pagosbf/scripts/run_smoke_tests.sh [SITE]
set -euo pipefail

SITE="${1:-barriofarma.localhost}"
# bench solo hace sys.exit(!=0) ante fallos de test si CI esta definido (frappe/commands/utils.py).
export CI="${CI:-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BENCH_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TESTS_ROOT="$APP_ROOT/pagosbf/tests"

cd "$BENCH_ROOT"

shopt -s nullglob
files=("$TESTS_ROOT"/test_*.py)
shopt -u nullglob

if ((${#files[@]} == 0)); then
	echo "run_smoke_tests: no hay test_*.py en $TESTS_ROOT" >&2
	exit 1
fi

for py in "${files[@]}"; do
	base=$(basename "$py" .py)
	mod="pagosbf.tests.$base"
	echo "==> smoke: $mod"
	bench --site "$SITE" run-tests --app pagosbf --module "$mod"
done

echo "run_smoke_tests: OK (${#files[@]} modulos)"
