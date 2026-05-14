"""Builder IECV: ``LibroCompraVenta`` (LibroCV_v10) sin firma XMLDSig."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from lxml import etree

from .constants import NS_SII_DTE, SII_XML_ENCODING


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


@dataclass(frozen=True)
class CaratulaLibroCV:
	"""Datos de caratula para ``EnvioLibro``."""

	rut_emisor_libro: str
	rut_envia: str
	periodo_tributario: str  # YYYY-MM
	fch_resol: str  # YYYY-MM-DD
	nro_resol: int
	tipo_operacion: str = "VENTA"  # COMPRA | VENTA
	tipo_libro: str = "MENSUAL"  # MENSUAL | ESPECIAL | RECTIFICA
	tipo_envio: str = "TOTAL"  # PARCIAL | FINAL | TOTAL | AJUSTE
	nro_segmento: int | None = None
	folio_notificacion: int | None = None
	cod_aut_rec: str | None = None


@dataclass(frozen=True)
class TotalesPeriodoLibroCV:
	"""Resumen por tipo de documento para ``ResumenPeriodo/TotalesPeriodo``."""

	tpo_doc: int
	tot_doc: int
	tot_mnt_exe: int = 0
	tot_mnt_neto: int = 0
	tot_mnt_iva: int = 0
	tot_iva_fuera_plazo: int | None = None
	tot_mnt_total: int = 0


def build_libro_cv_draft_bytes(
	caratula: CaratulaLibroCV,
	totales_periodo: list[TotalesPeriodoLibroCV],
	*,
	tmst_firma: datetime,
	envio_libro_id: str = "LIBROVENTA",
) -> bytes:
	"""Construye ``LibroCompraVenta`` (sin ``ds:Signature``)."""
	if not totales_periodo:
		raise ValueError("Se requiere al menos un TotalesPeriodo para LibroCompraVenta.")

	root = etree.Element(f"{{{NS_SII_DTE}}}LibroCompraVenta", nsmap=_nsmap_sii(), version="1.0")
	envio = _el(root, "EnvioLibro")
	envio.set("ID", envio_libro_id)

	car = _el(envio, "Caratula")
	_el(car, "RutEmisorLibro", caratula.rut_emisor_libro)
	_el(car, "RutEnvia", caratula.rut_envia)
	_el(car, "PeriodoTributario", caratula.periodo_tributario)
	_el(car, "FchResol", caratula.fch_resol)
	_el(car, "NroResol", str(int(caratula.nro_resol)))
	_el(car, "TipoOperacion", caratula.tipo_operacion)
	_el(car, "TipoLibro", caratula.tipo_libro)
	_el(car, "TipoEnvio", caratula.tipo_envio)
	if caratula.nro_segmento is not None:
		_el(car, "NroSegmento", str(int(caratula.nro_segmento)))
	if caratula.folio_notificacion is not None:
		_el(car, "FolioNotificacion", str(int(caratula.folio_notificacion)))
	if caratula.cod_aut_rec:
		_el(car, "CodAutRec", caratula.cod_aut_rec.strip()[:10])

	rp = _el(envio, "ResumenPeriodo")
	for row in totales_periodo:
		tp = _el(rp, "TotalesPeriodo")
		_el(tp, "TpoDoc", str(int(row.tpo_doc)))
		_el(tp, "TotDoc", str(int(row.tot_doc)))
		_el(tp, "TotMntExe", str(int(row.tot_mnt_exe)))
		_el(tp, "TotMntNeto", str(int(row.tot_mnt_neto)))
		_el(tp, "TotMntIVA", str(int(row.tot_mnt_iva)))
		if row.tot_iva_fuera_plazo is not None:
			_el(tp, "TotIVAFueraPlazo", str(int(row.tot_iva_fuera_plazo)))
		_el(tp, "TotMntTotal", str(int(row.tot_mnt_total)))

	_el(envio, "TmstFirma", tmst_firma.strftime("%Y-%m-%dT%H:%M:%S"))
	return _serialize(root)


__all__ = [
	"CaratulaLibroCV",
	"TotalesPeriodoLibroCV",
	"build_libro_cv_draft_bytes",
]
