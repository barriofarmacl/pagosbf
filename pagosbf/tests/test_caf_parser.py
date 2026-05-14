# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import base64
import os
import unittest
from datetime import date

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pagosbf.pagosbf.dte.caf_parser import CAFParserError, parse_autorizacion_bytes, parse_autorizacion_path
from pagosbf.pagosbf.dte import ted_generator, xml_builder
from .dte_fixtures import FIXED_TS, dte_39

# Ruta local opcional: `development/sii/*.xml` (ignorar en git: ver ahi .gitignore).
# Desde `apps/pagosbf/pagosbf/tests/`: 5x .. llega a `development/`.
_SII_CAF = os.path.normpath(
	os.path.join(
		os.path.dirname(__file__),
		*([os.pardir] * 5),
		"sii",
		"FoliosSII7695798539120264241935.xml",
	)
)


def _synthetic_autorizacion(tipo: int = 39) -> bytes:
	"""Autorizacion con RSA sintetica (tests deterministas, no SII)."""
	key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
	pub = key.public_key().public_numbers()
	n_bytes = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
	e_bytes = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
	m_b64 = base64.b64encode(n_bytes).decode("ascii")
	e_b64 = base64.b64encode(e_bytes).decode("ascii")
	priv_pem = key.private_bytes(
		serialization.Encoding.PEM,
		serialization.PrivateFormat.TraditionalOpenSSL,
		serialization.NoEncryption(),
	).decode("ascii")
	xml = f"""<?xml version="1.0"?>
<AUTORIZACION>
<CAF version="1.0">
<DA>
<RE>76000000-0</RE>
<RS>Test SA</RS>
<TD>{tipo}</TD>
<RNG><D>1</D><H>100</H></RNG>
<FA>2026-01-15</FA>
<RSAPK><M>{m_b64}</M><E>{e_b64}</E></RSAPK>
<IDK>100</IDK>
</DA>
<FRMA algoritmo="SHA1withRSA">dGVzdA==</FRMA>
</CAF>
<RSASK>{priv_pem}</RSASK>
</AUTORIZACION>"""
	return xml.encode("utf-8")


class TestCafParser(unittest.TestCase):
	def test_parse_sintetico_td_39(self):
		caf = parse_autorizacion_bytes(_synthetic_autorizacion(39))
		self.assertEqual(caf.tipo_dte, 39)
		self.assertEqual(caf.rango_desde, 1)
		self.assertEqual(caf.rango_hasta, 100)
		self.assertEqual(caf.rut_emisor, "76000000-0")
		self.assertEqual(caf.fecha_autorizacion, date(2026, 1, 15))
		self.assertIn(b"BEGIN RSA PRIVATE KEY", caf.rsa_private_key_pem)
		self.assertIn("<CAF", caf.caf_xml_element_str)
		# Carga de clave para TED
		x = xml_builder.build_dte(dte_39())
		ted = ted_generator.build_signed_ted(x.dd_data, caf, FIXED_TS)
		self.assertIsNotNone(ted.find("FRMT"))

	@unittest.skipUnless(os.path.isfile(_SII_CAF), f"Falta fixture local: {_SII_CAF}")
	def test_parse_archivo_sii_conseguido(self):
		"""Valida que el parser acepta el XML real descargado (solo si existe en disco)."""
		caf = parse_autorizacion_path(_SII_CAF)
		self.assertEqual(caf.tipo_dte, 39)
		self.assertEqual(caf.rango_desde, 1)
		self.assertEqual(caf.rango_hasta, 10)
		self.assertIn("76957985-0", caf.rut_emisor)
		self.assertEqual(caf.fecha_autorizacion, date(2026, 4, 24))

	def test_vacio(self):
		with self.assertRaises(CAFParserError):
			parse_autorizacion_bytes(b"")

	def test_no_rsask(self):
		bad = b"<?xml version='1.0'?><AUTORIZACION><CAF version='1.0'><DA><RE>1-9</RE><RS>X</RS><TD>39</TD><RNG><D>1</D><H>1</H></RNG><FA>2026-01-01</FA><RSAPK><M>aQ==</M><E>AQ==</E></RSAPK><IDK>1</IDK></DA><FRMA algoritmo='SHA1withRSA'>eA==</FRMA></CAF></AUTORIZACION>"
		with self.assertRaises(CAFParserError) as ctx:
			parse_autorizacion_bytes(bad)
		self.assertIn("RSASK", str(ctx.exception))

	def test_parse_sintetico_td_33(self):
		caf = parse_autorizacion_bytes(_synthetic_autorizacion(33))
		self.assertEqual(caf.tipo_dte, 33)

	def test_td_fuera_de_soporte_caf(self):
		b = _synthetic_autorizacion(39)
		s = b.decode("utf-8").replace("<TD>39</TD>", "<TD>52</TD>")
		with self.assertRaises(CAFParserError) as ctx:
			parse_autorizacion_bytes(s.encode("utf-8"))
		self.assertIn("no soportado", str(ctx.exception))
