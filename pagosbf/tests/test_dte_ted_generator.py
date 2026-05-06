# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest
from dataclasses import replace

from lxml import etree

from pagosbf.pagosbf.dte import ted_generator
from pagosbf.pagosbf.dte import xml_builder

from .dte_fixtures import FIXED_TS, dte_39, synthetic_caf


class TestDteTedGenerator(unittest.TestCase):
	def test_tipo_dte_mismatch(self):
		data = dte_39()
		caf = synthetic_caf(41)  # CAF para 41, DTE es 39
		draft = xml_builder.build_dte(data)
		with self.assertRaises(ted_generator.TEDGenerationError) as ctx:
			ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		self.assertIn("no coincide", str(ctx.exception))

	def test_folio_fuera_de_rango(self):
		data = dte_39()
		caf = replace(synthetic_caf(39), rango_desde=10, rango_hasta=20)  # folio 1 invalido
		draft = xml_builder.build_dte(data)
		with self.assertRaises(ted_generator.TEDGenerationError) as ctx:
			ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		self.assertIn("fuera del rango", str(ctx.exception))

	def test_caf_malformado(self):
		data = dte_39()
		caf = replace(
			synthetic_caf(39),
			caf_xml_element_str="<<<no es xml>>>",
		)
		draft = xml_builder.build_dte(data)
		with self.assertRaises(ted_generator.TEDGenerationError) as ctx:
			ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		self.assertIn("no parsea", str(ctx.exception))

	def test_frmt_presente_y_serialize_ted(self):
		data = dte_39()
		caf = synthetic_caf(39)
		draft = xml_builder.build_dte(data)
		ted = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		frmt = ted.find("FRMT")
		self.assertIsNotNone(frmt)
		self.assertEqual(frmt.get("algoritmo"), "SHA1withRSA")
		self.assertTrue(frmt.text and len(frmt.text) > 0)
		s = ted_generator.serialize_ted_for_pdf417(ted)
		self.assertIn("TED", s or "")

	def test_ted_misma_entrada_misma_salida(self):
		"""Mismos dd_data, CAF y timestamp -> TED serializado identico (firma determinista)."""
		caf = synthetic_caf(39)
		draft = xml_builder.build_dte(dte_39())
		a = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		b = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		self.assertEqual(etree.tostring(a, method="c14n", exclusive=True), etree.tostring(b, method="c14n", exclusive=True))
