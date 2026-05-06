"""xml_builder: construye el XML `<DTE>` para Boleta Electronica tipo 39/41.

Responsabilidades (spec pagosbf-sii-boleta R4):
- Serializar los datos de dominio (dataclasses `types.py`) en un arbol `lxml`
  que cumple `DTE_v10.xsd`.
- Exponer un contrato en dos pasos que permite insertar el TED ya firmado
  (calculado en `ted_generator` con la clave del CAF) antes de la firma
  XMLDSig final del documento.
- Validar contra XSD; cualquier violacion genera `DTEBuildError` y el caller
  (DocType `DTE Boleta`) marca `estado_envio = RECHAZADO_LOCAL`.

No depende de Frappe ni de red. Testeable puro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from lxml import etree

from .constants import (
	NS_SII_DTE,
	SII_XML_ENCODING,
	TIPO_DTE_BOLETA_AFECTA,
	TIPO_DTE_BOLETA_EXENTA,
	xsd_path,
)
from .types import DTEBoletaData

if TYPE_CHECKING:
	pass


class DTEBuildError(Exception):
	"""Error en construccion/validacion del XML DTE previa al envio SII."""


@dataclass(frozen=True)
class DDData:
	"""Payload del bloque `DD` del TED.

	Construido a partir del DTE y consumido por `ted_generator`. Esta estructura
	es EXACTAMENTE lo que el SII espera firmar con la clave del CAF.
	"""

	rut_emisor: str
	tipo_dte: int
	folio: int
	fecha_emision: str  # YYYY-MM-DD
	rut_receptor: str
	razon_social_receptor: str  # truncado a 40 chars
	monto_total: int
	descripcion_item_1: str  # truncado a 40 chars


@dataclass(frozen=True)
class DocumentoDraft:
	"""Resultado intermedio: `<DTE>` sin TED ni firma, junto con el DD para TED."""

	dte_element: etree._Element  # <DTE> tree (copia mutable)
	documento_element: etree._Element  # referencia a <Documento> dentro
	dd_data: DDData
	documento_id: str  # ID unico para firma XMLDSig


def _nsmap_sii() -> dict[str | None, str]:
	return {None: NS_SII_DTE}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
	"""Helper: crea elemento en el namespace SII y lo adjunta al padre."""
	element = etree.SubElement(parent, f"{{{NS_SII_DTE}}}{tag}")
	if text is not None:
		element.text = text
	return element


def _truncate(value: str, max_length: int) -> str:
	"""Trunca respetando codificacion SII (ISO-8859-1 safe)."""
	return (value or "").strip()[:max_length]


def build_dte(data: DTEBoletaData) -> DocumentoDraft:
	"""Construye `<DTE>` sin TED ni firma a partir de los datos de dominio.

	Raises:
	    DTEBuildError: si la data no pasa `DTEBoletaData.validate()` o si la
	        estructura resultante no es coherente.
	"""
	try:
		data.validate()
	except ValueError as exc:
		raise DTEBuildError(f"Datos de DTE invalidos: {exc}") from exc

	documento_id = f"BOL{data.tipo_dte}-{data.folio}"

	dte_root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(dte_root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)

	_build_encabezado(documento, data)
	_build_detalles(documento, data)
	_build_referencias(documento, data)
	# Placeholder <TED/> y <TmstFirma/> se insertan en `insert_ted()`.

	dd_data = DDData(
		rut_emisor=data.emisor.rut,
		tipo_dte=data.tipo_dte,
		folio=data.folio,
		fecha_emision=data.fecha_emision.isoformat(),
		rut_receptor=data.receptor.rut,
		razon_social_receptor=_truncate(data.receptor.razon_social, 40),
		monto_total=data.totales.monto_total,
		descripcion_item_1=_truncate(data.detalles[0].nombre_item, 40),
	)

	return DocumentoDraft(
		dte_element=dte_root,
		documento_element=documento,
		dd_data=dd_data,
		documento_id=documento_id,
	)


def _build_encabezado(documento: etree._Element, data: DTEBoletaData) -> None:
	encabezado = _el(documento, "Encabezado")

	id_doc = _el(encabezado, "IdDoc")
	_el(id_doc, "TipoDTE", str(data.tipo_dte))
	_el(id_doc, "Folio", str(data.folio))
	_el(id_doc, "FchEmis", data.fecha_emision.isoformat())
	_el(id_doc, "IndServicio", str(data.ind_servicio))

	emisor = _el(encabezado, "Emisor")
	_el(emisor, "RUTEmisor", data.emisor.rut)
	_el(emisor, "RznSocEmisor", _truncate(data.emisor.razon_social, 100))
	_el(emisor, "GiroEmisor", _truncate(data.emisor.giro, 80))
	if data.emisor.cdg_sii_sucur is not None:
		_el(emisor, "CdgSIISucur", str(int(data.emisor.cdg_sii_sucur)))
	_el(emisor, "DirOrigen", _truncate(data.emisor.direccion_origen, 70))
	_el(emisor, "CmnaOrigen", _truncate(data.emisor.comuna_origen, 20))
	co = (data.emisor.ciudad_origen or "").strip()
	if co:
		_el(emisor, "CiudadOrigen", _truncate(co, 20))

	receptor = _el(encabezado, "Receptor")
	_el(receptor, "RUTRecep", data.receptor.rut)
	_el(receptor, "RznSocRecep", _truncate(data.receptor.razon_social or "Sin nombre", 100))

	# Boleta Totales sequence (XSD BOLETADefType): MntNeto?, MntExe?, IVA?, MntTotal.
	# Nota: TasaIVA NO va en Totales de boleta (aplica solo a factura).
	totales = _el(encabezado, "Totales")
	if data.tipo_dte == TIPO_DTE_BOLETA_AFECTA:
		_el(totales, "MntNeto", str(data.totales.monto_neto))
		if data.totales.monto_exento:
			_el(totales, "MntExe", str(data.totales.monto_exento))
		_el(totales, "IVA", str(data.totales.iva))
	elif data.tipo_dte == TIPO_DTE_BOLETA_EXENTA:
		_el(totales, "MntExe", str(data.totales.monto_exento or data.totales.monto_total))
	_el(totales, "MntTotal", str(data.totales.monto_total))


def _build_detalles(documento: etree._Element, data: DTEBoletaData) -> None:
	for detalle in data.detalles:
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(detalle.nro_lin_det))
		# XSD EnvioBOLETA_v11: IndExe debe ir antes de NmbItem dentro de Detalle.
		if detalle.indica_exento and data.tipo_dte == TIPO_DTE_BOLETA_AFECTA:
			_el(det, "IndExe", "1")
		_el(det, "NmbItem", _truncate(detalle.nombre_item, 80))
		_el(det, "QtyItem", f"{detalle.cantidad:.2f}")
		if detalle.unidad_medida:
			_el(det, "UnmdItem", _truncate(detalle.unidad_medida, 4))
		_el(det, "PrcItem", f"{detalle.precio_item:.2f}")
		_el(det, "MontoItem", str(int(detalle.monto_item)))


def _build_referencias(documento: etree._Element, data: DTEBoletaData) -> None:
	"""Bloque Referencia del XSD EnvioBOLETA (CodRef string, RazonRef) antes del TED."""
	for ref in data.referencias:
		rf = _el(documento, "Referencia")
		_el(rf, "NroLinRef", str(ref.nro_lin_ref))
		if ref.cod_ref:
			_el(rf, "CodRef", _truncate(ref.cod_ref, 18))
		if ref.razon_ref:
			_el(rf, "RazonRef", _truncate(ref.razon_ref, 90))


def insert_ted(draft: DocumentoDraft, ted_element: etree._Element, tmst_firma: datetime) -> bytes:
	"""Inserta el TED firmado y el `TmstFirma`; retorna bytes DTE sin firma XMLDSig.

	El XML retornado ya esta en encoding SII (ISO-8859-1) y es la entrada de
	`xml_signer.sign_dte()`.
	"""
	documento = draft.documento_element

	existing_ted = documento.find(f"{{{NS_SII_DTE}}}TED")
	if existing_ted is not None:
		documento.remove(existing_ted)

	documento.append(ted_element)
	_el(documento, "TmstFirma", tmst_firma.strftime("%Y-%m-%dT%H:%M:%S"))

	return _serialize(draft.dte_element)


def _serialize(element: etree._Element) -> bytes:
	"""Serializa a bytes con declaracion XML y encoding SII.

	SII requiere `<?xml version="1.0" encoding="ISO-8859-1"?>`. `lxml.tostring`
	con `xml_declaration=True` genera la cabecera correcta y codifica el arbol
	en latin-1. Caracteres fuera de ISO-8859-1 provocaran `UnicodeEncodeError`.
	"""
	return etree.tostring(
		element,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
		pretty_print=False,
	)


_schema_cache: dict[str, etree.XMLSchema] = {}

_XS_NS = "http://www.w3.org/2001/XMLSchema"


def _build_boleta_schema_tree(version: str = "boleta") -> etree._ElementTree:
	"""Construye en memoria un XSD composite valido para `<DTE>` de boleta.

	Razon: la definicion `BOLETADefType` vive en `EnvioBOLETA_v11.xsd`, que:
	- Usa types `SiiDte:*` (PctType, RUTType, etc.) definidos en `SiiTypes_v10.xsd`
	  sin importarlo (asume composicion externa).
	- Tiene dos `minInclusive=0.00` restringiendo `PctType` cuya base es 0.01
	  (bug conocido que `lxml.etree.XMLSchema` rechaza con `XMLSchemaParseError`).

	Este helper:
	1. Parsea `EnvioBOLETA_v11.xsd` y lo patchea (0.00 -> 0.01) en DescuentoPct.
	2. Incluye `SiiTypes_v10.xsd` via `xs:include` en el mismo namespace.
	3. Declara un root extra `<xs:element name="DTE" type="SiiDte:BOLETADefType"/>`
	   para validar un DTE standalone sin envolverlo en `<EnvioBOLETA>`.

	No escribe al disco: devuelve un `ElementTree` listo para `etree.XMLSchema()`.
	"""
	base_dir = xsd_path(version=version)
	envio_path = base_dir / "EnvioBOLETA_v11.xsd"
	sii_types_path = base_dir / "SiiTypes_v10.xsd"
	if not envio_path.exists() or not sii_types_path.exists():
		raise DTEBuildError(f"XSD requeridos ausentes en {base_dir}")

	schema_tree = etree.parse(str(envio_path))
	root = schema_tree.getroot()

	# Patch PctType facets 0.00 -> 0.01 (quirk SII documentado en README.md).
	for facet in schema_tree.iter(f"{{{_XS_NS}}}minInclusive"):
		if facet.get("value") == "0.00":
			parent_restriction = facet.getparent()
			if parent_restriction is not None and parent_restriction.get("base") == "SiiDte:PctType":
				facet.set("value", "0.01")

	# Merge SiiTypes_v10.xsd SIN incluir definiciones duplicadas. EnvioBOLETA
	# redefine algunos tipos localmente (ej. DTEType); conservamos los locales
	# y copiamos solo los que faltan.
	sii_types_root = etree.parse(str(sii_types_path)).getroot()
	existing_names: set[tuple[str, str]] = set()
	for child in root:
		if not isinstance(child.tag, str):  # comments / PI
			continue
		tag = etree.QName(child.tag).localname
		name = child.get("name")
		if tag in {"simpleType", "complexType", "element", "attribute", "group", "attributeGroup"} and name:
			existing_names.add((tag, name))

	# XMLSchema requiere: (include | import | redefine | annotation)* antes de
	# definiciones de tipos/elementos. Insertamos despues del ultimo import/include.
	header_tags = {"include", "import", "redefine"}
	insert_idx = 0
	for idx, child in enumerate(root):
		if not isinstance(child.tag, str):
			continue
		localname = etree.QName(child.tag).localname
		if localname in header_tags:
			insert_idx = idx + 1

	for type_def in sii_types_root:
		if not isinstance(type_def.tag, str):
			continue
		tag = etree.QName(type_def.tag).localname
		name = type_def.get("name")
		if tag not in {"simpleType", "complexType", "element", "attribute", "group", "attributeGroup"}:
			continue
		if name and (tag, name) in existing_names:
			continue
		root.insert(insert_idx, type_def)
		insert_idx += 1
		if name:
			existing_names.add((tag, name))

	# Hacer `ds:Signature` dentro de `DTE` opcional para habilitar validacion
	# pre-firma (estructural). El SII valida la firma aparte al recibir.
	for sig_element in schema_tree.iter(f"{{{_XS_NS}}}element"):
		if sig_element.get("ref") == "ds:Signature":
			sig_element.set("minOccurs", "0")

	# Declarar <DTE> como root con BOLETADefType para validar standalone.
	dte_root = etree.SubElement(root, f"{{{_XS_NS}}}element")
	dte_root.set("name", "DTE")
	dte_root.set("type", "SiiDte:BOLETADefType")

	return schema_tree


def _load_schema_boleta(version: str = "boleta") -> etree.XMLSchema:
	cache_key = f"{version}/boleta_composite"
	if cache_key not in _schema_cache:
		tree = _build_boleta_schema_tree(version=version)
		try:
			_schema_cache[cache_key] = etree.XMLSchema(tree)
		except etree.XMLSchemaParseError as exc:
			raise DTEBuildError(f"No se pudo compilar XSD composite boleta: {exc}") from exc
	return _schema_cache[cache_key]


def validate_dte_xml(xml_bytes: bytes, version: str = "boleta") -> None:
	"""Valida `<DTE>` boleta (tipo 39/41) contra XSD composite en memoria.

	Debe llamarse **antes** de firmar (output de `insert_ted`). Llamarlo
	despues de firmar lanza falsos positivos porque el `xmldsignature_v10.xsd`
	del SII es mas restrictivo que lo que el propio servidor acepta (ver
	`public/xsd/boleta/README.md` quirk #3). La validacion de la firma se
	delega al SII mediante `RECIBOS`/`EstadoDTE`.

	Raises:
	    DTEBuildError: si el XML no valida. El mensaje incluye todos los errores
	        del schema (util para debugging del set de certificacion).
	"""
	schema = _load_schema_boleta(version=version)
	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	try:
		tree = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise DTEBuildError(f"XML mal formado: {exc}") from exc

	if not schema.validate(tree):
		errors = "; ".join(str(e) for e in schema.error_log)
		raise DTEBuildError(f"DTE no valida contra XSD boleta: {errors}")
