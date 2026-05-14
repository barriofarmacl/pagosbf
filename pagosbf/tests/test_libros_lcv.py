"""LCV 4811535: insumo desde `DTE Documento` aceptados."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from pagosbf.pagosbf.libros.lcv import (
	advertencias_lcv_desde_dte_documentos,
	totales_periodo_ventas_desde_dte_documentos,
)


def _dte(tipo: int, neto: int, iva: int, total: int, *, exento: int = 0, estado: str = "EPR"):
	return SimpleNamespace(
		tipo_dte=str(tipo),
		monto_neto=neto,
		monto_iva=iva,
		monto_exento=exento,
		monto_total=total,
		estado_envio=estado,
	)


class TestLibroVentasDesdeDTEDocumento(unittest.TestCase):
	def test_agrupa_totales_desde_dte_documentos_aceptados(self) -> None:
		rows = totales_periodo_ventas_desde_dte_documentos(
			[
				_dte(33, 1000, 190, 1190),
				_dte(33, 0, 0, 500, exento=500),
				_dte(61, 200, 38, 238),
				_dte(56, 0, 0, 0),
				_dte(33, 9999, 1900, 11899, estado="ENVIADO"),
			]
		)

		self.assertEqual([r.tpo_doc for r in rows], [33, 56, 61])
		self.assertEqual(rows[0].tot_doc, 2)
		self.assertEqual(rows[0].tot_mnt_neto, 1000)
		self.assertEqual(rows[0].tot_mnt_exe, 500)
		self.assertEqual(rows[0].tot_mnt_iva, 190)
		self.assertEqual(rows[0].tot_mnt_total, 1690)
		self.assertEqual(rows[1].tot_doc, 1)
		self.assertEqual(rows[2].tot_mnt_total, 238)

	def test_advierte_si_no_hay_dte_aceptados_para_lcv(self) -> None:
		warnings = advertencias_lcv_desde_dte_documentos([_dte(33, 100, 19, 119, estado="ENVIADO")])

		self.assertTrue(warnings)
		self.assertIn("DTE Documento aceptados", warnings[0])
		self.assertIn("LCV 4811535", warnings[0])


if __name__ == "__main__":
	unittest.main()
