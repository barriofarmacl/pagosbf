# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""LCE 4811536: calculo IVA uso comun y advertencias previas al envio."""

from __future__ import annotations

import unittest
from decimal import Decimal

from pagosbf.pagosbf.libros.lce import (
	LCE_FACTOR_IVA_USO_COMUN,
	advertencias_lce_4811536,
	build_libro_compras_4811536_draft_bytes,
	calculos_iva_uso_comun_4811536,
	movimientos_set_4811536,
)


class TestLibroCompras4811536(unittest.TestCase):
	def test_calcula_iva_uso_comun_con_factor_060(self) -> None:
		calculos = calculos_iva_uso_comun_4811536(movimientos_set_4811536())

		self.assertEqual(len(calculos), 1)
		self.assertEqual(calculos[0].tipo_documento, 30)
		self.assertEqual(calculos[0].folio, "781")
		self.assertEqual(calculos[0].factor, Decimal("0.60"))
		self.assertEqual(calculos[0].monto_afecto, 30_291)
		self.assertEqual(calculos[0].iva, 5_755)
		self.assertEqual(calculos[0].credito_iva_uso_comun, 3_453)
		self.assertEqual(LCE_FACTOR_IVA_USO_COMUN, Decimal("0.60"))

	def test_advierte_lce_incompleto_sin_movimientos_de_compra(self) -> None:
		warnings = advertencias_lce_4811536([])

		self.assertTrue(warnings)
		self.assertIn("4811536", warnings[0])
		self.assertIn("movimientos de compra", warnings[0])

	def test_genera_borrador_libro_compras_4811536_con_totales_txt(self) -> None:
		xml = build_libro_compras_4811536_draft_bytes(
			rut_emisor_libro="76000000-0",
			rut_envia="76000000-0",
			periodo_tributario="2026-05",
			fch_resol="2026-01-01",
			nro_resol=0,
		).decode("ISO-8859-1")

		self.assertIn("<LibroCompraVenta", xml)
		self.assertIn("<TipoOperacion>COMPRA</TipoOperacion>", xml)
		self.assertIn("<TpoDoc>30</TpoDoc>", xml)
		self.assertIn("<TotMntNeto>93578</TotMntNeto>", xml)
		self.assertIn("<TpoDoc>33</TpoDoc>", xml)
		self.assertIn("<TotMntExe>11195</TotMntExe>", xml)


if __name__ == "__main__":
	unittest.main()
