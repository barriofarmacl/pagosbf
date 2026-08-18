# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Cliente REST boleta SII (api.sii.cl / rahue.sii.cl). Issue whiteboard #69.

El camino SOAP DTEWS + cgi_dte/cgi_rtc es factura. Boleta produccion usa
OpenAPI boleta.electronica (Instructivo 28/10/2021). Tests con requests mockeado:
no pegan a palena ni rahue.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pagosbf.pagosbf.sii.boleta_rest import (
	REST_BOLETA_USER_AGENT,
	is_boleta_rest_url,
)
from pagosbf.pagosbf.sii.dte_upload import SIIUploadError, upload_envio_dte
from pagosbf.pagosbf.sii.sii_client import SIIClient, SIIClientConfig, SIIClientError
from pagosbf.pagosbf.sii.sii_response_xml import parse_sii_estado_payload

_SEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SII:RESPUESTA xmlns:SII="http://www.sii.cl/XMLSchema">
  <SII:RESP_HDR><ESTADO>00</ESTADO><GLOSA>Obtenido</GLOSA></SII:RESP_HDR>
  <SII:RESP_BODY><SEMILLA>030530912644</SEMILLA></SII:RESP_BODY>
</SII:RESPUESTA>
"""

_TOKEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<SII:RESPUESTA xmlns:SII="http://www.sii.cl/XMLSchema">
  <SII:RESP_HDR><ESTADO>00</ESTADO><GLOSA>Token Creado</GLOSA></SII:RESP_HDR>
  <SII:RESP_BODY><TOKEN>P7VQKYLDNHJGP</TOKEN></SII:RESP_BODY>
</SII:RESPUESTA>
"""

_REST_CFG = SIIClientConfig(
	url_semilla="https://api.sii.cl/recursos/v1/boleta.electronica.semilla",
	url_token="https://api.sii.cl/recursos/v1/boleta.electronica.token",
	url_envio="https://rahue.sii.cl/recursos/v1/boleta.electronica.envio",
	url_consulta="https://api.sii.cl/recursos/v1/boleta.electronica.envio",
)


class TestBoletaRestDetect(unittest.TestCase):
	def test_detecta_recursos_v1_y_boleta_electronica(self) -> None:
		self.assertTrue(is_boleta_rest_url(_REST_CFG.url_envio))
		self.assertTrue(is_boleta_rest_url(_REST_CFG.url_semilla))
		self.assertFalse(is_boleta_rest_url("https://palena.sii.cl/cgi_rtc/UPL/DTEUpload"))
		self.assertFalse(is_boleta_rest_url("https://palena.sii.cl/DTEWS/CrSeed.jws"))


class TestParseEstadoRestJson(unittest.TestCase):
	def test_json_epr(self) -> None:
		raw = '{"estado":"EPR","trackid":101412345678901,"rut_emisor":"76957985-0"}'
		p = parse_sii_estado_payload(raw)
		self.assertEqual(p.estado, "EPR")
		self.assertIn("EPR", p.glosa or "EPR")

	def test_xml_sigue_igual(self) -> None:
		p = parse_sii_estado_payload(_SEED_XML)
		self.assertEqual(p.estado, "00")
		self.assertEqual(p.semilla, "030530912644")


class TestBoletaRestSIIClient(unittest.TestCase):
	@patch("pagosbf.pagosbf.sii.sii_client.requests.get")
	def test_get_raw_seed_rest_no_wsdl(self, mock_get: MagicMock) -> None:
		mock_get.return_value = MagicMock(status_code=200, text=_SEED_XML)
		client = SIIClient(_REST_CFG)
		raw = client.get_raw_seed()
		self.assertIn("030530912644", raw)
		args, kwargs = mock_get.call_args
		self.assertEqual(args[0], _REST_CFG.url_semilla)
		self.assertNotIn("WSDL", args[0])
		self.assertEqual(kwargs["headers"]["User-Agent"], REST_BOLETA_USER_AGENT)

	@patch("pagosbf.pagosbf.sii.sii_client.requests.post")
	@patch(
		"pagosbf.pagosbf.sii.sii_client.sign_sii_get_token_envelope",
		return_value="<getToken><item><Semilla>1</Semilla></item></getToken>",
	)
	def test_token_rest_post_xml_body(self, _sign: MagicMock, mock_post: MagicMock) -> None:
		mock_post.return_value = MagicMock(status_code=200, text=_TOKEN_XML)
		client = SIIClient(_REST_CFG)
		mat = MagicMock()
		tok = client.get_token_with_certificate("030530912644", mat)
		self.assertEqual(tok, "P7VQKYLDNHJGP")
		args, kwargs = mock_post.call_args
		self.assertEqual(args[0], _REST_CFG.url_token)
		self.assertIn("application/xml", kwargs["headers"]["Content-Type"])
		self.assertEqual(kwargs["headers"]["User-Agent"], REST_BOLETA_USER_AGENT)
		self.assertIsInstance(kwargs["data"], (bytes, str))

	@patch("pagosbf.pagosbf.sii.sii_client.requests.get")
	def test_consultar_estado_rest_path_y_cookie(self, mock_get: MagicMock) -> None:
		mock_get.return_value = MagicMock(
			status_code=200,
			text='{"estado":"EPR","trackid":999888777666555}',
		)
		client = SIIClient(_REST_CFG)
		raw = client.consultar_estado("999888777666555", token="ABC", rut_emisor="76957985-0")
		self.assertIn("EPR", raw)
		url = mock_get.call_args.args[0]
		self.assertEqual(
			url,
			"https://api.sii.cl/recursos/v1/boleta.electronica.envio/76957985-0-999888777666555",
		)
		self.assertEqual(mock_get.call_args.kwargs["headers"]["Cookie"], "TOKEN=ABC")

	@patch("pagosbf.pagosbf.sii.sii_client.requests.get")
	def test_seed_http_4xx_no_es_00(self, mock_get: MagicMock) -> None:
		mock_get.return_value = MagicMock(status_code=401, text="NoAutorizado")
		client = SIIClient(_REST_CFG)
		with self.assertRaises(SIIClientError) as ctx:
			client.require_semilla()
		self.assertIn("401", str(ctx.exception))


class TestBoletaRestUpload(unittest.TestCase):
	@patch("pagosbf.pagosbf.sii.dte_upload.requests.post")
	def test_trackid_desde_json_rec(self, mock_post: MagicMock) -> None:
		mock_post.return_value = MagicMock(
			status_code=200,
			text='{"estado":"REC","trackid":101412345678901,"file":"archivo.xml"}',
		)
		res = upload_envio_dte(
			_REST_CFG.url_envio,
			b"<EnvioBOLETA/>",
			rut_emisor="76957985-0",
			token="TOKREST",
			rut_digitador="15437220-2",
		)
		self.assertEqual(res.track_id, "101412345678901")
		hdrs = mock_post.call_args.kwargs["headers"]
		self.assertEqual(hdrs["User-Agent"], REST_BOLETA_USER_AGENT)
		self.assertEqual(hdrs["Cookie"], "TOKEN=TOKREST")
		self.assertNotIn("Referer", hdrs)

	@patch("pagosbf.pagosbf.sii.dte_upload.requests.post")
	def test_http_401_sin_token(self, mock_post: MagicMock) -> None:
		mock_post.return_value = MagicMock(status_code=401, text="NoAutorizado")
		with self.assertRaises(SIIUploadError) as ctx:
			upload_envio_dte(
				_REST_CFG.url_envio,
				b"<a/>",
				rut_emisor="76957985-0",
				token="BAD",
			)
		self.assertIn("401", str(ctx.exception))


if __name__ == "__main__":
	unittest.main()
