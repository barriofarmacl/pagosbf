"""Ajustes de bytes XML para validadores del SII (portal / schema)."""

from __future__ import annotations

import re

from .constants import (
	CONSUMO_FOLIOS_SCHEMA_LOCATION,
	ENVIO_BOLETA_SCHEMA_LOCATION,
	ENVIO_DTE_SCHEMA_LOCATION,
	LIBRO_CV_SCHEMA_LOCATION,
	NS_XML_SCHEMA_INSTANCE,
)

# Raiz minimal que emite `lxml` al serializar `EnvioBOLETA` sin `xmlns:xsi` en el arbol.
_ENVIO_OPEN_MIN = b'<EnvioBOLETA xmlns="http://www.sii.cl/SiiDte" version="1.0">'
_ENVIO_OPEN_SCHEMA = (
	b'<EnvioBOLETA xmlns="http://www.sii.cl/SiiDte" xmlns:xsi="'
	+ NS_XML_SCHEMA_INSTANCE.encode("ascii")
	+ b'" version="1.0" xsi:schemaLocation="'
	+ ENVIO_BOLETA_SCHEMA_LOCATION.encode("ascii")
	+ b'">'
)

_ENVIO_DTE_OPEN_MIN = b'<EnvioDTE xmlns="http://www.sii.cl/SiiDte" version="1.0">'
_ENVIO_DTE_OPEN_SCHEMA = (
	b'<EnvioDTE xmlns="http://www.sii.cl/SiiDte" xmlns:xsi="'
	+ NS_XML_SCHEMA_INSTANCE.encode("ascii")
	+ b'" version="1.0" xsi:schemaLocation="'
	+ ENVIO_DTE_SCHEMA_LOCATION.encode("ascii")
	+ b'">'
)

_CONSUMO_OPEN_MIN = b'<ConsumoFolios xmlns="http://www.sii.cl/SiiDte" version="1.0">'
_CONSUMO_OPEN_SCHEMA = (
	b'<ConsumoFolios xmlns="http://www.sii.cl/SiiDte" xmlns:xsi="'
	+ NS_XML_SCHEMA_INSTANCE.encode("ascii")
	+ b'" version="1.0" xsi:schemaLocation="'
	+ CONSUMO_FOLIOS_SCHEMA_LOCATION.encode("ascii")
	+ b'">'
)

_LIBRO_CV_OPEN_MIN = b'<LibroCompraVenta xmlns="http://www.sii.cl/SiiDte" version="1.0">'
_LIBRO_CV_OPEN_SCHEMA = (
	b'<LibroCompraVenta xmlns="http://www.sii.cl/SiiDte" xmlns:xsi="'
	+ NS_XML_SCHEMA_INSTANCE.encode("ascii")
	+ b'" version="1.0" xsi:schemaLocation="'
	+ LIBRO_CV_SCHEMA_LOCATION.encode("ascii")
	+ b'">'
)

# lxml `etree.tostring(xml_declaration=True)` emite comillas simples; XSD y ejemplos SII usan comillas dobles.
_LXML_DECL = re.compile(
	br"^<\?xml\s+version='1\.0'\s+encoding='ISO-8859-1'\s*\?>",
)


def finalize_sii_xml_bytes(data: bytes) -> bytes:
	"""Reemplaza la declaracion XML al estilo de los XSD SII (comillas dobles).

	En el portal de carga manual se ha observado el rechazo **CHR-00001** con la
	cabecera que genera lxml (`version='1.0'`). El digest XMLDSig no incluye la
	prolog; el cambio es seguro despues de firmar.
	"""
	m = _LXML_DECL.match(data)
	if not m:
		return data
	return b'<?xml version="1.0" encoding="ISO-8859-1"?>' + data[m.end() :]


def inject_envio_boleta_xsi_schema_declaration(data: bytes) -> bytes:
	"""Añade en la raiz ``xmlns:xsi`` y ``xsi:schemaLocation`` (solo etiqueta de apertura).

	Uso: **antes** de parsear y firmar el sobre en ``sign_envio_boleta``. El
	portal puede rechazar **SCH-00001** si falta. Con C14N inclusive, el digest
	de la referencia ``#SetDte1`` depende de los namespace nodes del ancestro
	``EnvioBOLETA``; aplicar esto **despues** de firmar invalida la firma (RFR).

	No re-parsea los ``<DTE>`` (solo reemplazo por bytes de la apertura minima);
	``build_envio_boleta_draft_multi`` sigue incrustando DTE firmados como bytes
	para no romper XMLDSig por documento (DTE-3-505).
	"""
	i = 0
	if data.startswith(b"<?xml"):
		p = data.find(b"?>")
		if p == -1:
			return data
		i = p + 2
	payload = data[i:].lstrip()
	if not payload.startswith(_ENVIO_OPEN_MIN):
		if payload.startswith(b"<EnvioBOLETA") and b"xsi:schemaLocation=" in payload[:400]:
			return data
		return data
	replaced = _ENVIO_OPEN_SCHEMA + payload[len(_ENVIO_OPEN_MIN) :]
	return data[:i] + replaced


def inject_envio_dte_xsi_schema_declaration(data: bytes) -> bytes:
	"""Declara ``xsi:schemaLocation`` en la raiz ``EnvioDTE`` **antes** de firmar el sobre."""
	i = 0
	if data.startswith(b"<?xml"):
		p = data.find(b"?>")
		if p == -1:
			return data
		i = p + 2
	payload = data[i:].lstrip()
	if not payload.startswith(_ENVIO_DTE_OPEN_MIN):
		if payload.startswith(b"<EnvioDTE") and b"xsi:schemaLocation=" in payload[:400]:
			return data
		return data
	replaced = _ENVIO_DTE_OPEN_SCHEMA + payload[len(_ENVIO_DTE_OPEN_MIN) :]
	return data[:i] + replaced


def inject_consumo_folios_xsi_schema_declaration(data: bytes) -> bytes:
	"""Añade ``xmlns:xsi`` y ``xsi:schemaLocation`` en la raiz ``ConsumoFolios``.

	Misma idea que ``inject_envio_boleta_xsi_schema_declaration``: aplicar **antes**
	de parsear y firmar para que el digest de ``#RCOF_*`` incluya los namespace
	nodes del ancestro si el validador portal lo exige.
	"""
	i = 0
	if data.startswith(b"<?xml"):
		p = data.find(b"?>")
		if p == -1:
			return data
		i = p + 2
	payload = data[i:].lstrip()
	if not payload.startswith(_CONSUMO_OPEN_MIN):
		if payload.startswith(b"<ConsumoFolios") and b"xsi:schemaLocation=" in payload[:400]:
			return data
		return data
	replaced = _CONSUMO_OPEN_SCHEMA + payload[len(_CONSUMO_OPEN_MIN) :]
	return data[:i] + replaced


def inject_libro_cv_xsi_schema_declaration(data: bytes) -> bytes:
	"""Añade ``xmlns:xsi`` y ``xsi:schemaLocation`` en la raiz ``LibroCompraVenta``."""
	i = 0
	if data.startswith(b"<?xml"):
		p = data.find(b"?>")
		if p == -1:
			return data
		i = p + 2
	payload = data[i:].lstrip()
	if not payload.startswith(_LIBRO_CV_OPEN_MIN):
		if payload.startswith(b"<LibroCompraVenta") and b"xsi:schemaLocation=" in payload[:450]:
			return data
		return data
	replaced = _LIBRO_CV_OPEN_SCHEMA + payload[len(_LIBRO_CV_OPEN_MIN) :]
	return data[:i] + replaced
