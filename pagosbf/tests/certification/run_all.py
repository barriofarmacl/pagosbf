# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Runner offline del set de certificacion SII (build + TED + XSD).

Validacion contra maullin / EPR es paso aparte (Verify / E2E manual).

bench --site <sitio> execute pagosbf.tests.certification.run_all.run
"""

from __future__ import annotations

import json

from pagosbf.pagosbf.dte import ted_generator, xml_builder
from pagosbf.pagosbf.dte.types import DTEBoletaData
from pagosbf.tests.certification.fixtures.load_cases import iter_cases
from pagosbf.tests.dte_fixtures import FIXED_DATE, FIXED_TS, emisor, receptor, synthetic_caf


def _validate_one(_case_id: str, data: DTEBoletaData) -> None:
	caf = synthetic_caf(data.tipo_dte)
	draft = xml_builder.build_dte(data)
	ted = ted_generator.build_signed_ted(draft.dd_data, caf, data.timestamp_firma)
	xml_bytes = xml_builder.insert_ted(draft, ted, data.timestamp_firma)
	xml_builder.validate_dte_xml(xml_bytes)


def run_offline_suite() -> dict:
	"""Ejecuta todos los casos del manifest (offline)."""
	cases = iter_cases(emisor, receptor, FIXED_DATE, FIXED_TS)
	ok: list[str] = []
	errors: list[dict[str, str]] = []
	for c in cases:
		try:
			_validate_one(c.case_id, c.data)
			ok.append(c.case_id)
		except Exception as e:  # noqa: BLE001
			errors.append({"case_id": c.case_id, "error": f"{type(e).__name__}: {e}"})

	return {
		"mode": "offline_xsd",
		"total": len(cases),
		"ok_count": len(ok),
		"fail_count": len(errors),
		"ok": ok,
		"errors": errors,
	}


def run() -> str:
	"""Entrypoint bench execute: imprime JSON legible."""
	out = run_offline_suite()
	lines = [json.dumps(out, indent=2, ensure_ascii=False)]
	if out["fail_count"]:
		lines.append("")
		lines.append("Fallaron casos offline; revisar manifest.json y builders antes de maullin.")
	else:
		lines.append("")
		lines.append(
			"Offline OK: XML+XSD por caso. Siguiente paso contra SII: E2E_MANUAL.md + verify-report.md."
		)
	return "\n".join(lines)
