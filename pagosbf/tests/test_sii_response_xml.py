# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.pagosbf.sii.sii_response_xml import parse_respuesta_sii

_NS = 'xmlns:sii="http://www.sii.cl/SiiDte"'

# Respuestas con NS distintos: el parser usa local-name.
_SAMPLE_SEED = f"""<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA sii:COD="0" sii:MSG="0" {_NS}>
  <sii:RESP_HDR>
    <sii:ESTADO>00</sii:ESTADO>
  </sii:RESP_HDR>
  <sii:RESP_BODY>
    <sii:SEMILLA>ABCD1234</sii:SEMILLA>
  </sii:RESP_BODY>
</sii:RESPUESTA>
"""

_SAMPLE_TOKEN = f"""<?xml version="1.0" encoding="UTF-8"?>
<sii:RESPUESTA {_NS}>
  <sii:RESP_HDR>
    <sii:ESTADO>00</sii:ESTADO>
  </sii:RESP_HDR>
  <sii:RESP_BODY>
    <sii:TOKEN>tok_test_1</sii:TOKEN>
  </sii:RESP_BODY>
</sii:RESPUESTA>
"""


class TestParseRespuestaSii(unittest.TestCase):
	def test_get_seed_baseline(self) -> None:
		p = parse_respuesta_sii(_SAMPLE_SEED)
		self.assertEqual(p.estado, "00")
		self.assertEqual(p.semilla, "ABCD1234")
		self.assertIsNone(p.token)

	def test_get_token_baseline(self) -> None:
		p = parse_respuesta_sii(_SAMPLE_TOKEN)
		self.assertEqual(p.estado, "00")
		self.assertEqual(p.token, "tok_test_1")
		self.assertIsNone(p.semilla)

	def test_malformed_xml(self) -> None:
		with self.assertRaises(ValueError) as ctx:
			parse_respuesta_sii("not xml")
		self.assertIn("XML", str(ctx.exception))


if __name__ == "__main__":
	unittest.main()
