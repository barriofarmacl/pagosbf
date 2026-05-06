# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest
from dataclasses import replace
from datetime import datetime

from pagosbf.pagosbf.dte import xml_builder, xml_signer
from pagosbf.pagosbf.dte.signature_audit import audit_boleta_xml_bytes
from pagosbf.pagosbf.dte.envio_builder import (
	CaratulaEmision,
	RUT_SII_CARATULA,
	build_envio_boleta_draft,
	build_envio_boleta_draft_multi,
)
from pagosbf.pagosbf.dte.ted_generator import build_signed_ted

from .dte_fixtures import FIXED_TS, dte_39, pfx_for_tests, synthetic_caf


def _setdte_element_bytes(xml: bytes) -> bytes:
	"""Fragmento ``<SetDTE>...</SetDTE>`` (Caratula + DTEs), sin firma del sobre.

	Con inyeccion pre-firma de ``xsi`` en la raiz, el digest del sobre cambia pero
	este fragmento en bytes debe ser identico entre ambas variantes.
	"""
	i = xml.find(b"<SetDTE")
	j = xml.find(b"</SetDTE>")
	if i < 0 or j < 0:
		raise AssertionError("SetDTE no encontrado")
	return xml[i : j + len(b"</SetDTE>")]


class TestEnvioBuilder(unittest.TestCase):
	def test_build_envio_contiene_caratula_y_dte(self) -> None:
		pw = "test1234"
		mat = xml_signer.load_pfx(pfx_for_tests(pw), pw)
		data = dte_39()
		caf = synthetic_caf(39)
		draft = xml_builder.build_dte(data)
		ted = build_signed_ted(draft.dd_data, caf, FIXED_TS)
		d0 = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_builder.validate_dte_xml(d0, version="boleta")
		d1 = xml_signer.sign_dte(d0, mat, reference_uri=draft.documento_id)
		ca = CaratulaEmision(
			rut_emisor=data.emisor.rut,
			rut_envia=data.emisor.rut,
			rut_receptor=RUT_SII_CARATULA,
			fch_resol=data.emisor.resolucion_fecha,
			nro_resol=data.emisor.resolucion_numero,
			tmst_firma_env=datetime(2026, 4, 24, 15, 0, 0),
			tipo_dte=39,
			set_dte_id="SetDte1",
		)
		env = build_envio_boleta_draft(d1, ca)
		self.assertIn(b"EnvioBOLETA", env)
		self.assertNotIn(b"xmlns:xsi", env)
		self.assertIn(b"Caratula", env)
		self.assertIn(b"RutReceptor", env)
		sob_plain = xml_signer.sign_envio_boleta(
			env,
			mat,
			reference_uri=ca.set_dte_id,
			inject_portal_schema_location=False,
		)
		for a in audit_boleta_xml_bytes(sob_plain):
			self.assertTrue(a.xmldsig_verifies, a.detail)
		sob_upload = xml_signer.sign_envio_boleta(
			env,
			mat,
			reference_uri=ca.set_dte_id,
			inject_portal_schema_location=True,
		)
		for a in audit_boleta_xml_bytes(sob_upload):
			self.assertTrue(a.xmldsig_verifies, a.detail)
		self.assertIn(b"xmlns:xsi", sob_upload)
		self.assertIn(b"xsi:schemaLocation", sob_upload)
		self.assertIn(b"EnvioBOLETA_v11.xsd", sob_upload)
		self.assertEqual(_setdte_element_bytes(sob_plain), _setdte_element_bytes(sob_upload))
		self.assertIn(b"Signature", sob_upload)
		self.assertTrue(sob_upload.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>'))

	def test_build_envio_dos_dtes_firmados(self) -> None:
		pw = "test1234"
		mat = xml_signer.load_pfx(pfx_for_tests(pw), pw)
		caf = synthetic_caf(39)
		signed: list[bytes] = []
		base = dte_39()
		for folio in (1, 2):
			data = replace(base, folio=folio)
			draft = xml_builder.build_dte(data)
			ted = build_signed_ted(draft.dd_data, caf, FIXED_TS)
			d0 = xml_builder.insert_ted(draft, ted, FIXED_TS)
			xml_builder.validate_dte_xml(d0, version="boleta")
			signed.append(xml_signer.sign_dte(d0, mat, reference_uri=draft.documento_id))
		ca = CaratulaEmision(
			rut_emisor=base.emisor.rut,
			rut_envia=base.emisor.rut,
			rut_receptor=RUT_SII_CARATULA,
			fch_resol=base.emisor.resolucion_fecha,
			nro_resol=base.emisor.resolucion_numero,
			tmst_firma_env=datetime(2026, 4, 24, 15, 0, 0),
			tipo_dte=39,
			nro_dtes=2,
			set_dte_id="SetDte1",
		)
		env = build_envio_boleta_draft_multi(signed, ca)
		self.assertIn(b"EnvioBOLETA", env)
		self.assertEqual(env.decode("iso-8859-1").count("<DTE "), 2)
		sob_plain = xml_signer.sign_envio_boleta(
			env,
			mat,
			reference_uri=ca.set_dte_id,
			inject_portal_schema_location=False,
		)
		for a in audit_boleta_xml_bytes(sob_plain):
			self.assertTrue(a.xmldsig_verifies, a.detail)
		sob_upload = xml_signer.sign_envio_boleta(
			env,
			mat,
			reference_uri=ca.set_dte_id,
			inject_portal_schema_location=True,
		)
		for a in audit_boleta_xml_bytes(sob_upload):
			self.assertTrue(a.xmldsig_verifies, a.detail)
		self.assertIn(b"xsi:schemaLocation", sob_upload)
		self.assertEqual(_setdte_element_bytes(sob_plain), _setdte_element_bytes(sob_upload))
		self.assertIn(b"Signature", sob_upload)
		self.assertTrue(sob_upload.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>'))


if __name__ == "__main__":
	unittest.main()
