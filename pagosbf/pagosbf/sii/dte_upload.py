"""POST multipart al cgi DTEUpload del SII.

Campos alineados a integraciones publicas: multipart con rut sender/company y
``archivo``; el **token** va en cabecera ``Cookie: TOKEN=...`` como Maullin/Palena
esperan (p. ej. referencia ``python-sii`` / CGI DTEUpload). Enviar el token solo
como campo de formulario puede producir ``ptr NULL (ptrTkn)``.
Documentacion: 'Descripcion servicios web DTE' y paginas de ayuda maullin.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

import requests

from .rut import split_rut


class SIIUploadError(Exception):
	"""Error de envio o respuesta sin TrackID."""


# Variantes observadas en integraciones; el SII a veces devuelve RCH + TRACK/TrackID
_TRACK_PATTERNS = (
	re.compile(r"TRACK[:\s]+(\d+)", re.IGNORECASE),
	re.compile(r"TRACKID[:\s]+(\d+)", re.IGNORECASE),
	re.compile(r"<TRACKID>\s*(\d+)\s*</TRACKID>", re.IGNORECASE),
	re.compile(r"\bRCH\b[^\n]*?(\d{6,20})", re.IGNORECASE),  # ultimo fallback
)


def _text_for_track_parse(raw: str) -> str:
	"""Maullin a veces devuelve RECEPCIONDTE con entidades HTML (&lt;TRACKID&gt;...)."""
	return html.unescape(raw or "")


@dataclass(frozen=True, slots=True)
class DteUploadResult:
	track_id: str
	resumen: str
	response_text: str
	status_code: int


def upload_envio_dte(
	url: str,
	envio_bytes: bytes,
	*,
	rut_emisor: str,
	token: str,
	rut_digitador: str | None = None,
	timeout: float = 30.0,
) -> DteUploadResult:
	"""Envia el XML del sobre o envio. Retorna TrackID (string numerico) y cuerpo bruto.

	``rut_emisor`` es el RUT del contribuyente dueño del DTE (``RUTEmisor`` en el XML).
	``rut_digitador`` es el RUT del firmante del token (certificado digital). El CGI
	``DTEUpload`` usa ``rutSender``/``dvSender`` para enlazar el ``token``; si se envia
	el RUT empresa en ``rutSender`` pero el token fue emitido para el representante,
	Maullin/Palena puede responder ``ptr NULL (ptrTkn)``.

	Si ``rut_digitador`` es None, se usa ``rut_emisor`` en ambos pares de campos
	(contribuyente que tambien firma).

	Levanta `SIIUploadError` si el HTTP no es 2xx o no se detecta TrackID.
	"""
	sender = (rut_digitador or rut_emisor).strip()
	b_s, dv_s = split_rut(sender)
	b_c, dv_c = split_rut(rut_emisor)
	files: dict[str, Any] = {
		# El CGI historico referencia el archivo como "archivo.xml" en la
		# respuesta RECEPCIONDTE y en ejemplos oficiales/publicos de DTEUpload.
		"archivo": ("archivo.xml", envio_bytes, "text/xml; charset=ISO-8859-1"),
	}
	data = {
		"rutSender": b_s,
		"dvSender": dv_s,
		"rutCompany": b_c,
		"dvCompany": dv_c,
	}
	headers = {
		"Accept": "image/gif, image/x-xbitmap, image/jpeg, image/pjpeg,application/vnd.ms-powerpoint, application/ms-excel,application/msword, */*",
		"Accept-Language": "es-cl",
		"Cache-Control": "no-cache",
		"Cookie": f"TOKEN={token}",
		"Referer": "https://barriofarma.cl/",
		"User-Agent": "Mozilla/4.0 (compatible; PROG 1.0; Windows NT 5.0; YComp 5.0.2.4)",
	}
	r = requests.post(
		url,
		data=data,
		files=files,
		timeout=timeout,
		verify=True,
		headers=headers,
	)
	text = r.text
	if r.status_code >= 400:
		raise SIIUploadError(f"HTTP {r.status_code}: {text[:800]}")
	parse_text = _text_for_track_parse(text)
	tid: str | None = None
	for rx in _TRACK_PATTERNS:
		m = rx.search(parse_text)
		if m:
			tid = m.group(1)
			break
	if tid is None:
		# Linea puramente numerica larga
		for line in parse_text.splitlines():
			if line.strip().isdigit() and len(line.strip()) >= 6:
				tid = line.strip()
				break
	if tid is None:
		raise SIIUploadError(f"Respuesta sin TrackID: {text[:2000]!r}")
	return DteUploadResult(
		track_id=tid,
		resumen=text[:500],
		response_text=text,
		status_code=r.status_code,
	)
