# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Comprueba prerequisitos en el sitio antes de un E2E de emision SII.

Uso (desde el bench):
  bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.run

Nota: ``bench execute`` solo acepta una ruta ``modulo.atributo`` o una expresion ``eval``;
no admite bloques multilinea con ``import``. Para scripts libres usar ``bench console``.

Importante: si ``frappe.get_attr(...)(...)`` lanza, el comando ``execute`` de Frappe hace un
fallback ``eval(method + "(...)")`` donde ``method`` no resuelve namespaces con punto;
termina en ``NameError: pagosbf is not defined``. Por eso estos wrappers capturan excepciones
y devuelven JSON con ``ok: false`` en lugar de propagar.
"""

from __future__ import annotations

import json

import frappe


def run() -> str:
	"""Imprime resumen legible; retorna JSON string para --execute."""
	out: dict = {"ok": True, "errores": [], "aviso": []}
	try:
		c = frappe.get_single("SII Configuration")
		out["sii_razon_social"] = c.get("razon_social")
		if not c.get("rut_emisor"):
			out["errores"].append("SII Configuration.rut_emisor vacio")
		if not c.get("certificado_digital"):
			out["errores"].append("SII Configuration sin certificado_digital")
		caf_39 = frappe.get_all("CAF", filters={"tipo_dte": "39", "agotado": 0}, limit=1)
		caf_41 = frappe.get_all("CAF", filters={"tipo_dte": "41", "agotado": 0}, limit=1)
		out["caf_39"] = bool(caf_39)
		out["caf_41"] = bool(caf_41)
		if not caf_39 and not caf_41:
			out["errores"].append("Sin CAF no agotado (39 ni 41)")
		for lab, rows in (("39", caf_39), ("41", caf_41)):
			if rows:
				out[f"caf_tipo_{lab}_name"] = rows[0].name
	except Exception as e:  # noqa: BLE001
		out["ok"] = False
		out["errores"].append(f"SII Configuration: {e!s}")
	lines = [json.dumps(out, indent=2, ensure_ascii=False)]
	lines.append("")
	lines.append("Worker: si usas en_background=1, revisa RQ/scheduler y cola 'default'.")
	return "\n".join(lines)


def check_pos_invoice_dte39_ready(pos_invoice: str) -> str:
	"""Comprueba POS Invoice enviada con IVA > 0 (requisito para DTE 39).

	Uso:
	  bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.check_pos_invoice_dte39_ready \\
	    --args '["ACC-PSINV-2026-00001"]'
	"""
	out: dict = {
		"ok": True,
		"errores": [],
		"pos_invoice": pos_invoice,
		"docstatus": None,
		"net_total": None,
		"total_taxes_and_charges": None,
		"grand_total": None,
	}
	try:
		d = frappe.get_doc("POS Invoice", pos_invoice)
		out["docstatus"] = d.docstatus
		out["net_total"] = d.net_total
		out["total_taxes_and_charges"] = d.total_taxes_and_charges
		out["grand_total"] = d.grand_total
		if d.docstatus != 1:
			out["ok"] = False
			out["errores"].append(
				f"docstatus={d.docstatus} (se espera 1 = enviado).",
			)
		if float(d.total_taxes_and_charges or 0) <= 0:
			out["ok"] = False
			out["errores"].append(
				"total_taxes_and_charges debe ser > 0 para boleta afecta (DTE 39).",
			)
	except Exception as e:  # noqa: BLE001
		out["ok"] = False
		out["errores"].append(str(e))
	return json.dumps(out, indent=2, ensure_ascii=False)


def e2e_emitir_pos_invoice(
	pos_invoice: str,
	caf: str | None = None,
	en_background: int = 0,
) -> str:
	"""Llama ``emitir`` como Administrator (tipico en ``bench execute`` sin sesion web).

	Uso:
	  bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_emitir_pos_invoice \\
	    --kwargs \"{'pos_invoice': 'ACC-PSINV-...', 'en_background': 0}\"

	Con CAF explicito:
	  --kwargs \"{'pos_invoice': '...', 'caf': 'CAF-39-...', 'en_background': 0}\"
	"""
	frappe.set_user("Administrator")
	from pagosbf.pagosbf.api.boleta import emitir

	try:
		r = emitir(
			pos_invoice=pos_invoice,
			caf=caf,
			en_background=en_background,
		)
		out: dict = {"ok": True, "resultado": r, "pos_invoice": pos_invoice}
	except Exception as e:  # noqa: BLE001
		out = {"ok": False, "pos_invoice": pos_invoice, "error": str(e)}
	return json.dumps(out, indent=2, ensure_ascii=False, default=str)


def e2e_emitir_sales_invoice(
	sales_invoice: str,
	caf: str | None = None,
	en_background: int = 0,
) -> str:
	"""Igual que ``e2e_emitir_pos_invoice`` pero con ``sales_invoice`` (origen alternativo)."""
	frappe.set_user("Administrator")
	from pagosbf.pagosbf.api.boleta import emitir

	try:
		r = emitir(
			sales_invoice=sales_invoice,
			caf=caf,
			en_background=en_background,
		)
		out: dict = {"ok": True, "resultado": r, "sales_invoice": sales_invoice}
	except Exception as e:  # noqa: BLE001
		out = {"ok": False, "sales_invoice": sales_invoice, "error": str(e)}
	return json.dumps(out, indent=2, ensure_ascii=False, default=str)


def e2e_consultar_estado_dte(dte_boleta: str) -> str:
	"""Wrapper para ``consultar_estado`` con usuario Administrator.

	Uso:
	  bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_consultar_estado_dte \\
	    --args '[\"BOL-39-00001\"]'
	"""
	frappe.set_user("Administrator")
	from pagosbf.pagosbf.api.boleta import consultar_estado

	try:
		r = consultar_estado(dte_boleta)
		out: dict = {"ok": True, "resultado": r, "dte_boleta": dte_boleta}
	except Exception as e:  # noqa: BLE001
		out = {"ok": False, "dte_boleta": dte_boleta, "error": str(e)}
	return json.dumps(out, indent=2, ensure_ascii=False, default=str)
