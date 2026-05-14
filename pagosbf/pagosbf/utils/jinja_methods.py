# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Funciones Jinja globales para Print Format (POS Boleta SII). Registradas en ``pagosbf`` hooks."""

from __future__ import annotations

from typing import Any

import frappe


def pos_invoice_sii_print_block(doc: Any) -> dict[str, Any]:
	"""Datos DTE/timbre para POS Invoice (Print Format Jinja).

	Siempre retorna un ``dict`` con banderas ``sii_ready`` / ``sii_sin_dte`` para que la plantilla
	no asuma "pendiente" ambiguo: sin DTE se exige paso ``emitir``; con DTE sin TED se indica reintento.
	"""
	from pagosbf.pagosbf.api.boleta import datos_impresion_boleta_pos, timbre_pdf417_data_url

	name = getattr(doc, "name", None) or (doc.get("name") if isinstance(doc, dict) else None)
	if not name:
		return {
			"sii_ready": False,
			"sii_sin_dte": True,
			"mensaje_print": "Documento POS sin identificador.",
		}
	data = datos_impresion_boleta_pos(pos_invoice=name)
	if not data or not data.get("ok"):
		msg = (data or {}).get("mensaje") or "Sin DTE Boleta vinculada."
		return {
			"sii_ready": False,
			"sii_sin_dte": True,
			"mensaje_print": msg,
			"pos_invoice": name,
		}
	dte = data.get("dte_boleta")
	blk: dict[str, Any] = {
		"tipo_dte": data.get("tipo_dte"),
		"folio": data.get("folio"),
		"track_id": data.get("track_id"),
		"estado_envio": data.get("estado_envio"),
		"rut_emisor_fmt": data.get("rut_emisor_fmt"),
		"fecha_emision": data.get("fecha_emision"),
		"sii_cod_ref": data.get("sii_cod_ref"),
		"sii_razon_ref": data.get("sii_razon_ref"),
		"dte_boleta": dte,
		"name": dte,
		"ted_compact": data.get("ted_compact"),
		"ted_pdf417_payload": data.get("ted_pdf417_payload"),
	}
	payload = (blk.get("ted_pdf417_payload") or "").strip()
	if payload:
		try:
			du = timbre_pdf417_data_url(pos_invoice=name)
		except Exception:
			du = None
		if du and du.get("ok") and du.get("data_url"):
			blk = dict(blk)
			blk["timbre_pdf417_data_url"] = du["data_url"]
	out = dict(blk)
	out["sii_ready"] = True
	out["sii_sin_dte"] = False
	out["tiene_timbre"] = bool(
		(out.get("timbre_pdf417_data_url") or "").strip()
		or (out.get("ted_pdf417_payload") or "").strip()
	)
	return out


__all__ = ["pos_invoice_sii_print_block"]
