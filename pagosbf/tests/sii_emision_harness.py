# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Helpers para tests Frappe de emision/consulta SII (SII Configuration + CAF + Certificado)."""

from __future__ import annotations

import base64
from datetime import date
from typing import Any

import frappe
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pagosbf.pagosbf.dte.caf_parser import parse_autorizacion_bytes

from .dte_fixtures import pfx_for_tests


def synthetic_autorizacion_bytes(tipo: int = 39) -> bytes:
	"""AUTORIZACION con RSA sintetica (mismo patron que test_caf_parser)."""
	key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
	pub = key.public_key().public_numbers()
	n_bytes = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
	e_bytes = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
	m_b64 = base64.b64encode(n_bytes).decode("ascii")
	e_b64 = base64.b64encode(e_bytes).decode("ascii")
	priv_pem = key.private_bytes(
		serialization.Encoding.PEM,
		serialization.PrivateFormat.TraditionalOpenSSL,
		serialization.NoEncryption(),
	).decode("ascii")
	xml = f"""<?xml version="1.0"?>
<AUTORIZACION>
<CAF version="1.0">
<DA>
<RE>76000000-0</RE>
<RS>Test SA</RS>
<TD>{tipo}</TD>
<RNG><D>1</D><H>100</H></RNG>
<FA>2026-01-15</FA>
<RSAPK><M>{m_b64}</M><E>{e_b64}</E></RSAPK>
<IDK>100</IDK>
</DA>
<FRMA algoritmo="SHA1withRSA">dGVzdA==</FRMA>
</CAF>
<RSASK>{priv_pem}</RSASK>
</AUTORIZACION>"""
	return xml.encode("utf-8")


def _save_private_file(*, fname: str, content: bytes) -> str:
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": fname,
			"is_private": 1,
			"content": content,
		}
	)
	f.insert(ignore_permissions=True)
	return f.file_url


def setup_sii_configuration_y_rut_76(
	*,
	certificado_name: str,
	rut_emisor: str = "76000000-0",
) -> None:
	"""Rellena Single `SII Configuration` para usar CAF / cert de prueba RUT 76000000-0."""
	s = frappe.get_single("SII Configuration")
	s.rut_emisor = rut_emisor
	s.razon_social = s.razon_social or "Test Emisor SA"
	s.giro = s.giro or "Comercio"
	s.direccion_origen = s.direccion_origen or "Calle 1"
	s.comuna_origen = s.comuna_origen or "Santiago"
	s.resolucion_numero = s.resolucion_numero or 0
	s.resolucion_fecha = s.resolucion_fecha or date(2020, 1, 1)
	s.ambiente = s.ambiente or "Certificacion"
	s.certificado_digital = certificado_name
	s.save(ignore_permissions=True)


def create_certificado_pfx_fixture(*, nombre: str, password: str) -> str:
	"""Crea `Certificado Digital` con PFX generado; retorna `name`."""
	pfx = pfx_for_tests(password)
	url = _save_private_file(fname=f"{nombre}.pfx", content=pfx)
	doc = frappe.get_doc(
		{
			"doctype": "Certificado Digital",
			"nombre": nombre,
			"rut_firmante": "76000000-0",
			"vigencia_desde": date(2026, 1, 1),
			"vigencia_hasta": date(2030, 1, 1),
			"archivo_pfx": url,
			"password": password,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def create_caf_from_autorizacion_bytes(
	caf_xml: bytes,
	*,
	tipo_override: int | None = None,
) -> str:
	"""Adjunta XML CAF y crea DocType `CAF`. Retorna name."""
	data = parse_autorizacion_bytes(caf_xml)
	tipo = int(tipo_override if tipo_override is not None else data.tipo_dte)
	url = _save_private_file(
		fname=f"caf-test-{tipo}-{data.rango_desde}.xml",
		content=caf_xml,
	)
	doc = frappe.get_doc(
		{
			"doctype": "CAF",
			"tipo_dte": str(tipo),
			"rango_desde": data.rango_desde,
			"rango_hasta": data.rango_hasta,
			"fecha_autorizacion": data.fecha_autorizacion,
			"xml_caf": url,
		}
	)
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def mock_pos_invoice_afecta(name: str = "MOCK-POS-SII-AF") -> Any:
	"""Documento duck-typed compatible con `pos_invoice_to_dte_data` (sin persistir POS Invoice)."""
	from types import SimpleNamespace

	class _It:
		def __init__(self) -> None:
			self.qty = 1
			self.net_amount = 840
			self.item_tax_amount = 160
			self.item_name = "Item SII Test"
			self.item_code = "SII-T1"
			self.uom = "UN"

	return SimpleNamespace(
		name=name,
		doctype="POS Invoice",
		docstatus=1,
		posting_date=date(2026, 4, 24),
		posting_time="12:00:00",
		customer=None,
		customer_name="Cliente Boleta Test",
		net_total=840,
		total_taxes_and_charges=160,
		grand_total=1000,
		items=[_It()],
	)


def mock_pos_invoice_exenta(name: str = "MOCK-POS-SII-EX") -> Any:
	from types import SimpleNamespace

	class _It:
		def __init__(self) -> None:
			self.qty = 1
			self.net_amount = 5000
			self.item_tax_amount = 0
			self.item_name = "Item Exento"
			self.item_code = "SII-T2"
			self.uom = "UN"

	return SimpleNamespace(
		name=name,
		doctype="POS Invoice",
		docstatus=1,
		posting_date=date(2026, 4, 24),
		posting_time="12:00:00",
		customer=None,
		customer_name="Cliente Exento",
		net_total=5000,
		total_taxes_and_charges=0,
		grand_total=5000,
		items=[_It()],
	)


def make_get_doc_with_pos_stub(orig_get_doc: Any, mock_doc: Any) -> Any:
	"""Wrapper para patch `frappe.get_doc` que inyecta un POS Invoice ficticio."""

	def _wrap(*args: Any, **kw: Any):
		if len(args) == 1 and isinstance(args[0], dict):
			return orig_get_doc(args[0])
		if (
			len(args) >= 2
			and args[0] == "POS Invoice"
			and args[1] == mock_doc.name
		):
			return mock_doc
		return orig_get_doc(*args, **kw)

	return _wrap


def patch_frappe_db_get_value_pos_invoice_names(*names: str) -> Any:
	"""Hace que `frappe.db.get_value` reporte existencia de POS Invoice ficticios (validacion Link)."""
	from unittest.mock import patch

	allowed = set(names)

	def _gv(doctype: str, *args: Any, **kwargs: Any):
		if doctype == "POS Invoice" and args and args[0] in allowed:
			if len(args) >= 2 and args[1] == "name":
				return args[0]
			if (
				len(args) >= 2
				and isinstance(args[1], (list, tuple))
				and kwargs.get("as_dict")
			):
				return frappe._dict({f: (args[0] if f == "name" else None) for f in args[1]})
		return _gv._orig(doctype, *args, **kwargs)  # type: ignore[attr-defined]

	_gv._orig = frappe.db.get_value  # type: ignore[attr-defined]
	return patch.object(frappe.db, "get_value", side_effect=_gv)


__all__ = [
	"create_caf_from_autorizacion_bytes",
	"create_certificado_pfx_fixture",
	"make_get_doc_with_pos_stub",
	"mock_pos_invoice_afecta",
	"mock_pos_invoice_exenta",
	"patch_frappe_db_get_value_pos_invoice_names",
	"setup_sii_configuration_y_rut_76",
	"synthetic_autorizacion_bytes",
]
