"""Borradores ``DocumentoDraft`` (DTE sin TED) para el set **4811534** casos 1--8.

Cumple primera linea de ``Referencia``: ``TpoDocRef=SET``, ``RazonRef=CASO 4811534-x``.
Las referencias a facturas/NC usan ``TpoDocRef`` numerico del DTE (33, 61) segun corresponda.

Caller: timbrar con CAF del **mismo tipo** que el DTE (33, 61, 56) y firmar con PFX.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lxml import etree

from .cert_set_basico_4811534 import (
	CASO_4811534_1_LINEAS,
	CASO_4811534_2_LINEAS,
	CASO_4811534_6_DEVOLUCION,
	ReceptorFacturaSet4811534,
	lineas_caso_4811534_2,
	lineas_caso_4811534_3,
	lineas_caso_4811534_4,
	receptor_para_caso_referenciado,
	referencia_set_caso_razon,
	totales_caso_4811534_1,
	totales_caso_4811534_2,
	totales_caso_4811534_3,
	totales_caso_4811534_4,
	lineas_caso_4811534_6_nc,
	totales_caso_4811534_6_nc_devolucion,
	totales_caso_4811534_7_nc_anula,
)
from .constants import (
	MAX_IT1_LENGTH,
	MAX_RSR_LENGTH,
	NS_SII_DTE,
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from .xml_builder import DDData, DocumentoDraft


def _nsmap_sii() -> dict[str | None, str]:
	return {None: NS_SII_DTE}


def _el(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
	element = etree.SubElement(parent, f"{{{NS_SII_DTE}}}{tag}")
	if text is not None:
		element.text = text
	return element


def _truncate(value: str, max_length: int) -> str:
	return (value or "").strip()[:max_length]


def _serialize_id_tipo(tipo: int, folio: int) -> str:
	if tipo == TIPO_DTE_FACTURA_ELECTRONICA:
		return f"FAC33-{folio}"
	if tipo == TIPO_DTE_NOTA_CREDITO_ELECTRONICA:
		return f"NCE61-{folio}"
	if tipo == TIPO_DTE_NOTA_DEBITO_ELECTRONICA:
		return f"NDE56-{folio}"
	return f"DTE{tipo}-{folio}"


def _append_referencia(
	documento: etree._Element,
	nro_lin: int,
	tpo_doc_ref: str,
	folio_ref: str,
	fch_ref: date,
	*,
	razon_ref: str | None = None,
	cod_ref: int | None = None,
) -> None:
	rf = _el(documento, "Referencia")
	_el(rf, "NroLinRef", str(nro_lin))
	_el(rf, "TpoDocRef", _truncate(tpo_doc_ref, 3))
	_el(rf, "FolioRef", folio_ref[:18])
	_el(rf, "FchRef", fch_ref.isoformat())
	if cod_ref is not None:
		_el(rf, "CodRef", str(int(cod_ref)))
	if razon_ref:
		_el(rf, "RazonRef", _truncate(razon_ref, 90))


def _put_set_ref(documento: etree._Element, caso_id: str, fch: date) -> None:
	_append_referencia(
		documento,
		1,
		"SET",
		"0",
		fch,
		razon_ref=referencia_set_caso_razon(caso_id),
	)


@dataclass(frozen=True, slots=True)
class SetBasico4811534Emision:
	"""Folios y emisor compartidos para los 8 documentos del set (orden instructivo)."""

	emisor_rut: str
	emisor_rzn: str
	emisor_giro: str
	emisor_acteco: str
	fecha_emision: date
	folio_factura_caso_1: int
	folio_factura_caso_2: int
	folio_factura_caso_3: int
	folio_factura_caso_4: int
	folio_nc_caso_5: int
	folio_nc_caso_6: int
	folio_nc_caso_7: int
	folio_nd_caso_8: int
	# Overrides opcionales (spike / pruebas locales sin tocar RECEPTOR_FACTURA_POR_CASO)
	receptor_caso_1_rut: str | None = None
	receptor_caso_1_razon: str | None = None
	nombres_item_caso_1: tuple[str, str] | None = None


def _receptor_factura_caso_1(ctx: SetBasico4811534Emision) -> ReceptorFacturaSet4811534:
	if ctx.receptor_caso_1_rut:
		return ReceptorFacturaSet4811534(
			ctx.receptor_caso_1_rut.strip(),
			(ctx.receptor_caso_1_razon or "").strip(),
		)
	return receptor_para_caso_referenciado("4811534-1")


def build_set_basico_4811534_draft(
	caso_id: str,
	ctx: SetBasico4811534Emision,
) -> DocumentoDraft:
	"""Construye el borrador DTE para ``caso_id`` en ``4811534-1`` .. ``4811534-8``."""
	if caso_id == "4811534-1":
		return _draft_factura_1(ctx)
	if caso_id == "4811534-2":
		return _draft_factura_2(ctx)
	if caso_id == "4811534-3":
		return _draft_factura_3(ctx)
	if caso_id == "4811534-4":
		return _draft_factura_4(ctx)
	if caso_id == "4811534-5":
		return _draft_nc_5(ctx)
	if caso_id == "4811534-6":
		return _draft_nc_6(ctx)
	if caso_id == "4811534-7":
		return _draft_nc_7(ctx)
	if caso_id == "4811534-8":
		return _draft_nd_8(ctx)
	raise ValueError(f"Caso no soportado: {caso_id}")


def _emisor_receptor(
	encabezado: etree._Element,
	ctx: SetBasico4811534Emision,
	recep_rut: str,
	recep_rzn: str,
) -> None:
	emisor = _el(encabezado, "Emisor")
	_el(emisor, "RUTEmisor", ctx.emisor_rut)
	_el(emisor, "RznSoc", _truncate(ctx.emisor_rzn, 100))
	_el(emisor, "GiroEmis", _truncate(ctx.emisor_giro, 80))
	_el(emisor, "Acteco", (ctx.emisor_acteco or "").strip())
	receptor = _el(encabezado, "Receptor")
	_el(receptor, "RUTRecep", recep_rut)
	_el(receptor, "RznSocRecep", _truncate(recep_rzn, 100))


def _tot33_afectas_only(encabezado: etree._Element, mnt_neto: int, iva: int, total: int) -> None:
	tot = _el(encabezado, "Totales")
	_el(tot, "MntNeto", str(int(mnt_neto)))
	_el(tot, "TasaIVA", "19.00")
	_el(tot, "IVA", str(int(iva)))
	_el(tot, "MntTotal", str(int(total)))


def _tot33_con_exe(
	encabezado: etree._Element, mnt_neto: int, mnt_exe: int, iva: int, total: int
) -> None:
	tot = _el(encabezado, "Totales")
	if mnt_neto:
		_el(tot, "MntNeto", str(int(mnt_neto)))
	if mnt_exe:
		_el(tot, "MntExe", str(int(mnt_exe)))
	_el(tot, "TasaIVA", "19.00")
	_el(tot, "IVA", str(int(iva)))
	_el(tot, "MntTotal", str(int(total)))


def _dd(
	ctx: SetBasico4811534Emision,
	tipo: int,
	folio: int,
	recep_rut: str,
	recep_rzn: str,
	mnt_total: int,
	it1: str,
) -> DDData:
	return DDData(
		rut_emisor=ctx.emisor_rut,
		tipo_dte=tipo,
		folio=int(folio),
		fecha_emision=ctx.fecha_emision.isoformat(),
		rut_receptor=recep_rut,
		razon_social_receptor=_truncate(recep_rzn, MAX_RSR_LENGTH),
		monto_total=int(mnt_total),
		descripcion_item_1=_truncate(it1, MAX_IT1_LENGTH),
	)


def _draft_factura_1(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_factura_caso_1
	rec = _receptor_factura_caso_1(ctx)
	mnt_neto, iva, mnt_total = totales_caso_4811534_1()
	documento_id = _serialize_id_tipo(TIPO_DTE_FACTURA_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_FACTURA_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_afectas_only(eh, mnt_neto, iva, mnt_total)

	nombres_linea = ctx.nombres_item_caso_1 or (
		CASO_4811534_1_LINEAS[0][0],
		CASO_4811534_1_LINEAS[1][0],
	)
	for nro, ((_, qty, prc), nmb) in enumerate(
		zip(CASO_4811534_1_LINEAS, nombres_linea, strict=True), start=1
	):
		monto = int(qty * prc)
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(nro))
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "MontoItem", str(monto))

	_put_set_ref(documento, "4811534-1", ctx.fecha_emision)
	dd = _dd(ctx, TIPO_DTE_FACTURA_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, nombres_linea[0])
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_factura_2(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_factura_caso_2
	rec = receptor_para_caso_referenciado("4811534-2")
	mnt_neto, iva, mnt_total = totales_caso_4811534_2()
	documento_id = _serialize_id_tipo(TIPO_DTE_FACTURA_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_FACTURA_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_afectas_only(eh, mnt_neto, iva, mnt_total)

	names = tuple(x[0] for x in CASO_4811534_2_LINEAS)
	for nro, (row, nmb) in enumerate(
		zip(lineas_caso_4811534_2(), names, strict=True), start=1
	):
		qty, prc, bruto, pct, neto = row[0], row[1], row[2], row[3], row[4]
		dscto = bruto - neto
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(nro))
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "DescuentoPct", f"{pct:.2f}")
		_el(det, "DescuentoMonto", str(int(dscto)))
		_el(det, "MontoItem", str(int(neto)))

	_put_set_ref(documento, "4811534-2", ctx.fecha_emision)
	dd = _dd(ctx, TIPO_DTE_FACTURA_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, names[0])
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_factura_3(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_factura_caso_3
	rec = receptor_para_caso_referenciado("4811534-3")
	mnt_neto, mnt_exe, iva, mnt_total = totales_caso_4811534_3()
	documento_id = _serialize_id_tipo(TIPO_DTE_FACTURA_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_FACTURA_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_con_exe(eh, mnt_neto, mnt_exe, iva, mnt_total)

	for idx, (nmb, qty, prc, exe, monto) in enumerate(lineas_caso_4811534_3(), start=1):
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(idx))
		if exe:
			_el(det, "IndExe", "1")
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "MontoItem", str(int(monto)))

	_put_set_ref(documento, "4811534-3", ctx.fecha_emision)
	first_nmb = lineas_caso_4811534_3()[0][0]
	dd = _dd(ctx, TIPO_DTE_FACTURA_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, first_nmb)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_factura_4(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_factura_caso_4
	rec = receptor_para_caso_referenciado("4811534-4")
	rows, _ds_glob_decl = lineas_caso_4811534_4()
	mnt_neto, mnt_exe, iva, mnt_total = totales_caso_4811534_4()
	documento_id = _serialize_id_tipo(TIPO_DTE_FACTURA_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_FACTURA_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_con_exe(eh, mnt_neto, mnt_exe, iva, mnt_total)

	for idx, (nmb, qty, prc, exe, monto) in enumerate(rows, start=1):
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(idx))
		if exe:
			_el(det, "IndExe", "1")
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "MontoItem", str(int(monto)))

	dr = _el(documento, "DscRcgGlobal")
	_el(dr, "NroLinDR", "1")
	_el(dr, "TpoMov", "D")
	_el(dr, "GlosaDR", _truncate("Descuento global items afectos", 45))
	_el(dr, "TpoValor", "%")
	_el(dr, "ValorDR", "16.00")

	_put_set_ref(documento, "4811534-4", ctx.fecha_emision)
	first_nmb = rows[0][0]
	dd = _dd(ctx, TIPO_DTE_FACTURA_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, first_nmb)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_nc_5(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_nc_caso_5
	rec = _receptor_factura_caso_1(ctx)
	documento_id = _serialize_id_tipo(TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_NOTA_CREDITO_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	tot = _el(eh, "Totales")
	_el(tot, "MntNeto", "0")
	_el(tot, "TasaIVA", "19.00")
	_el(tot, "IVA", "0")
	_el(tot, "MntTotal", "0")

	det = _el(documento, "Detalle")
	_el(det, "NroLinDet", "1")
	_el(det, "NmbItem", _truncate("CORRIGE GIRO DEL RECEPTOR", 80))
	_el(det, "QtyItem", "1.00")
	_el(det, "MontoItem", "0")

	_put_set_ref(documento, "4811534-5", ctx.fecha_emision)
	_append_referencia(
		documento,
		2,
		str(TIPO_DTE_FACTURA_ELECTRONICA),
		str(ctx.folio_factura_caso_1),
		ctx.fecha_emision,
		cod_ref=2,
		razon_ref="CORRIGE GIRO DEL RECEPTOR",
	)

	it1 = "CORRIGE GIRO DEL RECEPTOR"
	dd = _dd(ctx, TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio, rec.rut, rec.razon_social, 0, it1)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_nc_6(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_nc_caso_6
	rec = receptor_para_caso_referenciado("4811534-2")
	mnt_neto, iva, mnt_total = totales_caso_4811534_6_nc_devolucion()
	documento_id = _serialize_id_tipo(TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_NOTA_CREDITO_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_afectas_only(eh, mnt_neto, iva, mnt_total)

	for idx, (nmb, qty, prc, pct, _bruto, dscto, neto) in enumerate(
		lineas_caso_4811534_6_nc(), start=1
	):
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(idx))
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "DescuentoPct", f"{pct:.2f}")
		_el(det, "DescuentoMonto", str(int(dscto)))
		_el(det, "MontoItem", str(int(neto)))

	_put_set_ref(documento, "4811534-6", ctx.fecha_emision)
	_append_referencia(
		documento,
		2,
		str(TIPO_DTE_FACTURA_ELECTRONICA),
		str(ctx.folio_factura_caso_2),
		ctx.fecha_emision,
		razon_ref="DEVOLUCION DE MERCADERIAS",
	)

	nmb0 = CASO_4811534_6_DEVOLUCION[0][0]
	dd = _dd(ctx, TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, nmb0)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_nc_7(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_nc_caso_7
	rec = receptor_para_caso_referenciado("4811534-3")
	mnt_neto, mnt_exe, iva, mnt_total = totales_caso_4811534_7_nc_anula()
	documento_id = _serialize_id_tipo(TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_NOTA_CREDITO_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	_tot33_con_exe(eh, mnt_neto, mnt_exe, iva, mnt_total)

	for idx, (nmb, qty, prc, exe, monto) in enumerate(lineas_caso_4811534_3(), start=1):
		det = _el(documento, "Detalle")
		_el(det, "NroLinDet", str(idx))
		if exe:
			_el(det, "IndExe", "1")
		_el(det, "NmbItem", _truncate(nmb, 80))
		_el(det, "QtyItem", f"{qty:.2f}")
		_el(det, "PrcItem", f"{prc:.2f}")
		_el(det, "MontoItem", str(int(monto)))

	_put_set_ref(documento, "4811534-7", ctx.fecha_emision)
	_append_referencia(
		documento,
		2,
		str(TIPO_DTE_FACTURA_ELECTRONICA),
		str(ctx.folio_factura_caso_3),
		ctx.fecha_emision,
		razon_ref="ANULA FACTURA",
	)

	first_nmb = lineas_caso_4811534_3()[0][0]
	dd = _dd(ctx, TIPO_DTE_NOTA_CREDITO_ELECTRONICA, folio, rec.rut, rec.razon_social, mnt_total, first_nmb)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)


def _draft_nd_8(ctx: SetBasico4811534Emision) -> DocumentoDraft:
	folio = ctx.folio_nd_caso_8
	rec = _receptor_factura_caso_1(ctx)
	documento_id = _serialize_id_tipo(TIPO_DTE_NOTA_DEBITO_ELECTRONICA, folio)
	root = etree.Element(f"{{{NS_SII_DTE}}}DTE", nsmap=_nsmap_sii(), version="1.0")
	documento = etree.SubElement(root, f"{{{NS_SII_DTE}}}Documento", ID=documento_id)
	eh = _el(documento, "Encabezado")
	id_doc = _el(eh, "IdDoc")
	_el(id_doc, "TipoDTE", str(TIPO_DTE_NOTA_DEBITO_ELECTRONICA))
	_el(id_doc, "Folio", str(folio))
	_el(id_doc, "FchEmis", ctx.fecha_emision.isoformat())
	_emisor_receptor(eh, ctx, rec.rut, rec.razon_social)
	tot = _el(eh, "Totales")
	_el(tot, "MntNeto", "0")
	_el(tot, "TasaIVA", "19.00")
	_el(tot, "IVA", "0")
	_el(tot, "MntTotal", "0")

	det = _el(documento, "Detalle")
	_el(det, "NroLinDet", "1")
	_el(det, "NmbItem", _truncate("ANULA NOTA DE CREDITO ELECTRONICA", 80))
	_el(det, "QtyItem", "1.00")
	_el(det, "MontoItem", "0")

	_put_set_ref(documento, "4811534-8", ctx.fecha_emision)
	_append_referencia(
		documento,
		2,
		str(TIPO_DTE_NOTA_CREDITO_ELECTRONICA),
		str(ctx.folio_nc_caso_5),
		ctx.fecha_emision,
		razon_ref="ANULA NOTA DE CREDITO ELECTRONICA",
	)

	it1 = "ANULA NOTA DE CREDITO ELECTRONICA"
	dd = _dd(ctx, TIPO_DTE_NOTA_DEBITO_ELECTRONICA, folio, rec.rut, rec.razon_social, 0, it1)
	return DocumentoDraft(dte_element=root, documento_element=documento, dd_data=dd, documento_id=documento_id)
