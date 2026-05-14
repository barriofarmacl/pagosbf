# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from lxml import etree

from pagosbf.pagosbf.dte import ted_generator, xml_builder, xml_signer

from .dte_fixtures import FIXED_TS, dte_39, pfx_for_tests, synthetic_caf

_DS = "http://www.w3.org/2000/09/xmldsig#"
_NS = {"ds": _DS}


class TestDteXmlSigner(unittest.TestCase):
	def test_load_pfx_password_incorrecta(self):
		pfx = pfx_for_tests("okpass")
		with self.assertRaises(xml_signer.XMLSignerError):
			xml_signer.load_pfx(pfx, "otra")

	def test_load_pfx_y_sign_dte_verify(self):
		pwd = "test1234"
		pfx = pfx_for_tests(pwd)
		mat = xml_signer.load_pfx(pfx, pwd)
		data = dte_39()
		caf = synthetic_caf(39)
		draft = xml_builder.build_dte(data)
		ted = ted_generator.build_signed_ted(draft.dd_data, caf, FIXED_TS)
		dte_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_bytes = xml_signer.sign_dte(dte_bytes, mat, reference_uri=draft.documento_id)
		self.assertTrue(xml_signer.verify_signature(xml_bytes, mat))

	def test_firma_dte_alinea_xsd_sii_xmldsignature_v10(self):
		"""Firma del Documento: mismo perfil que exige portal / xmldsignature_v10.xsd."""
		pwd = "test1234"
		mat = xml_signer.load_pfx(pfx_for_tests(pwd), pwd)
		data = dte_39()
		draft = xml_builder.build_dte(data)
		ted = ted_generator.build_signed_ted(draft.dd_data, synthetic_caf(39), FIXED_TS)
		dte_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		xml_bytes = xml_signer.sign_dte(dte_bytes, mat, reference_uri=draft.documento_id)
		root = etree.fromstring(xml_bytes)
		cm = root.find(".//ds:CanonicalizationMethod", namespaces=_NS)
		self.assertIsNotNone(cm)
		self.assertEqual(
			cm.get("Algorithm"),
			"http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
		)
		transforms = root.findall(".//ds:Reference/ds:Transforms/ds:Transform", namespaces=_NS)
		self.assertEqual(len(transforms), 1)
		self.assertEqual(
			transforms[0].get("Algorithm"),
			"http://www.w3.org/2000/09/xmldsig#enveloped-signature",
		)
		keyinfo = root.find(".//ds:KeyInfo", namespaces=_NS)
		self.assertIsNotNone(keyinfo)
		kids = list(keyinfo)
		self.assertGreaterEqual(len(kids), 2)
		self.assertEqual(kids[0].tag, "{%s}KeyValue" % _DS)
		self.assertEqual(kids[1].tag, "{%s}X509Data" % _DS)

	def test_malformed_xml_dte(self):
		mat = xml_signer.load_pfx(pfx_for_tests("x"), "x")
		with self.assertRaises(xml_signer.XMLSignerError):
			xml_signer.sign_dte(b"not xml", mat, reference_uri="BOL39-1")

	def test_sign_get_token_envelope_sii_manual_layout(self):
		"""SII AUTAUTOM cap. 8: Signature hijo de getToken, hermano de item (no dentro de item).

		El XML usa elementos XMLDSig sin prefijo ``ds:`` y ``xmlns`` en ``Signature``, como el manual / xmlsec.
		``signxml.XMLVerifier`` busca nodos ``ds:*`` y no valida este perfil; aceptacion real = SII ``getToken``.
		"""
		pwd = "test1234"
		mat = xml_signer.load_pfx(pfx_for_tests(pwd), pwd)
		out = xml_signer.sign_sii_get_token_envelope("000002360958", mat)
		root = etree.fromstring(out.encode("utf-8"))
		self.assertEqual(root.tag, "getToken")
		children = list(root)
		self.assertEqual(len(children), 2)
		self.assertEqual(children[0].tag, "item")
		self.assertEqual(
			children[1].tag,
			"{%s}Signature" % _DS,
		)
		sem = children[0].find("Semilla")
		self.assertIsNotNone(sem)
		self.assertEqual(sem.text, "000002360958")
		self.assertIsNone(
			children[0].find("{%s}Signature" % _DS),
		)
		self.assertIn('xmlns="http://www.w3.org/2000/09/xmldsig#"', out)
		self.assertNotIn("ds:Signature", out)
