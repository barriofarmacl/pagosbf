# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Funciones Jinja globales para Print Format (POS Boleta SII). Registradas en ``pagosbf`` hooks."""

from __future__ import annotations

from typing import Any

import frappe


def pos_invoice_sii_print_block(doc: Any) -> dict[str, Any] | None:
	"""Datos DTE/timbre para POS Invoice vía APIs internas (mismo contrato que Desk whitelisted).

	Usado por Print Format Jinja; evita ``frappe.get_attr`` en plantillas (sandbox sin ese atributo).
	"""
	from pagosbf.pagosbf.api.boleta import datos_impresion_boleta_pos, timbre_pdf417_data_url

	name = getattr(doc, "name", None) or (doc.get("name") if isinstance(doc, dict) else None)
	if not name:
		return None
	data = datos_impresion_boleta_pos(pos_invoice=name)
	if not data or not data.get("ok"):
		return None
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
	if not (blk.get("ted_pdf417_payload") or "").strip():
		return blk
	try:
		du = timbre_pdf417_data_url(pos_invoice=name)
	except Exception:
		return blk
	if du and du.get("ok") and du.get("data_url"):
		out = dict(blk)
		out["timbre_pdf417_data_url"] = du["data_url"]
		return out
	return blk


__all__ = ["pos_invoice_sii_print_block"]
