# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.pagosbf.sii.rut import rut_para_dte_xml, rut_para_soap_empresa, split_rut


class TestRutChile(unittest.TestCase):
	def test_split_puntos(self) -> None:
		self.assertEqual(split_rut("12.345.678-5"), ("12345678", "5"))

	def test_split_sin_puntos(self) -> None:
		self.assertEqual(split_rut("12345678-5"), ("12345678", "5"))

	def test_dv_k_upper(self) -> None:
		b, d = split_rut("1-9")
		self.assertEqual(d, "9")
		b2, d2 = split_rut("12k")
		self.assertEqual((b2, d2), ("12", "K"))

	def test_rut_para_soap_empresa_zerofill(self) -> None:
		self.assertEqual(
			rut_para_soap_empresa("1-9"), ("00000001", "9")
		)
		self.assertEqual(
			rut_para_soap_empresa("76.957.985-0"), ("76957985", "0")
		)

	def test_rut_invalido(self) -> None:
		with self.assertRaises(ValueError):
			split_rut("")

	def test_rut_para_dte_xml_contiguo_y_puntos(self) -> None:
		self.assertEqual(rut_para_dte_xml("769579850"), "76957985-0")
		self.assertEqual(rut_para_dte_xml("76.957.985-0"), "76957985-0")
		self.assertEqual(rut_para_dte_xml(""), "")


if __name__ == "__main__":
	unittest.main()
