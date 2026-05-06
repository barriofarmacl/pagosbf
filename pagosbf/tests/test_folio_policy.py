# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.pagosbf.dte import folio_policy


class TestFolioPolicy(unittest.TestCase):
	def test_cupo_folios(self):
		self.assertEqual(folio_policy.cupo_folios(1, 10), 10)
		self.assertEqual(folio_policy.cupo_folios(5, 5), 1)

	def test_folio_a_asignar(self):
		self.assertEqual(folio_policy.folio_a_asignar(1, 0), 1)
		self.assertEqual(folio_policy.folio_a_asignar(1, 9), 10)

	def test_rechaza_rango_invalido(self):
		with self.assertRaises(ValueError):
			folio_policy.cupo_folios(2, 1)

	def test_rechaza_consumidos_neg(self):
		with self.assertRaises(ValueError):
			folio_policy.folio_a_asignar(1, -1)

	def test_ultimo_folio_marca_agotado(self):
		self.assertTrue(folio_policy.agotado_despues_de_asignar(1, 3, 2))  # 3=ultimo, cupo=3, fc=2->+1=3
		self.assertFalse(folio_policy.agotado_despues_de_asignar(1, 10, 0))

	def test_folio_snapshot(self):
		s = folio_policy.FolioSnapshot(1, 2, 0, False)
		self.assertTrue(s.puede_asignar())
		s2 = folio_policy.FolioSnapshot(1, 1, 1, True)
		self.assertFalse(s2.puede_asignar())
