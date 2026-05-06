"""Lee bytes del CAF (adjunto) para `parse_autorizacion_bytes`."""

from __future__ import annotations

import frappe

from pagosbf.pagosbf.dte.caf_parser import CAFData, parse_autorizacion_bytes


def load_caf_data(caf_name: str) -> CAFData:
	"""Carga y parsea el XML de autorizacion vinculado al DocType `CAF`."""
	doc = frappe.get_doc("CAF", caf_name)
	url = (doc.xml_caf or "").strip()
	if not url:
		frappe.throw(f"CAF {caf_name!r} no tiene `xml_caf` adjunto.")
	fname = frappe.db.get_value("File", {"file_url": url}, "name")
	if not fname:
		frappe.throw(f"No se localiza File para {url!r}.")
	return parse_autorizacion_bytes(frappe.get_doc("File", fname).get_content())


__all__ = ["load_caf_data"]
