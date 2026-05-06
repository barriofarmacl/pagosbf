# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spec S4: fallo validacion XSD antes de POST → RECHAZADO_LOCAL (sin enviar a SII)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.boleta import emision
from pagosbf.pagosbf.dte.xml_builder import DTEBuildError

from .sii_emision_harness import (
	create_caf_from_autorizacion_bytes,
	create_certificado_pfx_fixture,
	make_get_doc_with_pos_stub,
	mock_pos_invoice_afecta,
	patch_frappe_db_get_value_pos_invoice_names,
	setup_sii_configuration_y_rut_76,
	synthetic_autorizacion_bytes,
)


class TestEmisionRechazadoLocal(FrappeTestCase):
	def test_validate_dte_falla_sin_post_sii(self) -> None:
		sp = "sp_s4_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(sp)
		try:
			pw = "pw-s4-test"
			cert = create_certificado_pfx_fixture(
				nombre=f"SII-TST-S4-{frappe.generate_hash(length=6)}",
				password=pw,
			)
			caf = create_caf_from_autorizacion_bytes(synthetic_autorizacion_bytes(39))
			setup_sii_configuration_y_rut_76(certificado_name=cert)

			mock_pi = mock_pos_invoice_afecta("MOCK-POS-S4-LOCAL")
			wrap = make_get_doc_with_pos_stub(frappe.get_doc, mock_pi)
			fake_client = MagicMock()
			fake_client.get_semilla_y_token.return_value = ("s", "t", "<x/>", "<y/>")
			fake_client.enviar_sobre = MagicMock()

			with patch_frappe_db_get_value_pos_invoice_names(mock_pi.name):
				with patch.object(frappe, "get_doc", new=wrap):
					with patch(
						"pagosbf.pagosbf.boleta.emision.sii_client_from_sii_configuration",
						return_value=fake_client,
					):
						with patch(
							"pagosbf.pagosbf.boleta.emision.xml_builder.validate_dte_xml",
							side_effect=DTEBuildError("simulado XSD"),
						):
							with self.assertRaises(DTEBuildError):
								emision.ejecutar_emision_sii(
									pos_invoice_name=mock_pi.name,
									caf_name=caf,
								)

			rows = frappe.get_all(
				"DTE Boleta",
				filters={"pos_invoice": mock_pi.name},
				pluck="name",
			)
			self.assertTrue(rows)
			b = frappe.get_doc("DTE Boleta", rows[0])
			self.assertEqual(b.estado_envio, "RECHAZADO_LOCAL")
			self.assertTrue(b.error_log)
			fake_client.enviar_sobre.assert_not_called()
		finally:
			frappe.db.rollback(save_point=sp)


if __name__ == "__main__":
	import unittest

	unittest.main()
