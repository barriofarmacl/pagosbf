# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""DTEUpload: token en Cookie (comportamiento CGI SII)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pagosbf.pagosbf.sii.dte_upload import DteUploadResult, upload_envio_dte


class TestDteUploadTokenCookie(unittest.TestCase):
	@patch("pagosbf.pagosbf.sii.dte_upload.requests.post")
	def test_trackid_from_html_escaped_recepciondte(self, mock_post: MagicMock) -> None:
		mock_post.return_value = MagicMock(
			status_code=200,
			text='<!--?xml version="1.0"?-->\n&lt;RECEPCIONDTE&gt;\n&lt;TRACKID&gt;0248796212&lt;/TRACKID&gt;\n&lt;/RECEPCIONDTE&gt;\n',
		)
		res: DteUploadResult = upload_envio_dte(
			"https://maullin.sii.cl/cgi_dte/UPL/DTEUpload",
			b"<a/>",
			rut_emisor="76957985-0",
			token="T",
			rut_digitador="15437220-2",
		)
		self.assertEqual(res.track_id, "0248796212")

	@patch("pagosbf.pagosbf.sii.dte_upload.requests.post")
	def test_token_in_cookie_not_in_multipart_data(self, mock_post: MagicMock) -> None:
		mock_post.return_value = MagicMock(
			status_code=200,
			text="RCH: ACEPTADO TRACK: 88112233",
		)
		res: DteUploadResult = upload_envio_dte(
			"https://maullin.sii.cl/cgi_dte/UPL/DTEUpload",
			b"<?xml version='1.0'?><a/>",
			rut_emisor="76957985-0",
			token="TOK_ABC_123",
			rut_digitador="15437220-2",
		)
		self.assertEqual(res.track_id, "88112233")
		kwargs = mock_post.call_args.kwargs
		self.assertEqual(kwargs["headers"]["Cookie"], "TOKEN=TOK_ABC_123")
		self.assertEqual(kwargs["headers"]["Referer"], "https://barriofarma.cl/")
		self.assertIn("Mozilla/4.0", kwargs["headers"]["User-Agent"])
		self.assertNotIn("token", kwargs["data"])
		self.assertEqual(kwargs["files"]["archivo"][0], "archivo.xml")
		self.assertEqual(kwargs["data"]["rutSender"], "15437220")
		self.assertEqual(kwargs["data"]["dvSender"], "2")
		self.assertEqual(kwargs["data"]["rutCompany"], "76957985")
		self.assertEqual(kwargs["data"]["dvCompany"], "0")
