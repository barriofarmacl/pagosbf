# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Fase A factura 33: mapper, persistencia `DTE Documento` y API con SII mockeado."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.api import facturacion as facturacion_api
from pagosbf.pagosbf.dte.constants import (
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from pagosbf.pagosbf.facturacion.invoice_to_factura import (
	sales_invoice_to_factura_data,
	sales_invoice_to_nota_credito_debito_data,
)
from pagosbf.pagosbf.sii.dte_upload import DteUploadResult

from .dte_fixtures import emisor
from .sii_emision_harness import (
	create_caf_from_autorizacion_bytes,
	create_certificado_pfx_fixture,
	setup_sii_configuration_y_rut_76,
	synthetic_autorizacion_bytes,
)


class _FakeSIIClientOk:
	def get_semilla_y_token(self, _material):  # noqa: ANN001
		raw0 = """<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA xmlns:sii="http://www.sii.cl/SiiDte"><sii:RESP_HDR><sii:ESTADO>00</sii:ESTADO></sii:RESP_HDR>
<sii:RESP_BODY><sii:SEMILLA>S1</sii:SEMILLA></sii:RESP_BODY></sii:RESPUESTA>"""
		raw1 = """<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA xmlns:sii="http://www.sii.cl/SiiDte"><sii:RESP_HDR><sii:ESTADO>00</sii:ESTADO></sii:RESP_HDR>
<sii:RESP_BODY><sii:TOKEN>T1</sii:TOKEN></sii:RESP_BODY></sii:RESPUESTA>"""
		return "S1", "T1", raw0, raw1

	def enviar_sobre(
		self,
		envio_bytes: bytes,
		token: str,
		rut_emisor: str,
		*,
		rut_digitador: str | None = None,
	) -> DteUploadResult:
		self.last_envio = envio_bytes
		_ = token, rut_emisor, rut_digitador
		return DteUploadResult(
			track_id="99112233",
			resumen="TRACK: 99112233",
			response_text="ACEPTADO TRACK: 99112233",
			status_code=200,
		)


def _sales_item(**overrides):
	base = {
		"item_code": "IT-33",
		"item_name": "Item Factura 33",
		"qty": 2,
		"rate": 1000,
		"net_rate": 900,
		"net_amount": 1800,
		"discount_percentage": 10,
		"item_tax_amount": 342,
		"uom": "UN",
	}
	base.update(overrides)
	return SimpleNamespace(**base)


def _mock_sales_invoice(name: str = "MOCK-SINV-33") -> SimpleNamespace:
	return SimpleNamespace(
		name=name,
		doctype="Sales Invoice",
		docstatus=1,
		is_return=0,
		is_debit_note=0,
		return_against=None,
		posting_date=date(2026, 5, 11),
		posting_time="12:00:00",
		customer="CUST-DTE-33",
		customer_name="Cliente Factura 33",
		net_total=2300,
		total_taxes_and_charges=342,
		grand_total=2642,
		items=[
			_sales_item(),
			_sales_item(
				item_code="IT-EXE",
				item_name="Servicio Exento",
				qty=1,
				rate=500,
				net_rate=500,
				net_amount=500,
				discount_percentage=0,
				item_tax_amount=0,
			),
		],
	)


def _patch_get_doc_sales_invoice(mock_doc: SimpleNamespace):
	orig_get_doc = frappe.get_doc

	def _wrap(*args, **kwargs):
		if len(args) == 1 and isinstance(args[0], dict):
			return orig_get_doc(args[0])
		if len(args) >= 2 and args[0] == "Sales Invoice" and args[1] == mock_doc.name:
			return mock_doc
		return orig_get_doc(*args, **kwargs)

	return patch.object(frappe, "get_doc", new=_wrap)


def _patch_db_get_value_sales_invoice(mock_doc: SimpleNamespace):
	orig_get_value = frappe.db.get_value

	def _gv(doctype: str, *args, **kwargs):
		if doctype == "Sales Invoice":
			if args and args[0] == mock_doc.name:
				if len(args) >= 2 and args[1] == "name":
					return mock_doc.name
				if len(args) >= 2 and isinstance(args[1], (list, tuple)) and kwargs.get("as_dict"):
					return frappe._dict({f: (mock_doc.name if f == "name" else None) for f in args[1]})
			if args and isinstance(args[0], dict) and args[0].get("name") == mock_doc.name:
				return mock_doc.name
		if doctype == "Customer" and args and args[0] == "CUST-DTE-33":
			return "77777777-7"
		return orig_get_value(doctype, *args, **kwargs)

	return patch.object(frappe.db, "get_value", side_effect=_gv)


class TestFactura33Mapper(unittest.TestCase):
	def test_sales_invoice_to_factura_33_refleja_descuento_y_exento(self) -> None:
		doc = _mock_sales_invoice()
		with patch(
			"pagosbf.pagosbf.facturacion.invoice_to_factura.frappe.db.get_value",
			return_value="77777777-7",
		):
			data = sales_invoice_to_factura_data(doc, folio=21, emisor=emisor(), acteco="477310")

		self.assertEqual(data.tipo_dte, TIPO_DTE_FACTURA_ELECTRONICA)
		self.assertEqual(data.folio, 21)
		self.assertEqual(data.receptor.rut, "77777777-7")
		self.assertEqual(data.totales.monto_neto, 1800)
		self.assertEqual(data.totales.monto_exento, 500)
		self.assertEqual(data.totales.iva, 342)
		self.assertEqual(data.totales.monto_total, 2642)
		self.assertEqual(data.detalles[0].descuento_pct, 10)
		self.assertTrue(data.detalles[1].indica_exento)

	def test_sales_invoice_return_maps_to_nota_credito_61_with_reference(self) -> None:
		doc = _mock_sales_invoice("MOCK-SINV-NC-61")
		doc.is_return = 1
		doc.return_against = "MOCK-SINV-ORIG-33"
		doc.grand_total = -2142
		doc.total_taxes_and_charges = -342
		doc.items = [
			_sales_item(qty=-2, rate=1000, net_rate=900, net_amount=-1800, item_tax_amount=-342),
		]

		def _gv(doctype: str, *args, **kwargs):
			if doctype == "Customer" and args and args[0] == "CUST-DTE-33":
				return "77777777-7"
			if doctype == "DTE Documento" and kwargs.get("as_dict"):
				return frappe._dict(
					{
						"tipo_dte": "33",
						"folio": 21,
						"fecha_emision": date(2026, 5, 9),
					}
				)
			return None

		with patch("pagosbf.pagosbf.facturacion.invoice_to_factura.frappe.db.get_value", side_effect=_gv):
			data = sales_invoice_to_nota_credito_debito_data(
				doc,
				folio=8,
				emisor=emisor(),
				razon_ref="DEVOLUCION DE MERCADERIAS",
			)

		self.assertEqual(data.tipo_dte, TIPO_DTE_NOTA_CREDITO_ELECTRONICA)
		self.assertEqual(data.detalles[0].cantidad, Decimal("2.0"))
		self.assertEqual(data.detalles[0].monto_item, 1800)
		self.assertEqual(data.totales.monto_neto, 1800)
		self.assertEqual(data.totales.iva, 342)
		self.assertEqual(data.totales.monto_total, 2142)
		self.assertEqual(data.referencias[0].tpo_doc_ref, "33")
		self.assertEqual(data.referencias[0].folio_ref, "21")
		self.assertEqual(data.referencias[0].cod_ref, 3)
		self.assertEqual(data.referencias[0].razon_ref, "DEVOLUCION DE MERCADERIAS")

	def test_sales_invoice_debit_note_maps_to_dte_56_with_explicit_nc_reference(self) -> None:
		doc = _mock_sales_invoice("MOCK-SINV-ND-56")
		doc.is_debit_note = 1
		doc.return_against = "MOCK-SINV-NC-61"
		doc.grand_total = 0
		doc.total_taxes_and_charges = 0
		doc.items = [
			_sales_item(
				item_name="ANULA NOTA DE CREDITO ELECTRONICA",
				qty=0,
				rate=0,
				net_rate=0,
				net_amount=0,
				item_tax_amount=0,
				discount_percentage=0,
			),
		]

		with patch(
			"pagosbf.pagosbf.facturacion.invoice_to_factura.frappe.db.get_value",
			return_value="77777777-7",
		):
			data = sales_invoice_to_nota_credito_debito_data(
				doc,
				folio=9,
				emisor=emisor(),
				referencia_tipo_dte=61,
				referencia_folio=5,
				referencia_fecha=date(2026, 5, 10),
				cod_ref=1,
				razon_ref="ANULA NOTA DE CREDITO ELECTRONICA",
			)

		self.assertEqual(data.tipo_dte, TIPO_DTE_NOTA_DEBITO_ELECTRONICA)
		self.assertEqual(data.detalles[0].cantidad, Decimal("1"))
		self.assertEqual(data.detalles[0].monto_item, 0)
		self.assertEqual(data.totales.monto_total, 0)
		self.assertEqual(data.referencias[0].tpo_doc_ref, "61")
		self.assertEqual(data.referencias[0].folio_ref, "5")
		self.assertEqual(data.referencias[0].cod_ref, 1)


class TestFacturacionEmision(FrappeTestCase):
	def test_dte_documento_persiste_track_id_y_respuestas(self) -> None:
		mock_si = _mock_sales_invoice("MOCK-SINV-DOC-33")
		sp = "sp_dte_doc_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			with _patch_db_get_value_sales_invoice(mock_si):
				doc = frappe.get_doc(
					{
						"doctype": "DTE Documento",
						"sales_invoice": mock_si.name,
						"tipo_dte": "33",
						"folio": 7,
						"fecha_emision": date(2026, 5, 11),
						"monto_neto": 1800,
						"monto_iva": 342,
						"monto_exento": 500,
						"monto_total": 2642,
						"track_id": "99112233",
						"estado_envio": "ENVIADO",
					}
				)
				doc.append(
					"respuestas",
					{
						"timestamp": "2026-05-11 12:00:00",
						"accion": "envio",
						"estado": "200",
						"glosa": "ACEPTADO TRACK: 99112233",
					},
				)
				doc.insert(ignore_permissions=True)

			reloaded = frappe.get_doc("DTE Documento", doc.name)
			self.assertEqual(reloaded.track_id, "99112233")
			self.assertEqual(reloaded.tipo_dte, "33")
			self.assertEqual(reloaded.respuestas[-1].accion, "envio")
		finally:
			frappe.db.rollback(save_point=sp)

	def test_api_rechaza_factura_33_si_flag_esta_inactivo(self) -> None:
		mock_si = _mock_sales_invoice("MOCK-SINV-FLAG-33")
		sp = "sp_flag_33_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			setup_sii_configuration_y_rut_76(
				certificado_name=create_certificado_pfx_fixture(
					nombre=f"SII-TST-FLAG-{frappe.generate_hash(length=6)}",
					password="pw-flag",
				)
			)
			single = frappe.get_single("SII Configuration")
			single.habilitar_factura_electronica = 0
			single.save(ignore_permissions=True)

			with _patch_get_doc_sales_invoice(mock_si), _patch_db_get_value_sales_invoice(mock_si):
				with self.assertRaises(frappe.ValidationError):
					facturacion_api.emitir(sales_invoice=mock_si.name)
		finally:
			frappe.db.rollback(save_point=sp)

	def test_api_emitir_factura_33_exige_permiso_sobre_sales_invoice(self) -> None:
		mock_si = _mock_sales_invoice("MOCK-SINV-PERM-33")
		with (
			_patch_get_doc_sales_invoice(mock_si),
			patch("pagosbf.pagosbf.api.facturacion.frappe.has_permission", return_value=False),
			patch("pagosbf.pagosbf.api.facturacion.emision.ejecutar_emision_factura") as emitir_mock,
		):
			with self.assertRaises(frappe.PermissionError):
				facturacion_api.emitir(sales_invoice=mock_si.name)

		emitir_mock.assert_not_called()

	def test_api_emitir_factura_33_persistiendo_track_id(self) -> None:
		mock_si = _mock_sales_invoice("MOCK-SINV-EMIT-33")
		sp = "sp_emit_33_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-F33-{frappe.generate_hash(length=6)}",
				password="pw-f33",
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(33))
			setup_sii_configuration_y_rut_76(certificado_name=cert)
			single = frappe.get_single("SII Configuration")
			single.habilitar_factura_electronica = 1
			single.save(ignore_permissions=True)

			with _patch_get_doc_sales_invoice(mock_si), _patch_db_get_value_sales_invoice(mock_si):
				with patch(
					"pagosbf.pagosbf.facturacion.emision.sii_client_from_sii_configuration",
					return_value=_FakeSIIClientOk(),
				):
					name = facturacion_api.emitir(sales_invoice=mock_si.name, caf=caf)

			dte = frappe.get_doc("DTE Documento", name)
			self.assertEqual(dte.tipo_dte, "33")
			self.assertEqual(dte.sales_invoice, mock_si.name)
			self.assertEqual(dte.estado_envio, "ENVIADO")
			self.assertEqual(dte.track_id, "99112233")
			self.assertIn("EnvioDTE", dte.xml_sobre_firmado)
			self.assertIn("semilla", [row.accion for row in dte.respuestas])
			self.assertIn("envio", [row.accion for row in dte.respuestas])
		finally:
			frappe.db.rollback(save_point=sp)
