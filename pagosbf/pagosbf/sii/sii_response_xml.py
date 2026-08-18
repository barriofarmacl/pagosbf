"""Parsea XML de respuestas SII (semilla, token, estados) sin depender de NS fijo."""

from __future__ import annotations

from dataclasses import dataclass
import json

from lxml import etree


@dataclass(frozen=True, slots=True)
class SiiRespuesta:
	estado: str
	glosa: str | None
	semilla: str | None
	token: str | None


def _text_first(el: etree._Element, local: str) -> str | None:
	"""Primer subelemento con `local-name() == local`, texto trim."""
	for c in el.iter():
		if isinstance(c.tag, str) and etree.QName(c.tag).localname == local and c.text:
			return c.text.strip()
	return None


def parse_respuesta_sii(respuesta_xml: str) -> SiiRespuesta:
	"""Normaliza un XML `SII:RESPUESTA` (getSeed, getToken, getEstUp)."""
	try:
		root = etree.fromstring(
			respuesta_xml.encode("utf-8")
			if isinstance(respuesta_xml, str)
			else respuesta_xml
		)
	except etree.XMLSyntaxError as exc:
		raise ValueError(f"XML de respuesta SII invalido: {exc}") from exc
	est = _text_first(root, "ESTADO")
	gl = _text_first(root, "GLOSA")
	sm = _text_first(root, "SEMILLA")
	tok = _text_first(root, "TOKEN")
	return SiiRespuesta(
		estado=est or "-1",
		glosa=gl,
		semilla=sm,
		token=tok,
	)


def parse_sii_estado_payload(raw: str) -> SiiRespuesta:
	"""XML SOAP/DTEWS o JSON REST boleta (`estado`, `trackid`)."""
	text = (raw or "").strip()
	if text.startswith("{") or text.startswith("["):
		try:
			data = json.loads(text)
		except json.JSONDecodeError as exc:
			raise ValueError(f"JSON de respuesta SII invalido: {exc}") from exc
		if not isinstance(data, dict):
			raise ValueError("JSON de estado SII no es un objeto")
		est = str(data.get("estado") or "-1")
		glosa = data.get("glosa") or data.get("descripcion")
		if not glosa:
			glosa = est
		return SiiRespuesta(
			estado=est,
			glosa=str(glosa),
			semilla=None,
			token=None,
		)
	return parse_respuesta_sii(raw)
