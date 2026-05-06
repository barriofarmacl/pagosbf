# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.pagosbf.dte.sii_xml_bytes import finalize_sii_xml_bytes


class TestSiiXmlBytes(unittest.TestCase):
	def test_finalize_double_quotes_declaration(self) -> None:
		raw = b"<?xml version='1.0' encoding='ISO-8859-1'?><a/>"
		out = finalize_sii_xml_bytes(raw)
		self.assertTrue(out.startswith(b'<?xml version="1.0" encoding="ISO-8859-1"?>'))
		self.assertTrue(out.endswith(b"<a/>"))

	def test_finalize_passthrough_if_already_double_quotes(self) -> None:
		raw = b'<?xml version="1.0" encoding="ISO-8859-1"?><a/>'
		self.assertEqual(finalize_sii_xml_bytes(raw), raw)


if __name__ == "__main__":
	unittest.main()
