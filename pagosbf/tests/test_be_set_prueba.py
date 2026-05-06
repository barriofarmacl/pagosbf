# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Totales del set de prueba BE vs cuadro SII."""

from __future__ import annotations

import unittest

from pagosbf.pagosbf.dte.be_set_prueba import be_set_prueba_dte_data

from .dte_fixtures import FIXED_DATE, FIXED_TS, emisor


class TestBeSetPrueba(unittest.TestCase):
	def test_caso_1_totales(self) -> None:
		d = be_set_prueba_dte_data(1, emisor=emisor(), folio=11, fecha_emision=FIXED_DATE, timestamp_firma=FIXED_TS)
		self.assertEqual(d.totales.monto_total, 29800)
		self.assertEqual(d.totales.monto_neto, 25042)
		self.assertEqual(d.totales.iva, 4758)
		self.assertEqual(d.referencias[0].razon_ref, "CASO-1")

	def test_caso_2_totales(self) -> None:
		d = be_set_prueba_dte_data(2, emisor=emisor(), folio=12, fecha_emision=FIXED_DATE, timestamp_firma=FIXED_TS)
		self.assertEqual(d.totales.monto_total, 2040)
		self.assertEqual(d.totales.monto_neto, 1714)
		self.assertEqual(d.totales.iva, 326)

	def test_caso_3_totales(self) -> None:
		d = be_set_prueba_dte_data(3, emisor=emisor(), folio=13, fecha_emision=FIXED_DATE, timestamp_firma=FIXED_TS)
		self.assertEqual(d.totales.monto_total, 4100)
		self.assertEqual(d.totales.monto_neto, 3445)
		self.assertEqual(d.totales.iva, 655)

	def test_caso_4_mixto(self) -> None:
		d = be_set_prueba_dte_data(4, emisor=emisor(), folio=14, fecha_emision=FIXED_DATE, timestamp_firma=FIXED_TS)
		self.assertEqual(d.totales.monto_total, 14720)
		self.assertEqual(d.totales.monto_neto, 10689)
		self.assertEqual(d.totales.iva, 2031)
		self.assertEqual(d.totales.monto_exento, 2000)
		self.assertTrue(d.detalles[1].indica_exento)

	def test_caso_5_kg(self) -> None:
		d = be_set_prueba_dte_data(5, emisor=emisor(), folio=15, fecha_emision=FIXED_DATE, timestamp_firma=FIXED_TS)
		self.assertEqual(d.totales.monto_total, 3500)
		self.assertEqual(d.detalles[0].unidad_medida, "Kg")


if __name__ == "__main__":
	unittest.main()
