# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""E2 / whiteboard #69: POS Invoice sin filas de IVA no debe caer a DTE 41.

ERPNext `set_taxes()` solo copia la plantilla si `is_new()`; el POS de mostrador
persiste el documento y deja `taxes` vacio. pagosbf MUST aplicar la plantilla del
POS Profile via `append_taxes_from_master` (spec pagosbf-sii-boleta: DTE 39 si IVA > 0).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pagosbf.pagosbf.boleta.pos_profile_taxes import (
	ensure_pos_profile_taxes,
	false_exenta_if_profile_has_iva_reason,
	pos_invoice_needs_profile_taxes,
)


class _DocLike(SimpleNamespace):
	def get(self, key, default=None):
		return getattr(self, key, default)


class TestPosInvoiceNeedsProfileTaxes(unittest.TestCase):
	def test_aplica_cuando_sin_filas_y_perfil_tiene_plantilla(self):
		doc = _DocLike(doctype="POS Invoice", is_return=0, taxes=[], pos_profile="Caja Rojas 1")
		self.assertTrue(pos_invoice_needs_profile_taxes(doc, "Chile Tax - BF"))

	def test_no_aplica_si_ya_hay_filas(self):
		doc = _DocLike(doctype="POS Invoice", is_return=0, taxes=[object()], pos_profile="Caja")
		self.assertFalse(pos_invoice_needs_profile_taxes(doc, "Chile Tax - BF"))

	def test_no_aplica_devolucion(self):
		doc = _DocLike(doctype="POS Invoice", is_return=1, taxes=[], pos_profile="Caja")
		self.assertFalse(pos_invoice_needs_profile_taxes(doc, "Chile Tax - BF"))

	def test_no_aplica_sin_plantilla_en_perfil(self):
		doc = _DocLike(doctype="POS Invoice", is_return=0, taxes=[], pos_profile="Caja")
		self.assertFalse(pos_invoice_needs_profile_taxes(doc, None))
		self.assertFalse(pos_invoice_needs_profile_taxes(doc, "  "))

	def test_no_aplica_otro_doctype(self):
		doc = _DocLike(doctype="Sales Invoice", is_return=0, taxes=[], pos_profile="Caja")
		self.assertFalse(pos_invoice_needs_profile_taxes(doc, "Chile Tax - BF"))


class TestEnsurePosProfileTaxes(unittest.TestCase):
	def test_append_taxes_from_master_cuando_vacio(self):
		doc = MagicMock()
		doc.doctype = "POS Invoice"
		doc.is_return = 0
		doc.pos_profile = "Caja Rojas 1"
		doc.taxes = []
		doc.get.side_effect = lambda k, default=None: (
			[] if k == "taxes" else getattr(doc, k, default)
		)

		with patch(
			"pagosbf.pagosbf.boleta.pos_profile_taxes.frappe.db.get_value",
			return_value="Chile Tax - BF",
		):
			applied = ensure_pos_profile_taxes(doc)

		self.assertTrue(applied)
		self.assertEqual(doc.taxes_and_charges, "Chile Tax - BF")
		doc.append_taxes_from_master.assert_called_once_with()

	def test_no_toca_si_ya_tiene_taxes(self):
		doc = MagicMock()
		doc.doctype = "POS Invoice"
		doc.is_return = 0
		doc.pos_profile = "Caja Rojas 1"
		doc.taxes = [object()]
		doc.get.side_effect = lambda k, default=None: (
			doc.taxes if k == "taxes" else getattr(doc, k, default)
		)
		with patch(
			"pagosbf.pagosbf.boleta.pos_profile_taxes.frappe.db.get_value",
			return_value="Chile Tax - BF",
		):
			applied = ensure_pos_profile_taxes(doc)
		self.assertFalse(applied)
		doc.append_taxes_from_master.assert_not_called()


class TestFalseExentaReason(unittest.TestCase):
	def test_reason_si_iva_cero_pero_perfil_con_plantilla(self):
		doc = SimpleNamespace(
			doctype="POS Invoice",
			name="ACC-PSINV-TEST",
			pos_profile="Caja Rojas 1",
			total_taxes_and_charges=0,
		)
		msg = false_exenta_if_profile_has_iva_reason(doc, "Chile Tax - BF")
		self.assertIsNotNone(msg)
		assert msg is not None
		self.assertIn("DTE 41", msg)
		self.assertIn("Chile Tax - BF", msg)

	def test_none_si_perfil_sin_plantilla(self):
		doc = SimpleNamespace(
			doctype="POS Invoice",
			name="ACC-PSINV-EXENTA",
			pos_profile="Caja Exenta",
			total_taxes_and_charges=0,
		)
		self.assertIsNone(false_exenta_if_profile_has_iva_reason(doc, None))

	def test_none_si_ya_es_afecta(self):
		doc = SimpleNamespace(
			doctype="POS Invoice",
			name="ACC-PSINV-OK",
			pos_profile="Caja Rojas 1",
			total_taxes_and_charges=878,
		)
		self.assertIsNone(false_exenta_if_profile_has_iva_reason(doc, "Chile Tax - BF"))


if __name__ == "__main__":
	unittest.main()
