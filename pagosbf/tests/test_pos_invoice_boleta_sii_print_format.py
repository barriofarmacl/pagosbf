# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Static checks for Print Format POS Invoice Boleta SII (R12 public ticket layout)."""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPosInvoiceBoletaSiiPrintFormat(FrappeTestCase):
	def test_company_address_display_sin_company(self) -> None:
		from pagosbf.pagosbf.utils.jinja_methods import company_address_display

		self.assertEqual(company_address_display(None), "")
		self.assertEqual(company_address_display(""), "")

	def test_pos_invoice_boleta_sii_json_contract(self) -> None:
		base = Path(frappe.get_app_path("pagosbf"))
		path = base / "pagosbf" / "print_format" / "pos_invoice_boleta_sii" / "pos_invoice_boleta_sii.json"
		self.assertTrue(path.is_file(), msg=f"missing print format json: {path}")
		obj = json.loads(path.read_text(encoding="utf-8"))
		self.assertEqual(obj.get("doc_type"), "POS Invoice")
		self.assertEqual(obj.get("name"), "POS Invoice Boleta SII")
		html = obj.get("html") or ""
		self.assertIn("@page", html)
		self.assertIn("size: 3in 7.5in", html)
		self.assertIn("pos_invoice_sii_print_block(doc)", html)
		self.assertIn("company_address_display(doc.company)", html)
		self.assertIn("sii_sin_dte", html)
		self.assertIn("timbre_pdf417_data_url", html)
		self.assertIn("Sin emision SII", html)
		self.assertNotIn("ted_compact", html)
		self.assertNotIn("ted_pdf417_payload", html)
