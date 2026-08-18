"""Deteccion y constantes del API REST de boleta electronica SII.

OpenAPI: https://www4c.sii.cl/bolcoreinternetui/api/openapi.yaml
Produccion: api.sii.cl (semilla/token/consulta) y rahue.sii.cl (POST envio).
Certificacion: apicert.sii.cl y pangal.sii.cl (POST envio).
"""

from __future__ import annotations

from .rut import split_rut

# OpenAPI 1.0.5: User-Agent required en POST /boleta.electronica.envio
REST_BOLETA_USER_AGENT = "Mozilla/4.0 ( compatible; PROG 1.0; Windows NT)"


def is_boleta_rest_url(url: str | None) -> bool:
	"""True si la URL es el API REST boleta (recursos/v1), no DTEWS/cgi_dte."""
	u = (url or "").strip().lower()
	if not u:
		return False
	return "boleta.electronica" in u or "/recursos/v1" in u


def rest_boleta_headers(
	*,
	token: str | None = None,
	accept: str = "application/xml",
) -> dict[str, str]:
	headers = {
		"Accept": accept,
		"User-Agent": REST_BOLETA_USER_AGENT,
	}
	if token:
		headers["Cookie"] = f"TOKEN={token}"
	return headers


def consulta_envio_url(url_consulta: str, rut_emisor: str, track_id: str) -> str:
	"""GET .../boleta.electronica.envio/{rut}-{dv}-{trackid}."""
	body, dv = split_rut(rut_emisor)
	base = (url_consulta or "").rstrip("/")
	tid = str(track_id).strip()
	return f"{base}/{body}-{dv}-{tid}"
