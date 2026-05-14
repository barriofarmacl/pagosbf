"""Construccion y validacion XSD de DTE Factura electronica (tipo 33).

Spike OpenSpec 2.2+: compositor + ``lxml`` contra ``public/xsd/factura/DTE_v10.xsd``.

- Validacion **pre-TED** (estructura documento): relaja ``TED``, ``TmstFirma`` y
  ``ds:Signature`` en memoria (paridad con boleta).
- Validacion **post-TED**: XSD con TED obligatorio; solo ``ds:Signature`` opcional
  hasta firmar el DTE con PFX.

``EnvioDTE`` (sobre): ver ``envio_builder.build_envio_dte_draft`` y
``xml_signer.sign_envio_dte``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from lxml import etree

from . import envio_builder, ted_generator
from .cert_set_basico_4811534 import CASO_4811534_1_LINEAS
from .constants import (
	MAX_IT1_LENGTH,
	MAX_RSR_LENGTH,
	NS_SII_DTE,
	SII_XML_ENCODING,
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
	xsd_path,
)
from .set_basico_4811534_dte import SetBasico4811534Emision, build_set_basico_4811534_draft
from .types import CAFData
from .signature_audit import audit_boleta_xml_bytes
from .xml_builder import DDData, DTEBuildError, DocumentoDraft, insert_ted
from .xml_signer import SigningMaterial, sign_dte, sign_envio_dte
from pagosbf.pagosbf.facturacion.types import Factura33Data

_XS_NS = "http://www.w3.org/2001/XMLSchema"

_schema_cache: dict[str, etree.XMLSchema] = {}


def _nsmap_sii() -> dict[str | None, str]:
	return {None: NS_SII_DTE}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
	element = etree.SubElement(parent, f"{{{NS_SII_DTE}}}{tag}")
	if text is not None:
		element.text = text
	return element


def _truncate(value: str, max_length: int) -> str:
	return (value or "").strip()[:max_length]


def _patch_pct_type_zero(schema_tree: etree._ElementTree) -> None:
	"""Corrige facetas SII ``minInclusive=0.00`` sobre ``SiiDte:PctType`` (base 0.01)."""
	for facet in schema_tree.iter(f"{{{_XS_NS}}}minInclusive"):
		if facet.get("value") != "0.00":
			continue
		parent_restriction = facet.getparent()
		if parent_restriction is not None and parent_restriction.get("base") == "SiiDte:PctType":
			facet.set("value", "0.01")


def _relax_for_validation(
	schema_tree: etree._ElementTree, *, relax_ted_tmst: bool
) -> None:
	for elem in schema_tree.iter(f"{{{_XS_NS}}}element"):
		name = elem.get("name")
		if relax_ted_tmst and name in {"TED", "TmstFirma"}:
			elem.set("minOccurs", "0")
		if elem.get("ref") == "ds:Signature":
			elem.set("minOccurs", "0")


def _build_factura_dte_schema_tree(*, relax_ted_tmst: bool) -> etree._ElementTree:
	base_dir = xsd_path(version="factura")
	dte_path = base_dir / "DTE_v10.xsd"
	if not dte_path.exists():
		raise DTEBuildError(f"XSD factura requerido ausente: {dte_path}")

	schema_tree = etree.parse(str(dte_path))
	_patch_pct_type_zero(schema_tree)
	_relax_for_validation(schema_tree, relax_ted_tmst=relax_ted_tmst)
	return schema_tree


def _load_schema_factura_dte(relax_ted_tmst: bool) -> etree.XMLSchema:
	key = f"factura/dte_v10_ted_{'optional' if relax_ted_tmst else 'required'}"
	if key not in _schema_cache:
		tree = _build_factura_dte_schema_tree(relax_ted_tmst=relax_ted_tmst)
		try:
			_schema_cache[key] = etree.XMLSchema(tree)
		except etree.XMLSchemaParseError as exc:
			raise DTEBuildError(f"No se pudo compilar XSD factura (DTE): {exc}") from exc
	return _schema_cache[key]


def validate_dte_factura_xml(xml_bytes: bytes) -> None:
	"""Valida ``<DTE>`` sin TED / firma documento (estructura base + totales).

	Raises:
		DTEBuildError: si el XML no valida.
	"""
	schema = _load_schema_factura_dte(relax_ted_tmst=True)
	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	try:
		tree = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise DTEBuildError(f"XML mal formado: {exc}") from exc

	if not schema.validate(tree):
		errors = "; ".join(str(e) for e in schema.error_log)
		raise DTEBuildError(f"DTE factura no valida contra XSD: {errors}")


def validate_dte_factura_xml_document_ready(xml_bytes: bytes) -> None:
	"""Valida DTE con TED y ``TmstFirma``; aun **sin** ``ds:Signature`` del documento."""
	schema = _load_schema_factura_dte(relax_ted_tmst=False)
	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	try:
		tree = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise DTEBuildError(f"XML mal formado: {exc}") from exc

	if not schema.validate(tree):
		errors = "; ".join(str(e) for e in schema.error_log)
		raise DTEBuildError(f"DTE factura (listo para firmar documento) no valida: {errors}")


def _serialize(element: etree._Element) -> bytes:
	return etree.tostring(
		element,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
		pretty_print=False,
	)


def _fmt_decimal(value: object) -> str:
	text = f"{value}"
	if "." not in text:
		return text
	return text.rstrip("0").rstrip(".") or "0"


def _documento_id_from_tipo(tipo_dte: int, folio: int) -> str:
	if tipo_dte == TIPO_DTE_FACTURA_ELECTRONICA:
		return f"FAC33-{int(folio)}"
	if tipo_dte == TIPO_DTE_NOTA_CREDITO_ELECTRONICA:
		return f"NCE61-{int(folio)}"
	if tipo_dte == TIPO_DTE_NOTA_DEBITO_ELECTRONICA:
		return f"NDE56-{int(folio)}"
	return f"DTE{int(tipo_dte)}-{int(folio)}"


def build_factura_33_documento_draft(data: Factura33Data) -> DocumentoDraft:
	"""Arma un DTE 33/61/56 generico desde `Sales Invoice` mapeada."""
	data.validate()
	documento_id = _documento_id_from_tipo(data.tipo_dte, data.folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(int(data.tipo_dte)))
	_el(id_doc, "Folio", str(int(data.folio)))
	_el(id_doc, "FchEmis", data.fecha_emision.isoformat())

	emisor = _el(eh, "Emisor")
	_el(emisor, "RUTEmisor", data.emisor.rut)
	_el(emisor, "RznSoc", _truncate(data.emisor.razon_social, 100))
	_el(emisor, "GiroEmis", _truncate(data.emisor.giro, 80))
	if data.acteco:
		_el(emisor, "Acteco", data.acteco.strip()[:6])
	_el(emisor, "DirOrigen", _truncate(data.emisor.direccion_origen, 70))
	_el(emisor, "CmnaOrigen", _truncate(data.emisor.comuna_origen, 20))

	receptor = _el(eh, "Receptor")
	_el(receptor, "RUTRecep", data.receptor.rut)
	_el(receptor, "RznSocRecep", _truncate(data.receptor.razon_social, 100))

	tot = _el(eh, "Totales")
	if data.totales.monto_neto:
		_el(tot, "MntNeto", str(int(data.totales.monto_neto)))
	if data.totales.monto_exento:
		_el(tot, "MntExe", str(int(data.totales.monto_exento)))
	_el(tot, "TasaIVA", _fmt_decimal(data.totales.tasa_iva))
	_el(tot, "IVA", str(int(data.totales.iva)))
	_el(tot, "MntTotal", str(int(data.totales.monto_total)))

	for detalle in data.detalles:
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(int(detalle.nro_lin_det)))
		if detalle.indica_exento:
			_el(det, "IndExe", "1")
		_el(det, "NmbItem", _truncate(detalle.nombre_item, 80))
		if detalle.cantidad:
			_el(det, "QtyItem", _fmt_decimal(detalle.cantidad))
		if detalle.unidad_medida:
			_el(det, "UnmdItem", detalle.unidad_medida[:4])
		_el(det, "PrcItem", _fmt_decimal(detalle.precio_item))
		if detalle.descuento_pct is not None:
			_el(det, "DescuentoPct", _fmt_decimal(detalle.descuento_pct))
		if detalle.descuento_monto is not None:
			_el(det, "DescuentoMonto", str(int(detalle.descuento_monto)))
		_el(det, "MontoItem", str(int(detalle.monto_item)))

	for ref in data.referencias:
		rf = _el(documento, "Referencia")
		_el(rf, "NroLinRef", str(int(ref.nro_lin_ref)))
		_el(rf, "TpoDocRef", _truncate(ref.tpo_doc_ref, 3))
		_el(rf, "FolioRef", _truncate(ref.folio_ref, 18))
		_el(rf, "FchRef", ref.fecha_ref.isoformat())
		if ref.cod_ref is not None:
			_el(rf, "CodRef", str(int(ref.cod_ref)))
		if ref.razon_ref:
			_el(rf, "RazonRef", _truncate(ref.razon_ref, 90))

	first_name = data.detalles[0].nombre_item
	dd = DDData(
		rut_emisor=data.emisor.rut,
		tipo_dte=int(data.tipo_dte),
		folio=int(data.folio),
		fecha_emision=data.fecha_emision.isoformat(),
		rut_receptor=data.receptor.rut,
		razon_social_receptor=_truncate(data.receptor.razon_social, MAX_RSR_LENGTH),
		monto_total=int(data.totales.monto_total),
		descripcion_item_1=_truncate(first_name, MAX_IT1_LENGTH),
	)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


@dataclass(frozen=True, slots=True)
class SpikeFactura33Params:
	"""Parametros emision DTE 33 alineados al **CASO 4811534-1** del set **4811534**.

	Cantidades y precios de linea salen de ``cert_set_basico_4811534`` (instructivo).
	**Emisor** (RUT, razon, giro sin abreviaturas, Acteco) deben coincidir con **Mi SII**
	y con el CAF real en certificacion; los defaults sirven solo para tests locales.
	"""

	emisor_rut: str = "76000000-0"
	emisor_rzn: str = "Emisor Pruebas DTE 33"
	# Giro: instructivo exige evitar abreviaturas; sustituir por texto Mi SII en maullin.
	emisor_giro: str = "VENTA AL POR MENOR DE PRODUCTOS FARMACEUTICOS Y MEDICINALES EN COMERCIO ESPECIALIZADO"
	emisor_acteco: str = "477310"
	recep_rut: str = "77777777-7"
	recep_rzn: str = "Receptor Certificacion SII"
	fecha_emision: date | None = None
	folio: int = 1
	item1_nombre: str = CASO_4811534_1_LINEAS[0][0]
	item2_nombre: str = CASO_4811534_1_LINEAS[1][0]


def build_spike_factura_33_documento_draft(
	params: SpikeFactura33Params | None = None,
) -> DocumentoDraft:
	"""Arma ``<DTE>`` sin TED ni firma + ``DDData`` para `ted_generator` (tipo 33).

	Set **4811534**, caso **4811534-1**: cantidades, PU, montos, referencia **SET** y
	``RazonRef`` instructivo; emisor/receptor/nombres item pueden sobreescribirse vía
	``SpikeFactura33Params``.
	"""
	p = params or SpikeFactura33Params()
	fecha = p.fecha_emision or date.today()
	ctx = SetBasico4811534Emision(
		emisor_rut=p.emisor_rut,
		emisor_rzn=p.emisor_rzn,
		emisor_giro=p.emisor_giro,
		emisor_acteco=p.emisor_acteco,
		fecha_emision=fecha,
		folio_factura_caso_1=int(p.folio),
		folio_factura_caso_2=0,
		folio_factura_caso_3=0,
		folio_factura_caso_4=0,
		folio_nc_caso_5=0,
		folio_nc_caso_6=0,
		folio_nc_caso_7=0,
		folio_nd_caso_8=0,
		receptor_caso_1_rut=p.recep_rut,
		receptor_caso_1_razon=p.recep_rzn,
		nombres_item_caso_1=(p.item1_nombre, p.item2_nombre),
	)
	return build_set_basico_4811534_draft("4811534-1", ctx)


def build_spike_factura_33_set_basico_4811534_1(
	fecha_emision: date | None = None,
	folio: int = 1,
) -> bytes:
	"""Serializa ``<DTE>`` sin TED (compat spike 2.2)."""
	p = SpikeFactura33Params(fecha_emision=fecha_emision, folio=folio)
	draft = build_spike_factura_33_documento_draft(p)
	return _serialize(draft.dte_element)


def insert_ted_factura(
	draft: DocumentoDraft,
	ted_element: etree._Element,
	tmst_firma: datetime,
) -> bytes:
	"""Inserta TED + TmstFirma; mismo contrato que ``xml_builder.insert_ted``."""
	return insert_ted(draft, ted_element, tmst_firma)


def finalize_dte_signed(
	draft: DocumentoDraft,
	caf: CAFData,
	material: SigningMaterial,
	timestamp: datetime,
) -> bytes:
	"""TED + validaciones + firma XMLDSig del documento (sin sobre).

	Raises:
		DTEBuildError: XSD / firma / TED.
	"""
	validate_dte_factura_xml(_serialize(draft.dte_element))
	ted = ted_generator.build_signed_ted(draft.dd_data, caf, timestamp)
	dte_with_ted = insert_ted_factura(draft, ted, timestamp)
	validate_dte_factura_xml_document_ready(dte_with_ted)
	dte_signed = sign_dte(dte_with_ted, material, reference_uri=draft.documento_id)
	for a in audit_boleta_xml_bytes(dte_signed):
		if not a.xmldsig_verifies:
			raise DTEBuildError(f"DTE: firma documento no verifica localmente ({a.detail})")
	return dte_signed


SET_BASICO_4811534_CASOS_ORDEN: tuple[str, ...] = tuple(f"4811534-{i}" for i in range(1, 9))


def build_signed_envio_set_basico_4811534(
	caf33: CAFData,
	caf61: CAFData,
	caf56: CAFData,
	material: SigningMaterial,
	timestamp: datetime,
	ctx: SetBasico4811534Emision,
	*,
	fch_resol: date | None = None,
	nro_resol: int | None = None,
	rut_envia: str | None = None,
) -> bytes:
	"""``EnvioDTE`` firmado con los **8** DTE del set 4811534 (orden instructivo).

	Requiere tres CAF autorizados (tipos 33, 61 y 56) y folios válidos en cada rango.
	"""
	fr = fch_resol or date(2020, 1, 1)
	nr = nro_resol if nro_resol is not None else 80
	rut_sii_car = rut_envia or ctx.emisor_rut
	caf_por_tipo = {
		TIPO_DTE_FACTURA_ELECTRONICA: caf33,
		TIPO_DTE_NOTA_CREDITO_ELECTRONICA: caf61,
		TIPO_DTE_NOTA_DEBITO_ELECTRONICA: caf56,
	}
	signed_seq: list[bytes] = []
	for caso in SET_BASICO_4811534_CASOS_ORDEN:
		draft = build_set_basico_4811534_draft(caso, ctx)
		td = draft.dd_data.tipo_dte
		try:
			caf_d = caf_por_tipo[int(td)]
		except KeyError as exc:
			raise DTEBuildError(f"CAF no provisto para tipo DTE {td}") from exc
		signed_seq.append(finalize_dte_signed(draft, caf_d, material, timestamp))

	subtot = (
		(TIPO_DTE_FACTURA_ELECTRONICA, 4),
		(TIPO_DTE_NOTA_CREDITO_ELECTRONICA, 3),
		(TIPO_DTE_NOTA_DEBITO_ELECTRONICA, 1),
	)
	caratula = envio_builder.CaratulaEmision(
		rut_emisor=ctx.emisor_rut,
		rut_envia=rut_sii_car,
		rut_receptor=envio_builder.RUT_SII_CARATULA,
		fch_resol=fr,
		nro_resol=nr,
		tmst_firma_env=timestamp,
		tipo_dte=TIPO_DTE_FACTURA_ELECTRONICA,
		nro_dtes=len(signed_seq),
		subtot_dtes=subtot,
	)
	envio_draft = envio_builder.build_envio_dte_draft_multi(signed_seq, caratula)
	envio_signed = sign_envio_dte(envio_draft, material, reference_uri="SetDte1")
	for a in audit_boleta_xml_bytes(envio_signed):
		if not a.xmldsig_verifies:
			raise DTEBuildError(f"EnvioDTE set 4811534: firma sobre no verifica ({a.detail})")
	return envio_signed


def build_signed_envio_spike_factura_33(
	caf: CAFData,
	material: SigningMaterial,
	timestamp: datetime,
	*,
	params: SpikeFactura33Params | None = None,
	fch_resol: date | None = None,
	nro_resol: int | None = None,
	rut_envia: str | None = None,
) -> tuple[bytes, DocumentoDraft]:
	"""Pipeline offline: DTE + TED + firma documento + ``EnvioDTE`` firmado.

	Retorna ``(envio_dte_signed_bytes, draft)`` para auditoria / POST maullin.

	``rut_envia`` por defecto es el emisor del spike; en produccion debe ser el
	RUT del titular del certificado (PFX) usado para firmar.
	"""
	p = params or SpikeFactura33Params()
	fr = fch_resol or date(2020, 1, 1)
	nr = nro_resol if nro_resol is not None else 80
	rut_sii = rut_envia or p.emisor_rut

	draft = build_spike_factura_33_documento_draft(p)
	dte_signed = finalize_dte_signed(draft, caf, material, timestamp)

	caratula = envio_builder.CaratulaEmision(
		rut_emisor=p.emisor_rut,
		rut_envia=rut_sii,
		rut_receptor=envio_builder.RUT_SII_CARATULA,
		fch_resol=fr,
		nro_resol=nr,
		tmst_firma_env=timestamp,
		tipo_dte=TIPO_DTE_FACTURA_ELECTRONICA,
		nro_dtes=1,
		set_dte_id="SetDte1",
	)

	envio_draft = envio_builder.build_envio_dte_draft(dte_signed, caratula)
	envio_signed = sign_envio_dte(envio_draft, material, reference_uri="SetDte1")

	for a in audit_boleta_xml_bytes(envio_signed):
		if not a.xmldsig_verifies:
			raise DTEBuildError(f"DTE dentro de EnvioDTE: firma no verifica ({a.detail})")

	return envio_signed, draft
