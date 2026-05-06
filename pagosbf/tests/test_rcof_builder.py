# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Tests: Consumo de Folios (RCOF) — agregación, XSD firmado, firma XMLDSig."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from pagosbf.pagosbf.dte import xml_signer
from pagosbf.pagosbf.dte.rcof_builder import (
	CaratulaRcof,
	ResumenRcof,
	aggregate_resumenes_from_envio_boleta_xml,
	build_consumo_folios_draft_bytes,
	validate_rcof_xml_signed,
)
from .dte_fixtures import pfx_for_tests

_NS = "http://www.sii.cl/SiiDte"

# Dos boletas 39 con Totales dentro de Encabezado (estructura SII real).
_MIN_ENVIO_TWO_DTE = f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<EnvioBOLETA xmlns="{_NS}" version="1.0">
  <SetDTE ID="SetDte1">
    <Caratula version="1.0"><RutEmisor>76000000-0</RutEmisor></Caratula>
    <DTE xmlns="{_NS}" version="1.0">
      <Documento ID="BOL39-10">
        <Encabezado>
          <IdDoc><TipoDTE>39</TipoDTE><Folio>10</Folio></IdDoc>
          <Totales><MntNeto>100</MntNeto><IVA>19</IVA><MntTotal>119</MntTotal></Totales>
        </Encabezado>
      </Documento>
    </DTE>
    <DTE xmlns="{_NS}" version="1.0">
      <Documento ID="BOL39-11">
        <Encabezado>
          <IdDoc><TipoDTE>39</TipoDTE><Folio>11</Folio></IdDoc>
          <Totales><MntNeto>200</MntNeto><IVA>38</IVA><MntTotal>238</MntTotal></Totales>
        </Encabezado>
      </Documento>
    </DTE>
  </SetDTE>
</EnvioBOLETA>
""".encode(
	"ISO-8859-1"
)


class TestRcofAggregate(unittest.TestCase):
	def test_agrega_dos_boletas_39(self):
		res = aggregate_resumenes_from_envio_boleta_xml(_MIN_ENVIO_TWO_DTE)
		self.assertEqual(len(res), 1)
		r = res[0]
		self.assertEqual(r.tipo_documento, 39)
		self.assertEqual(r.mnt_neto, 300)
		self.assertEqual(r.mnt_iva, 57)
		self.assertEqual(r.mnt_total, 357)
		self.assertEqual(r.folios_emitidos, 2)
		self.assertEqual(r.rangos_utilizados, ((10, 11),))


class TestRcofSignXsd(unittest.TestCase):
	def test_build_sign_validate_xsd(self):
		res = [
			ResumenRcof(
				tipo_documento=39,
				mnt_neto=100,
				mnt_iva=19,
				tasa_iva=19.0,
				mnt_total=119,
				folios_emitidos=1,
				folios_anulados=0,
				folios_utilizados=1,
				rangos_utilizados=((1, 1),),
			)
		]
		car = CaratulaRcof(
			rut_emisor="76000000-0",
			rut_envia="76000000-0",
			fch_resol="2020-01-01",
			nro_resol=0,
			fch_inicio="2026-05-01",
			fch_final="2026-05-01",
			sec_envio=1,
			tmst_firma_env=datetime(2026, 5, 1, 10, 0, 0),
		)
		draft = build_consumo_folios_draft_bytes(car, res)
		self.assertIn(b"<ConsumoFolios", draft)
		self.assertNotIn(b"ds:Signature", draft)

		mat = xml_signer.load_pfx(pfx_for_tests(), "test1234")
		signed = xml_signer.sign_consumo_folios(draft, mat)
		self.assertIn(b"<ds:Signature", signed)
		validate_rcof_xml_signed(signed)
		self.assertTrue(xml_signer.verify_signature(signed, mat))

	def test_fixture_envio_agrega_si_existe(self):
		# .../frappe-bench/apps/pagosbf/pagosbf/tests -> parents[5] = workspace development
		envio = (
			Path(__file__).resolve().parents[5]
			/ "sii"
			/ "out_be_certificacion"
			/ "envio_firmado.xml"
		)
		if not envio.is_file():
			self.skipTest(f"sin fixture {envio}")
		res = aggregate_resumenes_from_envio_boleta_xml(envio.read_bytes())
		self.assertTrue(res)
		self.assertEqual(res[0].tipo_documento, 39)


if __name__ == "__main__":
	unittest.main()
