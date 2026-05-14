# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spec S9: datos_impresion_boleta_pos + print_context TED / PDF417 payload."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.api import boleta as boleta_api
from pagosbf.pagosbf.boleta.print_context import get_pos_invoice_sii_block
from pagosbf.pagosbf.sii.dte_upload import DteUploadResult

from .sii_emision_harness import (
	create_caf_from_autorizacion_bytes,
	create_certificado_pfx_fixture,
	make_get_doc_with_pos_stub,
	mock_pos_invoice_afecta,
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


class TestDatosImpresionBoletaS9(FrappeTestCase):
	def test_s9_timbre_y_pdf417_tras_emitir(self) -> None:
		sp = "sp_s9_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pw = "pw-s9-test"
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-S9-{frappe.generate_hash(length=6)}",
				password=pw,
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(39))
			setup_sii_configuration_y_rut_76(certificado_name=cert)

			mock_pi = mock_pos_invoice_afecta("MOCK-POS-S9-39")
			wrap = make_get_doc_with_pos_stub(frappe.get_doc, mock_pi)

			with patch_frappe_db_get_value_pos_invoice_names(mock_pi.name):
				with patch.object(frappe, "get_doc", new=wrap):
					with patch(
						"pagosbf.pagosbf.boleta.emision.sii_client_from_sii_configuration",
						return_value=_FakeSIIClientOk(),
					):
						boleta_api.emitir(pos_invoice=mock_pi.name, caf=caf)

			blk = get_pos_invoice_sii_block(SimpleNamespace(name=mock_pi.name))
			self.assertIsNotNone(blk)
			assert blk is not None
			self.assertEqual(blk.get("estado_envio"), "ENVIADO")
			self.assertTrue((blk.get("ted_compact") or "").strip())
			self.assertTrue((blk.get("ted_pdf417_payload") or "").strip())
			self.assertIn("<TED", blk.get("ted_compact") or "")

			with patch_frappe_db_get_value_pos_invoice_names(mock_pi.name):
				with patch.object(frappe, "get_doc", new=wrap):
					out = boleta_api.datos_impresion_boleta_pos(pos_invoice=mock_pi.name)
					timb = boleta_api.timbre_pdf417_data_url(pos_invoice=mock_pi.name)
			self.assertTrue(out.get("ok"))
			self.assertEqual(out.get("pos_invoice"), mock_pi.name)
			self.assertEqual(out.get("dte_boleta"), blk.get("name"))
			self.assertTrue((out.get("ted_pdf417_payload") or "").strip())
			self.assertTrue(timb.get("ok"), msg=timb.get("mensaje"))
			self.assertIn("data:image/png;base64,", timb.get("data_url") or "")
		finally:
			frappe.db.rollback(save_point=sp)

	def test_datos_sin_dte_ok_false(self) -> None:
		sp = "sp_s9b_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pi_name = "PI-NODTE-" + frappe.generate_hash(length=8)
			with patch.object(boleta_api, "_require_source_permission", lambda *a, **k: None):
				out = boleta_api.datos_impresion_boleta_pos(pos_invoice=pi_name)
			self.assertFalse(out.get("ok"))
			self.assertIn("mensaje", out)
		finally:
			frappe.db.rollback(save_point=sp)


class TestPosInvoiceSiiPrintBlock(FrappeTestCase):
	def test_print_block_sin_dte_no_retorna_none(self) -> None:
		pi_name = "PI-JINJA-" + frappe.generate_hash(length=8)
		with patch("pagosbf.pagosbf.api.boleta._require_source_permission", lambda *a, **k: None):
			with patch(
				"pagosbf.pagosbf.api.boleta.datos_impresion_boleta_pos",
				return_value={"ok": False, "mensaje": "Sin DTE Boleta vinculada.", "pos_invoice": pi_name},
			):
				from pagosbf.pagosbf.utils.jinja_methods import pos_invoice_sii_print_block

				out = pos_invoice_sii_print_block(SimpleNamespace(name=pi_name))
		self.assertFalse(out.get("sii_ready"))
		self.assertTrue(out.get("sii_sin_dte"))
		self.assertIn("Sin DTE", out.get("mensaje_print") or "")


if __name__ == "__main__":
	import unittest

	unittest.main()
