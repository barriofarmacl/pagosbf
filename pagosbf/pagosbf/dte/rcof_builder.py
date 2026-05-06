"""RCOF: Consumo de Folios (`ConsumoFolios` / `DocumentoConsumoFolios`).

Construye XML conforme a ``ConsumoFolio_v10.xsd`` (sin firma). La firma XMLDSig
va en ``sign_consumo_folios`` (`xml_signer`).

Referencias:
- http://www.sii.cl/servicios_online/docs/xml/ConsumoFolio_v10.xsd
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from lxml import etree

from .constants import (
	IVA_RATE,
	NS_SII_DTE,
	SII_XML_ENCODING,
	TIPO_DTE_BOLETA_AFECTA,
	TIPO_DTE_BOLETA_EXENTA,
	xsd_file,
)

if TYPE_CHECKING:
	pass


class RcofBuildError(Exception):
	"""Error al construir o validar datos del Consumo de Folios."""


def _nsmap_sii() -> dict[str | None, str]:
	return {None: NS_SII_DTE}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
	element = etree.SubElement(parent, f"{{{NS_SII_DTE}}}{tag}")
	if text is not None:
		element.text = text
	return element


def _serialize(element: etree._Element) -> bytes:
	return etree.tostring(
		element,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
	)


def _split_contiguous_ranges(sorted_folios: list[int]) -> list[tuple[int, int]]:
	if not sorted_folios:
		return []
	out: list[tuple[int, int]] = []
	start = prev = sorted_folios[0]
	for f in sorted_folios[1:]:
		if f == prev + 1:
			prev = f
			continue
		out.append((start, prev))
		start = prev = f
	out.append((start, prev))
	return out


@dataclass(frozen=True)
class CaratulaRcof:
	"""Datos de carátula del DocumentoConsumoFolios."""

	rut_emisor: str
	rut_envia: str
	fch_resol: str  # YYYY-MM-DD
	nro_resol: int
	fch_inicio: str  # YYYY-MM-DD
	fch_final: str  # YYYY-MM-DD
	sec_envio: int
	tmst_firma_env: datetime
	correlativo: int | None = None


@dataclass(frozen=True)
class ResumenRcof:
	"""Un bloque ``Resumen`` por tipo DTE (39, 41 o 61 según XSD)."""

	tipo_documento: int
	mnt_total: int
	folios_emitidos: int
	folios_anulados: int
	folios_utilizados: int
	mnt_neto: int | None = None
	mnt_iva: int | None = None
	tasa_iva: float | None = None
	mnt_exento: int | None = None
	rangos_utilizados: tuple[tuple[int, int], ...] = ()
	rangos_anulados: tuple[tuple[int, int], ...] = ()


def build_consumo_folios_draft_bytes(
	caratula: CaratulaRcof,
	resumenes: list[ResumenRcof],
	*,
	documento_id: str = "RCOF_01",
) -> bytes:
	"""Arma ``ConsumoFolios`` con ``DocumentoConsumoFolios`` (sin ``ds:Signature``).

	La firma se aplica después con ``sign_consumo_folios``.
	"""
	if not resumenes:
		raise RcofBuildError("Se requiere al menos un Resumen.")

	root = etree.Element(
		f"{{{NS_SII_DTE}}}ConsumoFolios",
		nsmap=_nsmap_sii(),
		version="1.0",
	)

	doc_cf = etree.SubElement(root, f"{{{NS_SII_DTE}}}DocumentoConsumoFolios", ID=documento_id)

	car_el = etree.SubElement(doc_cf, f"{{{NS_SII_DTE}}}Caratula", version="1.0")
	_el(car_el, "RutEmisor", caratula.rut_emisor)
	_el(car_el, "RutEnvia", caratula.rut_envia)
	_el(car_el, "FchResol", caratula.fch_resol)
	_el(car_el, "NroResol", str(int(caratula.nro_resol)))
	_el(car_el, "FchInicio", caratula.fch_inicio)
	_el(car_el, "FchFinal", caratula.fch_final)
	if caratula.correlativo is not None:
		_el(car_el, "Correlativo", str(int(caratula.correlativo)))
	_el(car_el, "SecEnvio", str(int(caratula.sec_envio)))
	_el(car_el, "TmstFirmaEnv", caratula.tmst_firma_env.strftime("%Y-%m-%dT%H:%M:%S"))

	for res in resumenes:
		rs = etree.SubElement(doc_cf, f"{{{NS_SII_DTE}}}Resumen")
		_el(rs, "TipoDocumento", str(int(res.tipo_documento)))
		if res.mnt_neto is not None:
			_el(rs, "MntNeto", str(int(res.mnt_neto)))
		if res.mnt_iva is not None:
			_el(rs, "MntIva", str(int(res.mnt_iva)))
		if res.tasa_iva is not None:
			# XSD PctType: usar forma entera si es 19.0
			tv = res.tasa_iva
			_el(rs, "TasaIVA", str(int(tv)) if tv == int(tv) else str(tv))
		if res.mnt_exento is not None:
			_el(rs, "MntExento", str(int(res.mnt_exento)))
		_el(rs, "MntTotal", str(int(res.mnt_total)))
		_el(rs, "FoliosEmitidos", str(int(res.folios_emitidos)))
		_el(rs, "FoliosAnulados", str(int(res.folios_anulados)))
		_el(rs, "FoliosUtilizados", str(int(res.folios_utilizados)))
		for a, b in res.rangos_utilizados:
			ru = etree.SubElement(rs, f"{{{NS_SII_DTE}}}RangoUtilizados")
			_el(ru, "Inicial", str(int(a)))
			_el(ru, "Final", str(int(b)))
		for ra in res.rangos_anulados:
			a, b = ra[0], ra[1] if len(ra) > 1 else ra[0]
			ran = etree.SubElement(rs, f"{{{NS_SII_DTE}}}RangoAnulados")
			_el(ran, "Inicial", str(int(a)))
			if b != a:
				_el(ran, "Final", str(int(b)))

	return _serialize(root)


def aggregate_resumenes_from_envio_boleta_xml(xml_bytes: bytes) -> list[ResumenRcof]:
	"""Recorre ``EnvioBOLETA`` / ``<DTE>`` y agrega totales por ``TipoDTE``.

	Soporta boletas 39 (afecta) y 41 (exenta) mezcladas. Rangos de folios por
	tipo se calculan como intervalos contiguos separados.
	"""
	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	try:
		tree = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise RcofBuildError(f"XML envio mal formado: {exc}") from exc

	# Acumuladores por tipo DTE
	stats: dict[int, dict[str, object]] = {}

	S = f"{{{NS_SII_DTE}}}"
	for documento in tree.iter(f"{S}Documento"):
		parent = documento.getparent()
		if parent is None or not (
			isinstance(parent.tag, str) and etree.QName(parent.tag).localname == "DTE"
		):
			continue

		enc = documento.find(f"{S}Encabezado")
		if enc is None:
			continue
		id_doc_el = enc.find(f"{S}IdDoc")
		if id_doc_el is None:
			continue
		tipo_el = id_doc_el.find(f"{S}TipoDTE")
		folio_el = id_doc_el.find(f"{S}Folio")
		if tipo_el is None or tipo_el.text is None or folio_el is None or folio_el.text is None:
			continue
		tipo_dte = int(tipo_el.text.strip())
		folio = int(folio_el.text.strip())

		totales = enc.find(f"{S}Totales")
		if totales is None:
			continue

		mnt_neto = mnt_iva = mnt_exe = mnt_total = None
		for t in totales:
			if not isinstance(t.tag, str):
				continue
			tn = etree.QName(t.tag).localname
			if tn == "MntNeto" and t.text:
				mnt_neto = int(float(t.text.strip()))
			elif tn in ("IVA", "MntIva") and t.text:
				mnt_iva = int(float(t.text.strip()))
			elif tn in ("MntExe", "MntExento") and t.text:
				mnt_exe = int(float(t.text.strip()))
			elif tn == "MntTotal" and t.text:
				mnt_total = int(float(t.text.strip()))
		if mnt_total is None:
			continue

		if tipo_dte not in stats:
			stats[tipo_dte] = {
				"neto": 0,
				"iva": 0,
				"exe": 0,
				"total": 0,
				"folios": [],
			}
		st = stats[tipo_dte]
		st["folios"].append(folio)
		st["total"] = int(st["total"]) + mnt_total
		if tipo_dte == TIPO_DTE_BOLETA_AFECTA:
			st["neto"] = int(st["neto"]) + (mnt_neto or 0)
			st["iva"] = int(st["iva"]) + (mnt_iva or 0)
			if mnt_exe:
				st["exe"] = int(st["exe"]) + mnt_exe
		elif tipo_dte == TIPO_DTE_BOLETA_EXENTA:
			st["exe"] = int(st["exe"]) + (mnt_exe or mnt_total)

	out: list[ResumenRcof] = []
	for tipo in sorted(stats.keys()):
		st = stats[tipo]
		folios_sorted = sorted(set(st["folios"]))
		ranges = tuple(_split_contiguous_ranges(folios_sorted))
		n_docs = len(folios_sorted)
		n_anul = 0
		n_util = n_docs + n_anul

		if tipo == TIPO_DTE_BOLETA_AFECTA:
			neto = int(st["neto"])
			iva = int(st["iva"])
			exe_line = int(st.get("exe") or 0)
			out.append(
				ResumenRcof(
					tipo_documento=tipo,
					mnt_neto=neto if neto else None,
					mnt_iva=iva if iva else None,
					tasa_iva=IVA_RATE if neto else None,
					mnt_exento=exe_line if exe_line else None,
					mnt_total=int(st["total"]),
					folios_emitidos=n_docs,
					folios_anulados=n_anul,
					folios_utilizados=n_util,
					rangos_utilizados=ranges,
				)
			)
		elif tipo == TIPO_DTE_BOLETA_EXENTA:
			exe = int(st["exe"])
			out.append(
				ResumenRcof(
					tipo_documento=tipo,
					mnt_exento=exe if exe else None,
					mnt_total=int(st["total"]),
					folios_emitidos=n_docs,
					folios_anulados=n_anul,
					folios_utilizados=n_util,
					rangos_utilizados=ranges,
				)
			)
		else:
			out.append(
				ResumenRcof(
					tipo_documento=tipo,
					mnt_total=int(st["total"]),
					folios_emitidos=n_docs,
					folios_anulados=n_anul,
					folios_utilizados=n_util,
					rangos_utilizados=ranges,
				)
			)

	return out


_rcof_schema: etree.XMLSchema | None = None


def validate_rcof_xml_signed(xml_bytes: bytes) -> None:
	"""Valida ``ConsumoFolios`` firmado contra ``ConsumoFolio_v10.xsd`` (deps locales).

	Usar **después** de firmar: el XSD exige ``ds:Signature``.
	"""
	global _rcof_schema
	if _rcof_schema is None:
		path = xsd_file("ConsumoFolio_v10.xsd", version="consumo_folio")
		if not path.is_file():
			raise RcofBuildError(f"XSD ausente: {path}")
		try:
			_rcof_schema = etree.XMLSchema(etree.parse(str(path)))
		except etree.XMLSchemaParseError as exc:
			raise RcofBuildError(f"No se pudo compilar XSD RCOF: {exc}") from exc
	parser = etree.XMLParser(resolve_entities=False, no_network=True)
	try:
		tree = etree.fromstring(xml_bytes, parser=parser)
	except etree.XMLSyntaxError as exc:
		raise RcofBuildError(f"XML mal formado: {exc}") from exc
	if not _rcof_schema.validate(tree):
		errors = "; ".join(str(e) for e in _rcof_schema.error_log)
		raise RcofBuildError(f"ConsumoFolios no valida XSD: {errors}")


__all__ = [
	"CaratulaRcof",
	"RcofBuildError",
	"ResumenRcof",
	"aggregate_resumenes_from_envio_boleta_xml",
	"build_consumo_folios_draft_bytes",
	"validate_rcof_xml_signed",
]
