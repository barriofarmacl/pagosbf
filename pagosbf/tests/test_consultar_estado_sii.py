# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spec S5: consultar_estado persiste fila en DTE Respuesta SII (cliente SII mockeado)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.boleta import emision

from .sii_emision_harness import (
	create_caf_from_autorizacion_bytes,
	create_certificado_pfx_fixture,
	patch_frappe_db_get_value_pos_invoice_names,
	setup_sii_configuration_y_rut_76,
	synthetic_autorizacion_bytes,
)


class _FakeSIIClient:
	def get_semilla_y_token(self, _material):  # noqa: ANN001
		raw0 = """<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA xmlns:sii="http://www.sii.cl/SiiDte"><sii:RESP_HDR><sii:ESTADO>00</sii:ESTADO></sii:RESP_HDR>
<sii:RESP_BODY><sii:SEMILLA>S123</sii:SEMILLA></sii:RESP_BODY></sii:RESPUESTA>"""
		raw1 = """<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA xmlns:sii="http://www.sii.cl/SiiDte"><sii:RESP_HDR><sii:ESTADO>00</sii:ESTADO></sii:RESP_HDR>
<sii:RESP_BODY><sii:TOKEN>TOK99</sii:TOKEN></sii:RESP_BODY></sii:RESPUESTA>"""
		return "S123", "TOK99", raw0, raw1

	def consultar_estado(self, track_id: str, token: str, rut_emisor: str) -> str:
		return f"""<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA xmlns:sii="http://www.sii.cl/SiiDte">
  <sii:RESP_HDR><sii:ESTADO>EPR</sii:ESTADO><sii:GLOSA>Aceptado registro</sii:GLOSA></sii:RESP_HDR>
  <sii:RESP_BODY><sii:TRACKID>{track_id}</sii:TRACKID></sii:RESP_BODY>
</sii:RESPUESTA>"""


class TestConsultarEstadoSii(FrappeTestCase):
	def test_consultar_estado_registra_respuesta_epr(self) -> None:
		sp = "sp_s5_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pw = "pw-s5-test"
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-S5-{frappe.generate_hash(length=6)}",
				password=pw,
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(39))
			setup_sii_configuration_y_rut_76(certificado_name=cert)

			with patch_frappe_db_get_value_pos_invoice_names("MOCK-PI-CONS-EST-1"):
				bol = frappe.get_doc(
					{
						"doctype": "DTE Boleta",
						"pos_invoice": "MOCK-PI-CONS-EST-1",
						"tipo_dte": "39",
						"folio": 1,
						"caf": caf,
						"fecha_emision": date(2026, 4, 24),
						"monto_neto": 840,
						"monto_iva": 160,
						"monto_exento": 0,
						"monto_total": 1000,
						"track_id": "55001",
						"estado_envio": "ENVIADO",
					}
				)
				bol.insert(ignore_permissions=True)

				with patch(
					"pagosbf.pagosbf.boleta.emision.sii_client_from_sii_configuration",
					return_value=_FakeSIIClient(),
				):
					out = emision.consultar_estado_dte(bol.name)

			self.assertIn(out.get("estado"), ("EPR", "00", "0"))
			reloaded = frappe.get_doc("DTE Boleta", bol.name)
			acciones = [r.accion for r in reloaded.respuestas]
			self.assertIn("semilla", acciones)
			self.assertIn("token", acciones)
			self.assertIn("estado", acciones)
			est_rows = [r for r in reloaded.respuestas if r.accion == "estado"]
			self.assertTrue(est_rows)
			self.assertIn("EPR", est_rows[-1].estado or "")
			self.assertTrue((est_rows[-1].glosa or "").strip())
		finally:
			frappe.db.rollback(save_point=sp)


if __name__ == "__main__":
	import unittest

	unittest.main()
