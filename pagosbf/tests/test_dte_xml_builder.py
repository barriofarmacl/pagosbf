# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest
from dataclasses import replace

from lxml import etree

from pagosbf.pagosbf.dte import xml_builder
from pagosbf.pagosbf.dte.constants import NS_SII_DTE

from pagosbf.pagosbf.dte.types import BoletaReferencia

from .dte_fixtures import FIXED_TS, dte_39, dte_41, synthetic_caf


class TestDteXmlBuilder(unittest.TestCase):
	def test_build_39_documento_id_and_ind_servicio(self):
		data = dte_39()
		draft = xml_builder.build_dte(data)
		self.assertEqual(draft.documento_id, "BOL39-1")
		id_doc = draft.documento_element.find(f"{{{NS_SII_DTE}}}Encabezado/{{{NS_SII_DTE}}}IdDoc")
		self.assertIsNotNone(id_doc)
		ind = id_doc.find(f"{{{NS_SII_DTE}}}IndServicio")
		self.assertIsNotNone(ind)
		self.assertEqual(ind.text, "3")

	def test_build_39_totales_sin_tasa_iva(self):
		data = dte_39()
		draft = xml_builder.build_dte(data)
		totales = draft.documento_element.find(f"{{{NS_SII_DTE}}}Encabezado/{{{NS_SII_DTE}}}Totales")
		self.assertIsNotNone(totales)
		tags = {etree.QName(c.tag).localname: c.text for c in list(totales)}
		self.assertIn("MntNeto", tags)
		self.assertIn("IVA", tags)
		self.assertIn("MntTotal", tags)
		self.assertNotIn("TasaIVA", tags)

	def test_tipo_dte_invalido(self):
		data = dte_39()
		bad = replace(data, tipo_dte=33)
		with self.assertRaises(xml_builder.DTEBuildError):
			xml_builder.build_dte(bad)

	def test_totales_inconsistentes(self):
		data = dte_39()
		from pagosbf.pagosbf.dte.types import DTEBoletaData, TotalesBoleta

		bad = DTEBoletaData(
			tipo_dte=data.tipo_dte,
			folio=data.folio,
			fecha_emision=data.fecha_emision,
			emisor=data.emisor,
			receptor=data.receptor,
			detalles=data.detalles,
			totales=TotalesBoleta(
				monto_neto=840, iva=160, monto_exento=0, monto_total=9999
			),
		)
		with self.assertRaises(xml_builder.DTEBuildError):
			xml_builder.build_dte(bad)

	def test_insert_ted_xsd_pre_firma_39(self):
		data = dte_39()
		caf = synthetic_caf(39)
		draft = xml_builder.build_dte(data)
		from pagosbf.pagosbf.dte import ted_generator

		ted = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		xml_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_builder.validate_dte_xml(xml_bytes)

	def test_insert_ted_xsd_pre_firma_41(self):
		data = dte_41()
		caf = synthetic_caf(41)
		draft = xml_builder.build_dte(data)
		from pagosbf.pagosbf.dte import ted_generator

		ted = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		xml_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_builder.validate_dte_xml(xml_bytes)

	def test_referencia_cod_razon_y_unmditem_orden_xsd(self):
		from dataclasses import replace

		base = dte_39()
		det0 = base.detalles[0]
		det = replace(det0, unidad_medida="Kg")
		data = replace(
			base,
			detalles=(det,),
			referencias=(
				BoletaReferencia(nro_lin_ref=1, cod_ref="SET", razon_ref="CASO-2"),
			),
		)
		draft = xml_builder.build_dte(data)
		doc = draft.documento_element
		ns = NS_SII_DTE
		dets = doc.findall(f"{{{ns}}}Detalle")
		self.assertEqual(len(dets), 1)
		loc = [etree.QName(c.tag).localname for c in dets[0]]
		qty_i = loc.index("QtyItem")
		unm_i = loc.index("UnmdItem")
		prc_i = loc.index("PrcItem")
		self.assertLess(qty_i, unm_i)
		self.assertLess(unm_i, prc_i)
		self.assertEqual(dets[0].find(f"{{{ns}}}UnmdItem").text, "Kg")
		refs = doc.findall(f"{{{ns}}}Referencia")
		self.assertEqual(len(refs), 1)
		self.assertEqual(refs[0].find(f"{{{ns}}}CodRef").text, "SET")
		self.assertEqual(refs[0].find(f"{{{ns}}}RazonRef").text, "CASO-2")
		caf = synthetic_caf(39)
		from pagosbf.pagosbf.dte import ted_generator

		ted = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		xml_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_builder.validate_dte_xml(xml_bytes)

	def test_validate_dte_xml_rechaza_raiz_vacia_contra_xsd(self) -> None:
		"""S4 (capa local): DTE incompleto no pasa XSD; emision debe abortar en validate antes de POST."""
		bad = (
			b'<?xml version="1.0" encoding="ISO-8859-1"?>'
			b'<DTE xmlns="http://www.sii.cl/SiiDte" version="1.0"></DTE>'
		)
		with self.assertRaises(xml_builder.DTEBuildError) as ctx:
			xml_builder.validate_dte_xml(bad, version="boleta")
		self.assertIn("XSD", str(ctx.exception))


if __name__ == "__main__":
	unittest.main()
