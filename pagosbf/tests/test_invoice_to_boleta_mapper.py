# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Mapper POS/SI-like a DTEBoletaData (sin DocType real, duck typing)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pagosbf.pagosbf.boleta.invoice_to_boleta import pos_invoice_to_dte_data
from pagosbf.pagosbf.dte import constants

from .dte_fixtures import FIXED_DATE, emisor


class TestInvoiceToBoletaMapper(unittest.TestCase):
	def _item(self, **kwargs):
		base = dict(
			qty=1,
			net_amount=840,
			item_tax_amount=160,
			item_name="Item",
			item_code="IT-1",
		)
		base.update(kwargs)
		return SimpleNamespace(**base)

	def test_pos_invoice_like_afecta_39(self):
		doc = SimpleNamespace(
			net_total=840,
			total_taxes_and_charges=160,
			grand_total=1000,
			posting_date=FIXED_DATE,
			posting_time="12:00:00",
			customer=None,
			customer_name="Cliente Prueba",
			items=[self._item()],
		)
		data = pos_invoice_to_dte_data(doc, folio=7, emisor=emisor())
		data.validate()
		self.assertEqual(data.tipo_dte, constants.TIPO_DTE_BOLETA_AFECTA)
		self.assertEqual(data.folio, 7)
		self.assertEqual(data.totales.monto_neto, 840)
		self.assertEqual(data.totales.iva, 160)
		self.assertEqual(data.totales.monto_total, 1000)

	def test_afecta_sin_item_tax_amount_cuadra_monto_total(self) -> None:
		"""POS Invoice Item no tiene item_tax_amount; IVA va en cabecera (reparo HED-2-260)."""
		doc = SimpleNamespace(
			net_total=1200,
			total_taxes_and_charges=228,
			grand_total=1428,
			posting_date=FIXED_DATE,
			posting_time="12:00:00",
			customer=None,
			customer_name="Cliente Prueba",
			items=[self._item(net_amount=1200, item_tax_amount=0)],
		)
		data = pos_invoice_to_dte_data(doc, folio=59, emisor=emisor())
		data.validate()
		self.assertEqual(sum(int(d.monto_item) for d in data.detalles), 1428)
		self.assertEqual(data.totales.monto_total, 1428)

	def test_afecta_multilinea_distribuye_iva_pool(self) -> None:
		doc = SimpleNamespace(
			net_total=1000,
			total_taxes_and_charges=190,
			grand_total=1190,
			posting_date=FIXED_DATE,
			posting_time="12:00:00",
			customer=None,
			customer_name="Cliente Prueba",
			items=[
				self._item(net_amount=333, item_tax_amount=0, item_name="A"),
				self._item(net_amount=333, item_tax_amount=0, item_name="B"),
				self._item(net_amount=334, item_tax_amount=0, item_name="C"),
			],
		)
		data = pos_invoice_to_dte_data(doc, folio=1, emisor=emisor())
		data.validate()
		self.assertEqual(sum(int(d.monto_item) for d in data.detalles), 1190)

	def test_pos_invoice_like_exenta_41(self):
		doc = SimpleNamespace(
			net_total=5000,
			total_taxes_and_charges=0,
			grand_total=5000,
			posting_date=FIXED_DATE,
			posting_time="12:00:00",
			customer=None,
			customer_name="Cliente Prueba",
			items=[self._item(net_amount=5000, item_tax_amount=0)],
		)
		data = pos_invoice_to_dte_data(doc, folio=3, emisor=emisor())
		data.validate()
		self.assertEqual(data.tipo_dte, constants.TIPO_DTE_BOLETA_EXENTA)
		self.assertEqual(data.totales.monto_exento, 5000)
		self.assertEqual(data.totales.monto_total, 5000)

	@patch("pagosbf.pagosbf.boleta.invoice_to_boleta.frappe.db.get_value", return_value="1-9")
	def test_pos_invoice_like_con_customer_lee_tax_id(self, _mock_gv):
		doc = SimpleNamespace(
			net_total=1000,
			total_taxes_and_charges=190,
			grand_total=1190,
			posting_date=FIXED_DATE,
			posting_time="12:00:00",
			customer="CUST-1",
			customer_name="Con RUT",
			items=[self._item(net_amount=1000, item_tax_amount=190)],
		)
		data = pos_invoice_to_dte_data(doc, folio=1, emisor=emisor())
		self.assertEqual(data.receptor.rut, "1-9")


if __name__ == "__main__":
	unittest.main()
