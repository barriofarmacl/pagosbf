# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spec S1/S2: emitir desde POS Invoice con SII mockeado → DTE 39 / 41 ENVIADO."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.api import boleta as boleta_api
from pagosbf.pagosbf.sii.dte_upload import DteUploadResult

from .sii_emision_harness import (
	create_caf_from_autorizacion_bytes,
	create_certificado_pfx_fixture,
	make_get_doc_with_pos_stub,
	mock_pos_invoice_afecta,
	mock_pos_invoice_exenta,
	patch_frappe_db_get_value_pos_invoice_names,
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
		_ = envio_bytes, token, rut_emisor, rut_digitador
		return DteUploadResult(
			track_id="88112233",
			resumen="TRACK: 88112233",
			response_text="RCH: ACEPTADO TRACK: 88112233",
			status_code=200,
		)


class TestEmitirPosInvoiceMockSii(FrappeTestCase):
	def test_pos_afecta_dte_39_enviado(self) -> None:
		sp = "sp_s1_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pw = "pw-s1-test"
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-S1-{frappe.generate_hash(length=6)}",
				password=pw,
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(39))
			setup_sii_configuration_y_rut_76(certificado_name=cert)

			mock_pi = mock_pos_invoice_afecta("MOCK-POS-S1-39")
			wrap = make_get_doc_with_pos_stub(frappe.get_doc, mock_pi)

			with patch_frappe_db_get_value_pos_invoice_names(mock_pi.name):
				with patch.object(frappe, "get_doc", new=wrap):
					with patch(
						"pagosbf.pagosbf.boleta.emision.sii_client_from_sii_configuration",
						return_value=_FakeSIIClientOk(),
					):
						name = boleta_api.emitir(
							pos_invoice=mock_pi.name,
							caf=caf,
						)

			b = frappe.get_doc("DTE Boleta", name)
			self.assertEqual(b.tipo_dte, "39")
			self.assertEqual(b.estado_envio, "ENVIADO")
			self.assertEqual(b.pos_invoice, mock_pi.name)
			self.assertFalse((b.sales_invoice or "").strip())
			self.assertEqual(b.track_id, "88112233")
			self.assertTrue(b.xml_dte_firmado)
		finally:
			frappe.db.rollback(save_point=sp)

	def test_pos_exenta_dte_41_enviado(self) -> None:
		sp = "sp_s2_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pw = "pw-s2-test"
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-S2-{frappe.generate_hash(length=6)}",
				password=pw,
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(41))
			setup_sii_configuration_y_rut_76(certificado_name=cert)

			mock_pi = mock_pos_invoice_exenta("MOCK-POS-S2-41")
			wrap = make_get_doc_with_pos_stub(frappe.get_doc, mock_pi)

			with patch_frappe_db_get_value_pos_invoice_names(mock_pi.name):
				with patch.object(frappe, "get_doc", new=wrap):
					with patch(
						"pagosbf.pagosbf.boleta.emision.sii_client_from_sii_configuration",
						return_value=_FakeSIIClientOk(),
					):
						name = boleta_api.emitir(
							pos_invoice=mock_pi.name,
							caf=caf,
						)

			b = frappe.get_doc("DTE Boleta", name)
			self.assertEqual(b.tipo_dte, "41")
			self.assertEqual(b.estado_envio, "ENVIADO")
			self.assertEqual(b.pos_invoice, mock_pi.name)
			self.assertEqual(b.track_id, "88112233")
		finally:
			frappe.db.rollback(save_point=sp)


if __name__ == "__main__":
	import unittest

	unittest.main()
