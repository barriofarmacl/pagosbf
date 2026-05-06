# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.pagosbf.dte import signature_audit, ted_generator, xml_builder, xml_signer

from .dte_fixtures import FIXED_TS, dte_39, pfx_for_tests, synthetic_caf


class TestSignatureAudit(unittest.TestCase):
	def test_audit_signed_dte_roundtrip_ok(self):
		pwd = "test1234"
		mat = xml_signer.load_pfx(pfx_for_tests(pwd), pwd)
		draft = xml_builder.build_dte(dte_39())
		ted = ted_generator.build_signed_ted(draft.dd_data, synthetic_caf(39), FIXED_TS)
		dte_bytes = xml_builder.insert_ted(draft, ted, FIXED_TS)
		signed = xml_signer.sign_dte(dte_bytes, mat, reference_uri=draft.documento_id)
		results = signature_audit.audit_boleta_xml_bytes(signed)
		self.assertEqual(len(results), 1)
		r = results[0]
		self.assertTrue(r.modulus_matches_x509, r.detail)
		self.assertTrue(r.xmldsig_verifies, r.detail)


if __name__ == "__main__":
	unittest.main()
