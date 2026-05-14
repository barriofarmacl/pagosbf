# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spike 2.3 (issue #54): DTE 33 set basico — bytes de ``EnvioDTE`` y POST opcional a maullin.

Requiere CAF **tipo 33** real (AUTORIZACION XML SII) y certificado **PFX** cuyo RUT
sea el ``RutEnvia`` coherente con la caratula. No usa DocType ni Frappe salvo que
se invoque desde bench con configuracion adicional.

``bench execute`` serializa el retorno a JSON con ``ensure_ascii``: los caracteres
Latin-1 del XML (ej. ñ, ó) aparecen como ``\\u00f1``, ``\\u00f3``. Eso es solo
representacion JSON; si se copia ese texto literal a un ``.xml``, el archivo queda
**invalido**. El campo ``envio_xml_b64`` trae el sobre exacto en Base64; decodificar
a archivo antes de validar o subir al SII. Un ``bytes`` suelto aparece como lista de
enteros 0--255 (no es un error).

Ejemplo (solo armar sobre, sin red)::

	bench --site <sitio> execute \\
	  pagosbf.tests.certification.factura_set_basico_maullin.build_signed_envio_from_files_as_dict \\
	  --kwargs "{'caf_xml_path': '/ruta/AUTORIZACION33.xml', 'pfx_path': '/ruta/cert.pfx', 'pfx_password': '***', 'folio': 1}"

POST maullin (requiere red y credenciales validas)::

	bench --site <sitio> execute \\
	  pagosbf.tests.certification.factura_set_basico_maullin.emitir_set_basico_a_maullin \\
	  --kwargs "{... mismo ...}"
"""

from __future__ import annotations

import base64
import re
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

from pagosbf.pagosbf.dte.caf_parser import parse_autorizacion_path
from pagosbf.pagosbf.dte.cert_set_basico_4811534 import (
	totales_caso_4811534_1,
	totales_caso_4811534_2,
	totales_caso_4811534_3,
	totales_caso_4811534_4,
	totales_caso_4811534_6_nc_devolucion,
	totales_caso_4811534_7_nc_anula,
)
from pagosbf.pagosbf.dte.constants import (
	SII_XML_ENCODING,
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from pagosbf.pagosbf.dte.factura_xml import (
	SpikeFactura33Params,
	build_signed_envio_set_basico_4811534,
	build_signed_envio_spike_factura_33,
)
from pagosbf.pagosbf.dte.libro_cv_builder import (
	CaratulaLibroCV,
	TotalesPeriodoLibroCV,
	build_libro_cv_draft_bytes,
)
from pagosbf.pagosbf.dte.set_basico_4811534_dte import SetBasico4811534Emision
from pagosbf.pagosbf.dte.xml_signer import (
	XMLSignerError,
	load_pfx,
	sign_libro_compra_venta,
)
from pagosbf.pagosbf.libros.lce import totales_periodo_set_4811536_compras
from pagosbf.pagosbf.sii.sii_client import SIIClient

# bench execute --kwargs usa eval(): las fechas suelen llegar como str "YYYY-MM-DD", no como date.
# A veces se pega la documentacion literal: "datetime.date(2026, 5, 6)" (sin evaluar).
_FechaEmisionArg = date | datetime | str | None

_FECHA_LLAMADA_RE = re.compile(
	r"^(?:datetime\.)?date\(\s*(\d{1,4})\s*,\s*(\d{1,2})\s*,\s*(\d{1,2})\s*\)\s*$",
	re.IGNORECASE,
)


def _coerce_fecha_emision_bench(value: _FechaEmisionArg) -> date | None:
	"""Normaliza fecha de emision desde kwargs de bench (str, datetime o date)."""
	if value is None:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if isinstance(value, str):
		s = value.strip()
		if not s:
			return None
		m = _FECHA_LLAMADA_RE.match(s)
		if m:
			return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
		head = s.split("T", 1)[0].strip()
		try:
			return date.fromisoformat(head)
		except ValueError as exc:
			raise ValueError(
				f"fecha_emision no reconocida: {s!r}. Use 'YYYY-MM-DD' o datetime.date(ano, mes, dia)."
			) from exc
	raise TypeError(f"fecha_emision: tipo no soportado {type(value).__name__}")


def _bench_envio_dict(blob: bytes) -> dict:
	"""Payload comun para ``bench execute``: texto decodificado + Base64 sin perdida."""
	return {
		"encoding": SII_XML_ENCODING,
		"byte_len": len(blob),
		"envio_xml": blob.decode(SII_XML_ENCODING),
		"envio_xml_b64": base64.b64encode(blob).decode("ascii"),
	}


def _bench_libro_dict(blob: bytes) -> dict:
	"""Payload para LibroCV en ``bench execute`` (texto + Base64 sin perdida)."""
	return {
		"encoding": SII_XML_ENCODING,
		"byte_len": len(blob),
		"libro_xml": blob.decode(SII_XML_ENCODING),
		"libro_xml_b64": base64.b64encode(blob).decode("ascii"),
	}


def _totales_periodo_set_4811534() -> list[TotalesPeriodoLibroCV]:
	f1_n, f1_i, f1_t = totales_caso_4811534_1()
	f2_n, f2_i, f2_t = totales_caso_4811534_2()
	f3_n, f3_x, f3_i, f3_t = totales_caso_4811534_3()
	f4_n, f4_x, f4_i, f4_t = totales_caso_4811534_4()
	nc6_n, nc6_i, nc6_t = totales_caso_4811534_6_nc_devolucion()
	nc7_n, nc7_x, nc7_i, nc7_t = totales_caso_4811534_7_nc_anula()

	return [
		TotalesPeriodoLibroCV(
			tpo_doc=TIPO_DTE_FACTURA_ELECTRONICA,
			tot_doc=4,
			tot_mnt_exe=f3_x + f4_x,
			tot_mnt_neto=f1_n + f2_n + f3_n + f4_n,
			tot_mnt_iva=f1_i + f2_i + f3_i + f4_i,
			tot_mnt_total=f1_t + f2_t + f3_t + f4_t,
		),
		TotalesPeriodoLibroCV(
			tpo_doc=TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
			tot_doc=1,
			tot_mnt_exe=0,
			tot_mnt_neto=0,
			tot_mnt_iva=0,
			tot_mnt_total=0,
		),
		TotalesPeriodoLibroCV(
			tpo_doc=TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
			tot_doc=3,
			tot_mnt_exe=nc7_x,
			tot_mnt_neto=nc6_n + nc7_n,  # caso 5 es solo glosa (montos 0)
			tot_mnt_iva=nc6_i + nc7_i,
			tot_mnt_total=nc6_t + nc7_t,
		),
	]


def _totales_periodo_set_4811536_compras() -> list[TotalesPeriodoLibroCV]:
	"""Totales de libro de compras del instructivo 4811536 (TXT oficial)."""
	return list(totales_periodo_set_4811536_compras())


def build_signed_envio_from_files(
	caf_xml_path: str,
	pfx_path: str,
	pfx_password: str,
	folio: int,
	*,
	timestamp: datetime | None = None,
	emisor_rut_override: str | None = None,
	emisor_rzn: str | None = None,
	emisor_giro: str | None = None,
	emisor_acteco: str | None = None,
	recep_rut: str | None = None,
	recep_rzn: str | None = None,
	item1_nombre: str | None = None,
	item2_nombre: str | None = None,
	fecha_emision: _FechaEmisionArg = None,
	envia_rut_override: str | None = None,
	fch_resol: str | None = None,
	nro_resol: int | None = None,
) -> bytes:
	"""Construye ``EnvioDTE`` firmado para el caso numerico 4811534-1 (dos lineas).

	``folio`` debe pertenecer al rango del CAF. ``emisor_rut_override`` por defecto
	es el RUT del CAF. ``envia_rut_override`` debe coincidir con el titular del PFX.

	Para coincidir con el **instructivo 4811534** y **Mi SII**, pasar ``emisor_giro``,
	``emisor_acteco`` y (si aplica) ``recep_*`` y nombres de item exactos del PDF.
	Si ``emisor_rzn`` es omitido, se usa ``razon_social_emisor`` del CAF cuando venga
	no vacia.
	"""
	caf = parse_autorizacion_path(caf_xml_path)
	if caf.tipo_dte != TIPO_DTE_FACTURA_ELECTRONICA:
		raise ValueError(
			f"Se espera CAF tipo {TIPO_DTE_FACTURA_ELECTRONICA}, recibido TD={caf.tipo_dte}"
		)
	if not (caf.rango_desde <= int(folio) <= caf.rango_hasta):
		raise ValueError(
			f"Folio {folio} fuera del rango CAF [{caf.rango_desde}, {caf.rango_hasta}]"
		)

	try:
		mat = load_pfx(Path(pfx_path).read_bytes(), pfx_password)
	except (OSError, XMLSignerError) as exc:
		raise ValueError(f"No se pudo cargar PFX: {exc}") from exc

	ts = timestamp or datetime.now()
	ts = ts.replace(microsecond=0)
	r_em = (emisor_rut_override or caf.rut_emisor or "").strip()
	if not r_em:
		raise ValueError("RUT emisor vacio (CAF o override)")
	r_env = (envia_rut_override or r_em).strip()

	fr = date.fromisoformat(fch_resol) if fch_resol else None
	base = SpikeFactura33Params(emisor_rut=r_em, folio=int(folio))
	overrides: dict = {}
	if emisor_rzn is not None:
		overrides["emisor_rzn"] = emisor_rzn.strip()
	elif (caf.razon_social_emisor or "").strip():
		overrides["emisor_rzn"] = caf.razon_social_emisor.strip()
	if emisor_giro is not None:
		overrides["emisor_giro"] = emisor_giro.strip()
	if emisor_acteco is not None:
		overrides["emisor_acteco"] = emisor_acteco.strip()
	if recep_rut is not None:
		overrides["recep_rut"] = recep_rut.strip()
	if recep_rzn is not None:
		overrides["recep_rzn"] = recep_rzn.strip()
	if item1_nombre is not None:
		overrides["item1_nombre"] = item1_nombre.strip()
	if item2_nombre is not None:
		overrides["item2_nombre"] = item2_nombre.strip()
	fe_coerced = _coerce_fecha_emision_bench(fecha_emision)
	if fe_coerced is not None:
		overrides["fecha_emision"] = fe_coerced
	params = replace(base, **overrides)
	envio, _draft = build_signed_envio_spike_factura_33(
		caf,
		mat,
		ts,
		params=params,
		fch_resol=fr,
		nro_resol=nro_resol,
		rut_envia=r_env,
	)
	return envio


def build_signed_envio_from_files_as_dict(
	caf_xml_path: str,
	pfx_path: str,
	pfx_password: str,
	folio: int,
	*,
	timestamp: datetime | None = None,
	emisor_rut_override: str | None = None,
	emisor_rzn: str | None = None,
	emisor_giro: str | None = None,
	emisor_acteco: str | None = None,
	recep_rut: str | None = None,
	recep_rzn: str | None = None,
	item1_nombre: str | None = None,
	item2_nombre: str | None = None,
	fecha_emision: _FechaEmisionArg = None,
	envia_rut_override: str | None = None,
	fch_resol: str | None = None,
	nro_resol: int | None = None,
) -> dict:
	"""Igual que ``build_signed_envio_from_files`` pero retorno apto para ``bench execute``.

	Devuelve ``envio_xml`` (texto ISO-8859-1) y ``envio_xml_b64`` (sobre exacto).
	Preferir Base64 para persistir el XML: ver docstring del modulo (escape JSON ``\\uXXXX``).
	"""
	blob = build_signed_envio_from_files(
		caf_xml_path,
		pfx_path,
		pfx_password,
		folio,
		timestamp=timestamp,
		emisor_rut_override=emisor_rut_override,
		emisor_rzn=emisor_rzn,
		emisor_giro=emisor_giro,
		emisor_acteco=emisor_acteco,
		recep_rut=recep_rut,
		recep_rzn=recep_rzn,
		item1_nombre=item1_nombre,
		item2_nombre=item2_nombre,
		fecha_emision=fecha_emision,
		envia_rut_override=envia_rut_override,
		fch_resol=fch_resol,
		nro_resol=nro_resol,
	)
	return _bench_envio_dict(blob)


def _require_caf_td(path: str, tipo: int):
	caf = parse_autorizacion_path(path)
	if caf.tipo_dte != tipo:
		raise ValueError(f"{path}: se espera CAF TD={tipo}, recibido {caf.tipo_dte}")
	return caf


def _folio_en_caf(caf_label: str, folio: int, caf) -> None:
	if not (caf.rango_desde <= int(folio) <= caf.rango_hasta):
		raise ValueError(
			f"Folio {folio} ({caf_label}) fuera del rango CAF [{caf.rango_desde}, {caf.rango_hasta}]"
		)


def build_signed_set_basico_4811534_from_files(
	caf33_xml_path: str,
	caf61_xml_path: str,
	caf56_xml_path: str,
	pfx_path: str,
	pfx_password: str,
	folio_base: int = 1,
	*,
	timestamp: datetime | None = None,
	emisor_rut_override: str | None = None,
	emisor_rzn: str | None = None,
	emisor_giro: str | None = None,
	emisor_acteco: str | None = None,
	fecha_emision: _FechaEmisionArg = None,
	envia_rut_override: str | None = None,
	fch_resol: str | None = None,
	nro_resol: int | None = None,
	receptor_caso_1_rut: str | None = None,
	receptor_caso_1_razon: str | None = None,
	nombres_item_caso_1: tuple[str, str] | None = None,
) -> bytes:
	"""Construye ``EnvioDTE`` firmado con los **8** DTE del set **4811534** (orden SII).

	Requiere tres archivos **AUTORIZACION** del SII: TD 33, 61 y 56. Los folios por
	defecto son ``folio_base`` .. ``folio_base+3`` para las cuatro facturas,
	``folio_base`` .. ``folio_base+2`` para las tres notas de crédito y
	``folio_base`` para la nota de débito (mismo número en distintos tipos es válido).
	"""
	caf33 = _require_caf_td(caf33_xml_path, TIPO_DTE_FACTURA_ELECTRONICA)
	caf61 = _require_caf_td(caf61_xml_path, TIPO_DTE_NOTA_CREDITO_ELECTRONICA)
	caf56 = _require_caf_td(caf56_xml_path, TIPO_DTE_NOTA_DEBITO_ELECTRONICA)

	try:
		mat = load_pfx(Path(pfx_path).read_bytes(), pfx_password)
	except (OSError, XMLSignerError) as exc:
		raise ValueError(f"No se pudo cargar PFX: {exc}") from exc

	ts = (timestamp or datetime.now()).replace(microsecond=0)
	r_em = (emisor_rut_override or caf33.rut_emisor or "").strip()
	if not r_em:
		raise ValueError("RUT emisor vacio (CAF 33 o override)")
	r_env = (envia_rut_override or r_em).strip()
	fr = date.fromisoformat(fch_resol) if fch_resol else None
	nr = nro_resol
	fe = _coerce_fecha_emision_bench(fecha_emision) or date.today()
	fb = int(folio_base)

	_folio_en_caf("F33 caso 1", fb, caf33)
	_folio_en_caf("F33 caso 2", fb + 1, caf33)
	_folio_en_caf("F33 caso 3", fb + 2, caf33)
	_folio_en_caf("F33 caso 4", fb + 3, caf33)
	_folio_en_caf("NC caso 5", fb, caf61)
	_folio_en_caf("NC caso 6", fb + 1, caf61)
	_folio_en_caf("NC caso 7", fb + 2, caf61)
	_folio_en_caf("ND caso 8", fb, caf56)

	rzn = (emisor_rzn or caf33.razon_social_emisor or "").strip() or "Emisor certificacion"
	giro = (emisor_giro or "").strip() or (
		"VENTA AL POR MENOR DE PRODUCTOS FARMACEUTICOS Y MEDICINALES EN COMERCIO ESPECIALIZADO"
	)
	acteco = (emisor_acteco or "477310").strip()

	ctx = SetBasico4811534Emision(
		emisor_rut=r_em,
		emisor_rzn=rzn,
		emisor_giro=giro,
		emisor_acteco=acteco,
		fecha_emision=fe,
		folio_factura_caso_1=fb,
		folio_factura_caso_2=fb + 1,
		folio_factura_caso_3=fb + 2,
		folio_factura_caso_4=fb + 3,
		folio_nc_caso_5=fb,
		folio_nc_caso_6=fb + 1,
		folio_nc_caso_7=fb + 2,
		folio_nd_caso_8=fb,
		receptor_caso_1_rut=(receptor_caso_1_rut or "").strip() or None,
		receptor_caso_1_razon=(receptor_caso_1_razon or "").strip() or None,
		nombres_item_caso_1=nombres_item_caso_1,
	)

	return build_signed_envio_set_basico_4811534(
		caf33,
		caf61,
		caf56,
		mat,
		ts,
		ctx,
		fch_resol=fr,
		nro_resol=nr,
		rut_envia=r_env,
	)


def build_signed_set_basico_4811534_from_files_as_dict(
	caf33_xml_path: str,
	caf61_xml_path: str,
	caf56_xml_path: str,
	pfx_path: str,
	pfx_password: str,
	folio_base: int = 1,
	*,
	timestamp: datetime | None = None,
	emisor_rut_override: str | None = None,
	emisor_rzn: str | None = None,
	emisor_giro: str | None = None,
	emisor_acteco: str | None = None,
	fecha_emision: _FechaEmisionArg = None,
	envia_rut_override: str | None = None,
	fch_resol: str | None = None,
	nro_resol: int | None = None,
	receptor_caso_1_rut: str | None = None,
	receptor_caso_1_razon: str | None = None,
	nombres_item_caso_1: tuple[str, str] | None = None,
) -> dict:
	"""Igual que ``build_signed_set_basico_4811534_from_files`` pero salida legible en ``bench execute``."""
	blob = build_signed_set_basico_4811534_from_files(
		caf33_xml_path,
		caf61_xml_path,
		caf56_xml_path,
		pfx_path,
		pfx_password,
		folio_base,
		timestamp=timestamp,
		emisor_rut_override=emisor_rut_override,
		emisor_rzn=emisor_rzn,
		emisor_giro=emisor_giro,
		emisor_acteco=emisor_acteco,
		fecha_emision=fecha_emision,
		envia_rut_override=envia_rut_override,
		fch_resol=fch_resol,
		nro_resol=nro_resol,
		receptor_caso_1_rut=receptor_caso_1_rut,
		receptor_caso_1_razon=receptor_caso_1_razon,
		nombres_item_caso_1=nombres_item_caso_1,
	)
	return _bench_envio_dict(blob)


def build_signed_libro_ventas_4811535_from_set_4811534(
	pfx_path: str,
	pfx_password: str,
	*,
	rut_emisor_libro: str,
	rut_envia: str | None = None,
	periodo_tributario: str | None = None,
	fch_resol: str,
	nro_resol: int,
	timestamp: datetime | None = None,
	envio_libro_id: str = "LIBROVENTA",
	tipo_libro: str = "MENSUAL",
	tipo_envio: str = "TOTAL",
) -> bytes:
	"""Construye y firma el Libro de Ventas (set 4811535) con documentos del set 4811534.

	Regla del instructivo: cuando se obtuvo set básico 4811534, usar esos documentos
	para construir el Libro de Ventas 4811535.
	"""
	r_em = (rut_emisor_libro or "").strip()
	if not r_em:
		raise ValueError("rut_emisor_libro es obligatorio")
	r_env = (rut_envia or r_em).strip()
	if not r_env:
		raise ValueError("rut_envia vacio")

	try:
		mat = load_pfx(Path(pfx_path).read_bytes(), pfx_password)
	except (OSError, XMLSignerError) as exc:
		raise ValueError(f"No se pudo cargar PFX: {exc}") from exc

	ts = (timestamp or datetime.now()).replace(microsecond=0)
	periodo = (periodo_tributario or f"{ts.year:04d}-{ts.month:02d}").strip()
	car = CaratulaLibroCV(
		rut_emisor_libro=r_em,
		rut_envia=r_env,
		periodo_tributario=periodo,
		fch_resol=fch_resol,
		nro_resol=int(nro_resol),
		tipo_operacion="VENTA",
		tipo_libro=tipo_libro.strip().upper(),
		tipo_envio=tipo_envio.strip().upper(),
	)
	draft = build_libro_cv_draft_bytes(
		car,
		_totales_periodo_set_4811534(),
		tmst_firma=ts,
		envio_libro_id=envio_libro_id.strip() or "LIBROVENTA",
	)
	return sign_libro_compra_venta(draft, mat, reference_uri=envio_libro_id.strip() or "LIBROVENTA")


def build_signed_libro_ventas_4811535_from_set_4811534_as_dict(
	pfx_path: str,
	pfx_password: str,
	*,
	rut_emisor_libro: str,
	rut_envia: str | None = None,
	periodo_tributario: str | None = None,
	fch_resol: str,
	nro_resol: int,
	timestamp: datetime | None = None,
	envio_libro_id: str = "LIBROVENTA",
	tipo_libro: str = "MENSUAL",
	tipo_envio: str = "TOTAL",
) -> dict:
	"""Wrapper `bench execute` para Libro de Ventas firmado (texto ISO + Base64)."""
	blob = build_signed_libro_ventas_4811535_from_set_4811534(
		pfx_path=pfx_path,
		pfx_password=pfx_password,
		rut_emisor_libro=rut_emisor_libro,
		rut_envia=rut_envia,
		periodo_tributario=periodo_tributario,
		fch_resol=fch_resol,
		nro_resol=nro_resol,
		timestamp=timestamp,
		envio_libro_id=envio_libro_id,
		tipo_libro=tipo_libro,
		tipo_envio=tipo_envio,
	)
	return _bench_libro_dict(blob)


def build_signed_libro_compras_4811536_from_txt(
	pfx_path: str,
	pfx_password: str,
	*,
	rut_emisor_libro: str,
	rut_envia: str | None = None,
	periodo_tributario: str | None = None,
	fch_resol: str,
	nro_resol: int,
	timestamp: datetime | None = None,
	envio_libro_id: str = "LIBROCOMPRA",
	tipo_libro: str = "MENSUAL",
	tipo_envio: str = "TOTAL",
) -> bytes:
	"""Construye y firma Libro de Compras (set 4811536) desde el TXT oficial."""
	r_em = (rut_emisor_libro or "").strip()
	if not r_em:
		raise ValueError("rut_emisor_libro es obligatorio")
	r_env = (rut_envia or r_em).strip()
	if not r_env:
		raise ValueError("rut_envia vacio")

	try:
		mat = load_pfx(Path(pfx_path).read_bytes(), pfx_password)
	except (OSError, XMLSignerError) as exc:
		raise ValueError(f"No se pudo cargar PFX: {exc}") from exc

	ts = (timestamp or datetime.now()).replace(microsecond=0)
	periodo = (periodo_tributario or f"{ts.year:04d}-{ts.month:02d}").strip()
	car = CaratulaLibroCV(
		rut_emisor_libro=r_em,
		rut_envia=r_env,
		periodo_tributario=periodo,
		fch_resol=fch_resol,
		nro_resol=int(nro_resol),
		tipo_operacion="COMPRA",
		tipo_libro=tipo_libro.strip().upper(),
		tipo_envio=tipo_envio.strip().upper(),
	)
	libro_id = envio_libro_id.strip() or "LIBROCOMPRA"
	draft = build_libro_cv_draft_bytes(
		car,
		_totales_periodo_set_4811536_compras(),
		tmst_firma=ts,
		envio_libro_id=libro_id,
	)
	return sign_libro_compra_venta(draft, mat, reference_uri=libro_id)


def build_signed_libro_compras_4811536_from_txt_as_dict(
	pfx_path: str,
	pfx_password: str,
	*,
	rut_emisor_libro: str,
	rut_envia: str | None = None,
	periodo_tributario: str | None = None,
	fch_resol: str,
	nro_resol: int,
	timestamp: datetime | None = None,
	envio_libro_id: str = "LIBROCOMPRA",
	tipo_libro: str = "MENSUAL",
	tipo_envio: str = "TOTAL",
) -> dict:
	"""Wrapper `bench execute` para Libro de Compras firmado (texto ISO + Base64)."""
	blob = build_signed_libro_compras_4811536_from_txt(
		pfx_path=pfx_path,
		pfx_password=pfx_password,
		rut_emisor_libro=rut_emisor_libro,
		rut_envia=rut_envia,
		periodo_tributario=periodo_tributario,
		fch_resol=fch_resol,
		nro_resol=nro_resol,
		timestamp=timestamp,
		envio_libro_id=envio_libro_id,
		tipo_libro=tipo_libro,
		tipo_envio=tipo_envio,
	)
	return _bench_libro_dict(blob)


def emitir_set_basico_a_maullin(
	caf_xml_path: str,
	pfx_path: str,
	pfx_password: str,
	folio: int,
	*,
	rut_emisor: str | None = None,
	emisor_rzn: str | None = None,
	emisor_giro: str | None = None,
	emisor_acteco: str | None = None,
	recep_rut: str | None = None,
	recep_rzn: str | None = None,
	item1_nombre: str | None = None,
	item2_nombre: str | None = None,
	fecha_emision: _FechaEmisionArg = None,
	envia_rut_override: str | None = None,
	fch_resol: str | None = None,
	nro_resol: int | None = None,
) -> dict:
	"""Obtiene semilla/token y ejecuta DTEUpload en maullin.

	Retorno: ``track_id``, ``resumen``, ``estado_consulta`` (XML crudo de getEstUp).

	Raises:
		ValueError: datos inconsistentes o PFX ilegible.
	"""
	envio = build_signed_envio_from_files(
		caf_xml_path,
		pfx_path,
		pfx_password,
		folio,
		emisor_rut_override=rut_emisor,
		emisor_rzn=emisor_rzn,
		emisor_giro=emisor_giro,
		emisor_acteco=emisor_acteco,
		recep_rut=recep_rut,
		recep_rzn=recep_rzn,
		item1_nombre=item1_nombre,
		item2_nombre=item2_nombre,
		fecha_emision=fecha_emision,
		envia_rut_override=envia_rut_override,
		fch_resol=fch_resol,
		nro_resol=nro_resol,
	)
	caf = parse_autorizacion_path(caf_xml_path)
	mat = load_pfx(Path(pfx_path).read_bytes(), pfx_password)
	r_em = (rut_emisor or caf.rut_emisor or "").strip()

	client = SIIClient()
	_semilla, token, _raw_seed, _raw_tok = client.get_semilla_y_token(mat)
	up = client.enviar_sobre(envio, token, r_em)
	raw_est = client.consultar_estado(up.track_id, token, r_em)
	return {
		"track_id": up.track_id,
		"upload_resumen": up.resumen,
		"estado_xml": raw_est,
	}
