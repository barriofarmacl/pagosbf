# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spike 2.2: DTE 33 minimo + validacion XSD `public/xsd/factura/`."""

import unittest
from datetime import date

from lxml import etree

from pagosbf.pagosbf.dte import factura_xml
from pagosbf.pagosbf.dte.cert_set_basico_4811534 import (
	totales_caso_4811534_1,
	totales_caso_4811534_2,
	totales_caso_4811534_3,
	totales_caso_4811534_4,
	totales_caso_4811534_6_nc_devolucion,
)
from pagosbf.pagosbf.dte.libro_cv_builder import (
	CaratulaLibroCV,
	TotalesPeriodoLibroCV,
	build_libro_cv_draft_bytes,
)
from pagosbf.pagosbf.dte.set_basico_4811534_dte import (
	SetBasico4811534Emision,
	build_set_basico_4811534_draft,
)
from pagosbf.pagosbf.dte.xml_builder import DTEBuildError
from pagosbf.pagosbf.dte.xml_signer import load_pfx, sign_libro_compra_venta

from .dte_fixtures import FIXED_TS, pfx_for_tests, synthetic_caf


NS = {"sii": "http://www.sii.cl/SiiDte"}


def _set_basico_ctx() -> SetBasico4811534Emision:
	return SetBasico4811534Emision(
		emisor_rut="76000000-0",
		emisor_rzn="Barrio Farma",
		emisor_giro=(
			"VENTA AL POR MENOR DE PRODUCTOS FARMACEUTICOS Y MEDICINALES EN COMERCIO ESPECIALIZADO"
		),
		emisor_acteco="477310",
		fecha_emision=date(2026, 5, 6),
		folio_factura_caso_1=1,
		folio_factura_caso_2=2,
		folio_factura_caso_3=3,
		folio_factura_caso_4=4,
		folio_nc_caso_5=1,
		folio_nc_caso_6=2,
		folio_nc_caso_7=3,
		folio_nd_caso_8=1,
	)


class TestFacturaXmlSpike(unittest.TestCase):
	def test_totales_4811534_1_instructivo(self) -> None:
		# PDF/TXT set basico: neto lineas 363600 + 252693; IVA 19% redondeo estandar.
		self.assertEqual(totales_caso_4811534_1(), (616_293, 117_096, 733_389))

	def test_spike_4811534_1_valida_xsd_sin_ted_ni_firma(self) -> None:
		xml_bytes = factura_xml.build_spike_factura_33_set_basico_4811534_1()
		factura_xml.validate_dte_factura_xml(xml_bytes)

	def test_totales_4811534_2_3_4_6_txt_oficial(self) -> None:
		self.assertEqual(totales_caso_4811534_2(), (3_452_158, 655_910, 4_108_068))
		self.assertEqual(totales_caso_4811534_3(), (903_509, 35_048, 171_667, 1_110_224))
		self.assertEqual(totales_caso_4811534_4(), (1_434_646, 13_612, 272_583, 1_720_841))
		self.assertEqual(totales_caso_4811534_6_nc_devolucion(), (1_679_450, 319_096, 1_998_546))

	def test_set_basico_4811534_envio_ocho_dtes_offline(self) -> None:
		ctx = _set_basico_ctx()
		mat = load_pfx(pfx_for_tests(), "test1234")
		env = factura_xml.build_signed_envio_set_basico_4811534(
			synthetic_caf(33),
			synthetic_caf(61),
			synthetic_caf(56),
			mat,
			FIXED_TS,
			ctx,
			fch_resol=date(2026, 1, 1),
			nro_resol=0,
			rut_envia="76000000-0",
		)
		self.assertIn(b"EnvioDTE", env)
		self.assertEqual(env.decode("ISO-8859-1").count("<DTE "), 8)

	def test_set_basico_4811534_drafts_incluyen_detalles_y_referencias_nc_nd(self) -> None:
		ctx = _set_basico_ctx()
		expectations = {
			"4811534-1": ("33", 2, [("SET", "0", "CASO 4811534-1")]),
			"4811534-2": ("33", 2, [("SET", "0", "CASO 4811534-2")]),
			"4811534-3": ("33", 3, [("SET", "0", "CASO 4811534-3")]),
			"4811534-4": ("33", 3, [("SET", "0", "CASO 4811534-4")]),
			"4811534-5": ("61", 1, [("SET", "0", "CASO 4811534-5"), ("33", "1", "CORRIGE GIRO DEL RECEPTOR")]),
			"4811534-6": ("61", 2, [("SET", "0", "CASO 4811534-6"), ("33", "2", "DEVOLUCION DE MERCADERIAS")]),
			"4811534-7": ("61", 3, [("SET", "0", "CASO 4811534-7"), ("33", "3", "ANULA FACTURA")]),
			"4811534-8": ("56", 1, [("SET", "0", "CASO 4811534-8"), ("61", "1", "ANULA NOTA DE CREDITO ELECTRONICA")]),
		}

		for caso, (tipo, detail_count, refs) in expectations.items():
			with self.subTest(caso=caso):
				draft = build_set_basico_4811534_draft(caso, ctx)
				xml = etree.fromstring(factura_xml._serialize(draft.dte_element))  # noqa: SLF001
				self.assertEqual(xml.findtext(".//sii:TipoDTE", namespaces=NS), tipo)
				self.assertEqual(len(xml.findall(".//sii:Detalle", namespaces=NS)), detail_count)
				actual_refs = [
					(
						ref.findtext("sii:TpoDocRef", namespaces=NS),
						ref.findtext("sii:FolioRef", namespaces=NS),
						ref.findtext("sii:RazonRef", namespaces=NS),
					)
					for ref in xml.findall(".//sii:Referencia", namespaces=NS)
				]
				self.assertEqual(actual_refs, refs)

	def test_pipeline_offline_ted_firma_dte_y_envio_dte(self) -> None:
		caf = synthetic_caf(33)
		mat = load_pfx(pfx_for_tests(), "test1234")
		envio, _draft = factura_xml.build_signed_envio_spike_factura_33(caf, mat, FIXED_TS)
		self.assertIn(b"EnvioDTE", envio)
		self.assertIn(b"<ds:Signature", envio)

	def test_raiz_vacia_rechaza_xsd(self) -> None:
		bad = (
			b'<?xml version="1.0" encoding="ISO-8859-1"?>'
			b'<DTE xmlns="http://www.sii.cl/SiiDte" version="1.0"></DTE>'
		)
		with self.assertRaises(DTEBuildError) as ctx:
			factura_xml.validate_dte_factura_xml(bad)
		self.assertIn("XSD", str(ctx.exception))

	def test_libro_cv_ventas_set_basico_firma_offline(self) -> None:
		mat = load_pfx(pfx_for_tests(), "test1234")
		car = CaratulaLibroCV(
			rut_emisor_libro="76000000-0",
			rut_envia="76000000-0",
			periodo_tributario="2026-05",
			fch_resol="2026-01-01",
			nro_resol=0,
			tipo_operacion="VENTA",
			tipo_libro="MENSUAL",
			tipo_envio="TOTAL",
		)
		rows = [
			TotalesPeriodoLibroCV(33, 4, 48_660, 6_406_606, 1_217_256, None, 7_672_522),
			TotalesPeriodoLibroCV(56, 1, 0, 0, 0, None, 0),
			TotalesPeriodoLibroCV(61, 3, 35_048, 2_582_959, 490_763, None, 3_108_770),
		]
		draft = build_libro_cv_draft_bytes(car, rows, tmst_firma=FIXED_TS, envio_libro_id="LIBROVENTA")
		signed = sign_libro_compra_venta(draft, mat, reference_uri="LIBROVENTA")
		text = signed.decode("ISO-8859-1")
		self.assertIn("<LibroCompraVenta", text)
		self.assertIn("LibroCV_v10.xsd", text)
		self.assertIn('<EnvioLibro ID="LIBROVENTA">', text)
		self.assertIn("<ds:Signature", text)

	def test_libro_cv_compras_txt_firma_offline(self) -> None:
		mat = load_pfx(pfx_for_tests(), "test1234")
		car = CaratulaLibroCV(
			rut_emisor_libro="76000000-0",
			rut_envia="76000000-0",
			periodo_tributario="2026-05",
			fch_resol="2026-01-01",
			nro_resol=0,
			tipo_operacion="COMPRA",
			tipo_libro="MENSUAL",
			tipo_envio="TOTAL",
		)
		rows = [
			TotalesPeriodoLibroCV(30, 2, 0, 93_578, 17_780, None, 111_358),
			TotalesPeriodoLibroCV(33, 2, 11_195, 25_824, 4_907, None, 41_926),
			TotalesPeriodoLibroCV(46, 1, 0, 10_964, 2_083, None, 13_047),
			TotalesPeriodoLibroCV(60, 2, 0, 13_487, 2_563, None, 16_050),
		]
		draft = build_libro_cv_draft_bytes(car, rows, tmst_firma=FIXED_TS, envio_libro_id="LIBROCOMPRA")
		signed = sign_libro_compra_venta(draft, mat, reference_uri="LIBROCOMPRA")
		text = signed.decode("ISO-8859-1")
		self.assertIn("<LibroCompraVenta", text)
		self.assertIn('<EnvioLibro ID="LIBROCOMPRA">', text)
		self.assertIn("<TipoOperacion>COMPRA</TipoOperacion>", text)
		self.assertIn("<ds:Signature", text)


if __name__ == "__main__":
	unittest.main()
