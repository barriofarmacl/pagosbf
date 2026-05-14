# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Hooks `on_sales_invoice_submit` / politica consolidado (spec S8)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.api import boleta


class TestSalesInvoiceSubmitHook(FrappeTestCase):
	"""Requiere site con app `pagosbf`; no persiste Sales Invoice real."""

	def test_consolidated_no_encola_emision(self) -> None:
		"""S8: SI consolidada no debe encolar `ejecutar_emision_sii` vía hook."""
		doc = SimpleNamespace(
			doctype="Sales Invoice",
			name="SI-CONSOL-TEST",
			is_consolidated=1,
			docstatus=1,
			is_return=0,
			flags={},
		)
		with patch.object(boleta.emision, "encolar_emision_sii") as enc:
			boleta.on_sales_invoice_submit(doc)
			enc.assert_not_called()

	def test_no_consolidated_encola_cuando_singles_activos(self) -> None:
		doc = SimpleNamespace(
			doctype="Sales Invoice",
			name="SI-NORM-TEST",
			is_consolidated=0,
			docstatus=1,
			is_return=0,
			flags={},
		)

		def _gsv(doctype: str, fieldname: str, *args, **kwargs):
			if doctype == "SII Configuration" and fieldname == "encolar_emision_en_submit":
				return 1
			if doctype == "SII Configuration" and fieldname == "certificado_digital":
				return "Certificado-Hook-Test"
			return None

		with patch.object(boleta.emision, "encolar_emision_sii") as enc:
			with patch.object(boleta.frappe.db, "get_single_value", side_effect=_gsv):
				with patch.object(boleta.frappe.db, "get_value", return_value=None):
					boleta.on_sales_invoice_submit(doc)
		enc.assert_called_once_with("SI-NORM-TEST")


class TestPosInvoiceSubmitHook(FrappeTestCase):
	def test_pos_emitir_sincrono_tiene_prioridad_sobre_encolar(self) -> None:
		doc = SimpleNamespace(
			doctype="POS Invoice",
			name="POS-SYNC-TEST",
			docstatus=1,
			is_return=0,
			flags={},
		)

		def _gsv(doctype: str, fieldname: str, *args, **kwargs):
			if doctype == "SII Configuration" and fieldname == "emitir_sincrono_pos_invoice_submit":
				return 1
			if doctype == "SII Configuration" and fieldname == "encolar_emision_en_submit":
				return 1
			if doctype == "SII Configuration" and fieldname == "certificado_digital":
				return "Certificado-Hook-Test"
			return None

		with patch.object(boleta.emision, "ejecutar_emision_sii") as ex:
			with patch.object(boleta.emision, "encolar_emision_sii") as enc:
				with patch.object(boleta.frappe.db, "get_single_value", side_effect=_gsv):
					with patch.object(boleta.frappe.db, "get_value", return_value=None):
						boleta.on_pos_invoice_submit(doc)
		ex.assert_called_once_with(pos_invoice_name="POS-SYNC-TEST")
		enc.assert_not_called()

	def test_pos_encola_si_sincrono_off(self) -> None:
		doc = SimpleNamespace(
			doctype="POS Invoice",
			name="POS-ASYNC-TEST",
			docstatus=1,
			is_return=0,
			flags={},
		)

		def _gsv(doctype: str, fieldname: str, *args, **kwargs):
			if doctype == "SII Configuration" and fieldname == "emitir_sincrono_pos_invoice_submit":
				return 0
			if doctype == "SII Configuration" and fieldname == "encolar_emision_en_submit":
				return 1
			if doctype == "SII Configuration" and fieldname == "certificado_digital":
				return "Certificado-Hook-Test"
			return None

		with patch.object(boleta.emision, "ejecutar_emision_sii") as ex:
			with patch.object(boleta.emision, "encolar_emision_sii") as enc:
				with patch.object(boleta.frappe.db, "get_single_value", side_effect=_gsv):
					with patch.object(boleta.frappe.db, "get_value", return_value=None):
						boleta.on_pos_invoice_submit(doc)
		ex.assert_not_called()
		enc.assert_called_once_with(pos_invoice_name="POS-ASYNC-TEST")


if __name__ == "__main__":
	unittest.main()
