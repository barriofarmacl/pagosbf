"""POST multipart al cgi DTEUpload del SII.

Campos alineados a formularios publicos (rut sender/company, token, `archivo`).
Documentacion: 'Descripcion servicios web DTE' y paginas de ayuda maullin.
"""

from __future__ import annotations

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
	re.compile(r"\bRCH\b[^\n]*?(\d{6,20})", re.IGNORECASE),  # ultimo fallback
)


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
	timeout: float = 30.0,
) -> DteUploadResult:
	"""Envia el XML del sobre o envio. Retorna TrackID (string numerico) y cuerpo bruto.

	Levanta `SIIUploadError` si el HTTP no es 2xx o no se detecta TrackID.
	"""
	b, dv = split_rut(rut_emisor)
	files: dict[str, Any] = {
		"archivo": ("envio.xml", envio_bytes, "text/xml; charset=ISO-8859-1"),
	}
	data = {
		"rutSender": b,
		"dvSender": dv,
		"rutCompany": b,
		"dvCompany": dv,
		"token": token,
	}
	r = requests.post(
		url, data=data, files=files, timeout=timeout, verify=True, headers={}
	)
	text = r.text
	if r.status_code >= 400:
		raise SIIUploadError(f"HTTP {r.status_code}: {text[:800]}")
	tid: str | None = None
	for rx in _TRACK_PATTERNS:
		m = rx.search(text)
		if m:
			tid = m.group(1)
			break
	if tid is None:
		# Linea puramente numerica larga
		for line in text.splitlines():
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
