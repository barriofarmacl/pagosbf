# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from pagosbf.pagosbf.dte.folio_allocator import (
	CAFNotFoundError,
	FolioExhaustedError,
	allocate_next_folio,
)


class TestFolioAllocatorFrappe(FrappeTestCase):
	"""Requiere site con app `pagosbf` y DocType `CAF` migrado."""

	@staticmethod
	def _crear_caf(r0: int, r1: int) -> str:
		d = frappe.get_doc(
			{
				"doctype": "CAF",
				"tipo_dte": "39",
				"rango_desde": r0,
				"rango_hasta": r1,
				"fecha_autorizacion": "2026-01-10",
			}
		)
		d.insert(ignore_mandatory=True, ignore_permissions=True)
		return d.name

	def test_secuencia_y_agotamiento(self):
		name = self._crear_caf(100, 102)
		try:
			self.assertEqual(allocate_next_folio(name), 100)
			self.assertEqual(allocate_next_folio(name), 101)
			self.assertEqual(allocate_next_folio(name), 102)
			with self.assertRaises(FolioExhaustedError):
				allocate_next_folio(name)
			doc = frappe.get_doc("CAF", name)
			self.assertEqual(doc.folios_consumidos, 3)
			self.assertEqual(doc.agotado, 1)
		finally:
			frappe.delete_doc("CAF", name, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_caf_inexistente(self):
		with self.assertRaises(CAFNotFoundError):
			allocate_next_folio("CAF-39-0-0-DOES-NOT-EXIST")
		frappe.db.commit()

	def test_asignar_desde_metodo_caf(self):
		n = self._crear_caf(10, 11)
		try:
			doc = frappe.get_doc("CAF", n)
			f1 = doc.asignar_siguiente_folio()
			f2 = doc.asignar_siguiente_folio()
			self.assertEqual(f1, 10)
			self.assertEqual(f2, 11)
		finally:
			frappe.delete_doc("CAF", n, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_agotado_manual_consumidos_bajos_persiste(self):
		"""Desk: marcar Agotado aunque folios_consumidos no refleje el cupo (p. ej. pruebas)."""
		n = self._crear_caf(200, 205)
		try:
			doc = frappe.get_doc("CAF", n)
			doc.agotado = 1
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			again = frappe.get_doc("CAF", n)
			self.assertEqual(int(again.agotado or 0), 1)
		finally:
			frappe.delete_doc("CAF", n, force=True, ignore_permissions=True)
			frappe.db.commit()

	def test_20_folios_sin_gaps(self):
		n = self._crear_caf(1, 20)
		try:
			obtenidos: list[int] = []
			for _ in range(20):
				obtenidos.append(allocate_next_folio(n))
			self.assertEqual(sorted(obtenidos), list(range(1, 21)))
		finally:
			frappe.delete_doc("CAF", n, force=True, ignore_permissions=True)
			frappe.db.commit()


if __name__ == "__main__":
	unittest.main()
