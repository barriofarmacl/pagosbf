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

	def test_tax_row_print_label_chile_iva(self) -> None:
		from pagosbf.pagosbf.utils.jinja_methods import tax_row_print_label

		self.assertEqual(tax_row_print_label({"description": "VAT @ 19.0"}), "IVA 19%")
		self.assertEqual(tax_row_print_label({"description": "VAT", "rate": 19}), "IVA 19%")
		self.assertEqual(tax_row_print_label({"description": "Impuesto adicional"}), "Impuesto adicional")

	def test_pos_boleta_tax_lines_inclusive_fallback(self) -> None:
		from pagosbf.pagosbf.utils.jinja_methods import pos_boleta_tax_lines

		doc = frappe._dict(
			currency="CLP",
			taxes=[
				frappe._dict(
					description="VAT @ 19.0",
					rate=19,
					included_in_print_rate=1,
					tax_amount=0,
					tax_amount_after_discount_amount=0,
				)
			],
			total_taxes_and_charges=206,
		)
		doc.get_formatted = lambda field, *a, **k: "$ 206" if field == "total_taxes_and_charges" else ""

		lines = pos_boleta_tax_lines(doc)
		self.assertEqual(len(lines), 1)
		self.assertEqual(lines[0]["label"], "IVA 19%")
		self.assertEqual(lines[0]["formatted"], "$ 206")

	def test_pos_boleta_tax_lines_from_row_amount(self) -> None:
		from pagosbf.pagosbf.utils.jinja_methods import pos_boleta_tax_lines

		row = frappe._dict(
			description="VAT @ 19.0",
			rate=19,
			tax_amount=206,
			get_formatted=lambda field, doc: "$ 206",
		)
		doc = frappe._dict(currency="CLP", taxes=[row], total_taxes_and_charges=206)
		lines = pos_boleta_tax_lines(doc)
		self.assertEqual(len(lines), 1)
		self.assertEqual(lines[0]["label"], "IVA 19%")

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
		self.assertIn("width: 90%", html)
		self.assertNotIn("42mm", html)
		self.assertIn("Sin emision SII", html)
		self.assertNotIn("ted_compact", html)
		self.assertNotIn("ted_pdf417_payload", html)
		# Boleta Chile: IVA inclusivo debe verse en ticket (no ocultar por included_in_print_rate).
		self.assertNotIn("not row.included_in_print_rate", html)
		self.assertIn("pos_boleta_tax_lines(doc)", html)
		self.assertIn("tax_line.label", html)
