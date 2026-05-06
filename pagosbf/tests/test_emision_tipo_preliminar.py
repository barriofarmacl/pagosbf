# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

from __future__ import annotations

import unittest
from types import SimpleNamespace

from pagosbf.pagosbf.boleta.emision import _tipo_preliminar
from pagosbf.pagosbf.dte import constants


class TestTipoPreliminarInvoiceLike(unittest.TestCase):
	def test_iva_positivo_afecta(self):
		d = SimpleNamespace(total_taxes_and_charges=160)
		self.assertEqual(_tipo_preliminar(d), constants.TIPO_DTE_BOLETA_AFECTA)

	def test_sin_iva_exenta(self):
		d = SimpleNamespace(total_taxes_and_charges=0)
		self.assertEqual(_tipo_preliminar(d), constants.TIPO_DTE_BOLETA_EXENTA)


if __name__ == "__main__":
	unittest.main()
