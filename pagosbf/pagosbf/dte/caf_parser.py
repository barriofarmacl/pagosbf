"""Parser del XML de autorizacion de folios (CAF) entregado por el SII.

Formato tipico: raiz `AUTORIZACION` con hijos:
- `CAF` (DA con RUT, TD, rango, RSAPK, IDK, FRMA firmado por SII)
- `RSASK` (clave privada RSA en PEM, para el timbre electronico)
- `RSAPUBK` (clave publica PEM, redundante con RSAPK)

No valida la firma `FRMA` del SII (el servidor ya valido al emitir; opcional: verificar offline).

Uso: subir el archivo al DocType `CAF` o leerlo desde ruta, llamar
`parse_autorizacion_bytes`, pasar el `CAFData` a `ted_generator` y
persistir metadatos en Frappe.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from lxml import etree

from .constants import VALID_TIPOS_DTE
from .types import CAFData


class CAFParserError(Exception):
	"""Error al parsear o validar un archivo AUTORIZACION / CAF."""


def parse_autorizacion_bytes(xml_bytes: bytes) -> CAFData:
	"""Parsea un archivo XML `AUTORIZACION` (descarga SII) y retorna `CAFData`.

	Args:
	    xml_bytes: Contenido del XML (UTF-8 o Latin-1; se parsea con `lxml`).

	Raises:
	    CAFParserError: estructura invalida, TD no soportado, fechas/enteros
	        ilegibles, o PEM faltante.
	"""
	if not xml_bytes or not xml_bytes.strip():
		raise CAFParserError("XML vacio.")

	parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
	try:
		root = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise CAFParserError(f"XML mal formado: {exc}") from exc
	if root is None or etree.QName(root.tag).localname != "AUTORIZACION":
		raise CAFParserError("Se espera raiz <AUTORIZACION>.")

	caf = _child_local(root, "CAF")
	if caf is None:
		raise CAFParserError("Falta elemento <CAF>.")

	rsask_el = _child_local(root, "RSASK")
	if rsask_el is None or not (rsask_el.text and rsask_el.text.strip()):
		raise CAFParserError("Falta <RSASK> o clave privada vacia (no se puede firmar el TED).")

	pem = _normalize_pem_block(rsask_el.text)
	try:
		rsa_private_key_pem = pem.encode("ascii")
	except UnicodeEncodeError as exc:
		raise CAFParserError("RSASK contiene caracteres no ASCII; PEM invalido.") from exc

	# CAF compacto para embeber en <DD>: el XML de autorizacion suele traer saltos de linea
	# entre etiquetas; como nodos de texto influyen en C14N del DD (firma FRMT del TED y el
	# digest XMLDSig del <Documento>), se eliminan textos solo-blanco en el parse intermedio.
	caf_compact_xml = etree.tostring(caf, encoding="utf-8", xml_declaration=False, pretty_print=False)
	caf_norm = etree.fromstring(
		caf_compact_xml,
		parser=etree.XMLParser(
			remove_blank_text=True,
			resolve_entities=False,
			no_network=True,
			recover=False,
		),
	)
	caf_xml_element_str = etree.tostring(
		caf_norm,
		encoding="unicode",
		xml_declaration=False,
		pretty_print=False,
	)

	da = _child_local(caf_norm, "DA")
	if da is None:
		raise CAFParserError("Falta <DA> dentro de <CAF>.")

	re = _text_child(da, "RE")
	rs = _text_child(da, "RS")
	td_s = _text_child(da, "TD")
	fa_s = _text_child(da, "FA")
	idk = _text_child(da, "IDK") or "100"
	rng = _child_local(da, "RNG")
	if rng is None:
		raise CAFParserError("Falta <RNG> en <DA>.")
	desde_s = _text_child(rng, "D")
	hasta_s = _text_child(rng, "H")
	rsapk = _child_local(da, "RSAPK")
	if rsapk is None:
		raise CAFParserError("Falta <RSAPK> en <DA>.")

	m_b64 = _text_child(rsapk, "M")
	e_b64 = _text_child(rsapk, "E")
	if m_b64 is None or e_b64 is None:
		raise CAFParserError("Falta <M> o <E> en <RSAPK>.")

	try:
		tipo_dte = int(td_s or "")
		rango_desde = int(desde_s or "")
		rango_hasta = int(hasta_s or "")
	except ValueError as exc:
		raise CAFParserError(f"TD o rango no numerico: {exc}") from exc

	if tipo_dte not in VALID_TIPOS_DTE:
		raise CAFParserError(
			f"TD={tipo_dte} no soportado (solo boletas {sorted(VALID_TIPOS_DTE)})."
		)
	if rango_desde < 0 or rango_hasta < rango_desde:
		raise CAFParserError("Rango de folios invalido (D, H).")

	try:
		fecha_autorizacion = _parse_fecha_sii(fa_s or "")
	except ValueError as exc:
		raise CAFParserError(f"FechaFA invalida: {fa_s!r}") from exc

	return CAFData(
		tipo_dte=tipo_dte,
		rango_desde=rango_desde,
		rango_hasta=rango_hasta,
		rut_emisor=re or "",
		razon_social_emisor=rs or "",
		fecha_autorizacion=fecha_autorizacion,
		caf_xml_element_str=caf_xml_element_str,
		rsa_private_key_pem=rsa_private_key_pem,
		rsa_public_key_modulus_b64=m_b64,
		rsa_public_key_exponent_b64=e_b64,
		idk=idk,
	)


def parse_autorizacion_path(path: str | Path) -> CAFData:
	"""Carga y parsea un archivo de autorizacion desde disco."""
	p = Path(path)
	if not p.is_file():
		raise CAFParserError(f"No existe el archivo: {p}")
	return parse_autorizacion_bytes(p.read_bytes())


def _child_local(parent: etree._Element, local_name: str) -> etree._Element | None:
	for child in list(parent):
		if isinstance(child.tag, str) and etree.QName(child.tag).localname == local_name:
			return child
	return None


def _text_child(parent: etree._Element, local_name: str) -> str | None:
	child = _child_local(parent, local_name)
	if child is None or child.text is None:
		return None
	return child.text.strip()


def _parse_fecha_sii(fa: str) -> date:
	# Formato SII: YYYY-MM-DD
	return date.fromisoformat(fa.strip())


def _normalize_pem_block(text: str) -> str:
	"""Asegura PEM con saltos de linea Unix; conserva delimitadores."""
	t = text.strip()
	if "BEGIN" not in t or "END" not in t:
		raise CAFParserError("RSASK no parece un PEM (BEGIN/END faltante).")
	# Colapsa espacios internos a una sola linea entre headers y cuerpo base64
	lines: list[str] = []
	for line in t.splitlines():
		ln = line.strip()
		if not ln:
			continue
		lines.append(ln)
	return "\n".join(lines) + "\n"


__all__ = ["CAFParserError", "parse_autorizacion_bytes", "parse_autorizacion_path"]
