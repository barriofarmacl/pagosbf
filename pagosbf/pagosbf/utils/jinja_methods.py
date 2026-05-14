# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Funciones Jinja globales para Print Format (POS Boleta SII). Registradas en ``pagosbf`` hooks."""

from __future__ import annotations

import html
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


def _first_address_name_for_company(company: str) -> str | None:
	"""Cualquier Address activa enlazada a Company (no exige bandera primaria)."""
	row = frappe.db.sql(
		"""
		SELECT dl.parent
		FROM `tabDynamic Link` dl
		INNER JOIN `tabAddress` addr ON addr.name = dl.parent
		WHERE dl.parenttype = 'Address'
		  AND dl.link_doctype = 'Company'
		  AND dl.link_name = %(company)s
		  AND IFNULL(addr.disabled, 0) = 0
		ORDER BY IFNULL(addr.is_primary_address, 0) DESC,
		         IFNULL(addr.is_shipping_address, 0) DESC,
		         addr.modified DESC
		LIMIT 1
		""",
		{"company": company},
	)
	return row[0][0] if row else None


def _address_plain_br(address_name: str) -> str:
	"""Lineas de direccion sin plantilla Address (evita fallos de template en impresion)."""
	try:
		a = frappe.get_cached_doc("Address", address_name)
	except Exception:
		return ""
	parts: list[str] = []
	for fn in ("address_line1", "address_line2", "city", "state", "pincode", "country"):
		v = (a.get(fn) or "").strip()
		if v:
			parts.append(html.escape(v))
	return "<br>".join(parts) if parts else ""


def company_address_display(company: str | None) -> str:
	"""Direccion de la Company para boleta POS; vacio si no hay Address enlazada.

	Orden: direccion primaria, despacho, cualquier Address enlazada a la Company.
	Si ``render_address`` falla (plantilla), usa lineas planas del Address.
	"""
	if not company:
		return ""
	try:
		from frappe.contacts.doctype.address.address import get_default_address, render_address
	except Exception:
		return ""

	addr_name = get_default_address("Company", company, "is_primary_address")
	if not addr_name:
		addr_name = get_default_address("Company", company, "is_shipping_address")
	if not addr_name:
		addr_name = _first_address_name_for_company(company)
	if not addr_name:
		return ""

	try:
		rendered = render_address(addr_name, check_permissions=False)
		if rendered and str(rendered).strip():
			return str(rendered).strip()
	except Exception:
		pass
	return _address_plain_br(addr_name)


__all__ = ["company_address_display", "pos_invoice_sii_print_block"]
