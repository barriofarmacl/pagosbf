# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Datos para print formats que enlazan POS Invoice con DTE Boleta (SII)."""

from __future__ import annotations

import html
from typing import Any

from lxml import etree

from pagosbf.pagosbf.dte.ted_generator import serialize_ted_for_pdf417


def _maybe_unescape_xml_field(s: str) -> str:
	"""Algunos caminos de persistencia devuelven XML con entidades HTML (&lt;...&gt;)."""
	t = s.strip().lstrip("\ufeff")
	if "&lt;" not in t[:500] and "&amp;lt;" not in t[:800]:
		return t
	for _ in range(6):
		u = html.unescape(t)
		if u == t:
			return u
		t = u
	return t


def _parse_dte_xml_root(xml_str: str | None) -> etree._Element | None:
	if not xml_str or not str(xml_str).strip():
		return None
	raw = _maybe_unescape_xml_field(str(xml_str))
	strict = etree.XMLParser(resolve_entities=False, recover=False)
	loose = etree.XMLParser(resolve_entities=False, recover=True)
	for enc in ("utf-8", "iso-8859-1"):
		try:
			payload = raw.encode(enc)
		except UnicodeEncodeError:
			continue
		for parser in (strict, loose):
			try:
				return etree.fromstring(payload, parser=parser)
			except etree.XMLSyntaxError:
				continue
	return None


def _find_ted_element(root: etree._Element) -> etree._Element | None:
	for el in root.iter():
		if isinstance(el.tag, str) and etree.QName(el.tag).localname == "TED":
			return el
	return None


def get_pos_invoice_sii_block(doc: Any) -> dict[str, Any] | None:
	"""Devuelve filas de `DTE Boleta` y timbre compacto para el ticket, o None."""
	import frappe

	name = getattr(doc, "name", None) or str(doc)
	if not name:
		return None
	row = frappe.db.get_value(
		"DTE Boleta",
		{"pos_invoice": name},
		[
			"name",
			"tipo_dte",
			"folio",
			"track_id",
			"estado_envio",
			"fecha_emision",
			"sii_cod_ref",
			"sii_razon_ref",
		],
		as_dict=True,
	)
	if not row:
		return None
	# Long Text: leer desde el documento (evita lecturas incompletas en algunos caminos de test/ORM).
	bol = frappe.get_doc("DTE Boleta", row["name"])
	xml = bol.get("xml_dte_firmado")
	rut_raw = (frappe.db.get_single_value("SII Configuration", "rut_emisor") or "").strip()
	row["rut_emisor_fmt"] = _format_rut_display(rut_raw)
	root = _parse_dte_xml_root(xml)
	row["ted_compact"] = _ted_compact_from_root(root)
	row["ted_pdf417_payload"] = _ted_pdf417_from_root(root)
	return row


def _format_rut_display(rut: str) -> str:
	r = (rut or "").replace(".", "").replace(" ", "").upper()
	if not r:
		return ""
	if "-" in r:
		return r
	if len(r) < 2:
		return r
	return f"{r[:-1]}-{r[-1]}"


def _ted_compact_from_root(root: etree._Element | None, max_len: int = 520) -> str:
	if root is None:
		return ""
	ted = _find_ted_element(root)
	if ted is None:
		return ""
	s = etree.tostring(ted, encoding="unicode", method="xml")
	s = " ".join(s.split())
	if len(s) > max_len:
		return s[: max_len - 1] + "…"
	return s


def _ted_pdf417_from_root(root: etree._Element | None) -> str:
	if root is None:
		return ""
	ted = _find_ted_element(root)
	if ted is None:
		return ""
	return serialize_ted_for_pdf417(ted)


def extract_ted_compact(xml_str: str | None, max_len: int = 520) -> str:
	"""Una sola linea con el nodo TED (timbre) para ticket termico; truncado."""
	return _ted_compact_from_root(_parse_dte_xml_root(xml_str), max_len=max_len)


__all__ = ["extract_ted_compact", "get_pos_invoice_sii_block"]
