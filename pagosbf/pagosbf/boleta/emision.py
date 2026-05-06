"""Orquesta build TED + firma DTE/sobre + `SIIClient` (una sola ruta de emision)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe.utils.data import getdate

from pagosbf.pagosbf.boleta.caf_file import load_caf_data
from pagosbf.pagosbf.boleta.cert_utils import get_signing_material_or_throw
from pagosbf.pagosbf.boleta.invoice_to_boleta import pos_invoice_to_dte_data, sales_invoice_to_dte_data
from pagosbf.pagosbf.dte.caf_parser import CAFData
from pagosbf.pagosbf.dte import constants
from pagosbf.pagosbf.dte.envio_builder import RUT_SII_CARATULA, CaratulaEmision, build_envio_boleta_draft
from pagosbf.pagosbf.dte.folio_allocator import (
	CAFNotFoundError,
	FolioExhaustedError,
	allocate_next_folio,
)
from pagosbf.pagosbf.dte.ted_generator import build_signed_ted
from pagosbf.pagosbf.dte import xml_builder, xml_signer
from pagosbf.pagosbf.dte.types import BoletaReferencia, DTEBoletaData, Emisor
from pagosbf.pagosbf.sii.rut import rut_para_dte_xml
from pagosbf.pagosbf.sii.sii_frappe import append_dte_respuesta_sii, sii_client_from_sii_configuration
from pagosbf.pagosbf.sii.sii_response_xml import parse_respuesta_sii

try:
	_CL_TZ = ZoneInfo("America/Santiago")
except Exception:  # noqa: BLE001
	_CL_TZ = timezone.utc


def emisor_from_sii_configuration() -> Emisor:
	"""Rellena `Emisor` desde el Single SII (resolucion, RUT, razon, etc.)."""
	c = frappe.get_single("SII Configuration")
	fd = c.resolucion_fecha
	rut_raw = (c.rut_emisor or "").strip()
	try:
		rut_fmt = rut_para_dte_xml(rut_raw) if rut_raw else ""
	except ValueError as e:
		frappe.throw(
			f"SII Configuration.rut_emisor invalido ({c.rut_emisor!r}). Use formato chileno "
			f"(ej. 76957985-0). Detalle: {e!s}",
		)
	return Emisor(
		rut=rut_fmt,
		razon_social=(c.razon_social or "-").strip(),
		giro=(c.giro or "-").strip(),
		direccion_origen=(c.direccion_origen or "-").strip(),
		comuna_origen=(c.comuna_origen or "Santiago").strip(),
		resolucion_numero=int(c.resolucion_numero or 0),
		resolucion_fecha=getdate(fd) if fd else date(2020, 1, 1),
	)


def validate_resolucion_para_caratula_envio_boleta() -> None:
	"""Comprueba datos minimos antes de armar ``Caratula`` del sobre.

	Exige **fecha de resolucion** cargada en SII Configuration. El **numero** puede ser
	``0`` en instructivos de certificacion; en produccion suele ser el N° oficial (> 0).
	Si numero/fecha no coinciden con lo registrado en el SII para el contribuyente, el
	portal rechaza con **CRT-3-19**.
	"""
	c = frappe.get_single("SII Configuration")
	n = int(c.resolucion_numero or 0)
	if n < 0:
		frappe.throw("SII Configuration / Resolucion: Numero Resolucion no puede ser negativo.")
	if not c.resolucion_fecha:
		frappe.throw(
			"SII Configuration / Resolucion: ingrese la Fecha de Resolucion (requerida en caratula). "
			"Sin fecha puede producirse CRT-3-19."
		)


def resolve_caf_por_tipo_dte(tipo: int) -> str:
	"""Primer `CAF` no agotado con `tipo_dte` coincidente (mas reciente)."""
	rows = frappe.get_all(
		"CAF",
		filters={"tipo_dte": str(tipo), "agotado": 0},
		pluck="name",
		order_by="modified desc",
		limit=1,
	)  # agotado Check: 0 = no
	if not rows:
		frappe.throw(f"No hay CAF no agotado para TipoDTE {tipo} (ver DocType CAF).")
	return rows[0]


def _bytes_xml_log(b: bytes) -> str:
	return b.decode("iso-8859-1", errors="replace")


def _xsd_version() -> str:
	return (frappe.get_single("SII Configuration").get("version_schema") or "boleta") or "boleta"


def ejecutar_emision_sii(
	sales_invoice_name: str | None = None,
	*,
	caf_name: str | None = None,
	pos_invoice_name: str | None = None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
) -> str:
	"""Crea/actualiza `DTE Boleta`, envia a SII. Retorna `name` de `DTE Boleta`.

	Indique exactamente uno de: ``sales_invoice_name`` o ``pos_invoice_name``.
	El primer argumento posicional sigue siendo el name de Sales Invoice (compatibilidad).
	"""
	if sales_invoice_name and pos_invoice_name:
		frappe.throw("Indique solo sales_invoice o pos_invoice, no ambos.")
	if pos_invoice_name:
		return _ejecutar_emision_core(
			"POS Invoice",
			pos_invoice_name,
			caf_name=caf_name,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
		)
	if sales_invoice_name:
		return _ejecutar_emision_core(
			"Sales Invoice",
			sales_invoice_name,
			caf_name=caf_name,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
		)
	frappe.throw("Falta sales_invoice_name o pos_invoice_name.")


def _with_sii_cert_refs(
	data: DTEBoletaData,
	*,
	cod_ref: str | None,
	razon_ref: str | None,
) -> DTEBoletaData:
	"""Una referencia de certificacion (CodRef/RazonRef) antes del TED."""
	if not cod_ref and not razon_ref:
		return data
	ref = BoletaReferencia(nro_lin_ref=1, cod_ref=cod_ref, razon_ref=razon_ref)
	ref.validate()
	return replace(data, referencias=(ref,))


def _ejecutar_emision_core(
	source_doctype: str,
	source_name: str,
	*,
	caf_name: str | None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
) -> str:
	"""Crea/actualiza `DTE Boleta`, envia a SII. ``source_doctype`` en Sales Invoice | POS Invoice."""
	if source_doctype not in ("Sales Invoice", "POS Invoice"):
		frappe.throw(f"Origen no soportado: {source_doctype!r}")

	flt = (
		{"pos_invoice": source_name}
		if source_doctype == "POS Invoice"
		else {"sales_invoice": source_name}
	)
	exist = frappe.db.get_value("DTE Boleta", flt, "name")
	doc_cod: str | None = None
	doc_raz: str | None = None
	if exist:
		bex = frappe.get_doc("DTE Boleta", exist)
		if bex.estado_envio in ("ENVIADO",) and bex.track_id:
			return bex.name
		doc_cod = (bex.sii_cod_ref or "").strip() or None
		doc_raz = (bex.sii_razon_ref or "").strip() or None
		if bex.estado_envio == "RECHAZADO_LOCAL":
			frappe.delete_doc(
				"DTE Boleta", bex.name, force=1, ignore_permissions=True, flags={"ignore_links": 1}
			)
			exist = None

	final_cod, final_raz = doc_cod, doc_raz
	if sii_cod_ref is not None:
		final_cod = (sii_cod_ref or "").strip() or None
	if sii_razon_ref is not None:
		final_raz = (sii_razon_ref or "").strip() or None

	doc = frappe.get_doc(source_doctype, source_name)
	if doc.docstatus != 1:
		frappe.throw(f"{source_doctype} debe estar enviado (docstatus=1) para DTE SII.")
	single = frappe.get_single("SII Configuration")
	cert = (single.get("certificado_digital") or "").strip()
	if not cert:
		frappe.throw("Configure `certificado_digital` en SII Configuration.")
	em = emisor_from_sii_configuration()
	tipo = _tipo_preliminar(doc)
	caf = caf_name or resolve_caf_por_tipo_dte(tipo)
	caf_d: CAFData = load_caf_data(caf)
	if int(caf_d.tipo_dte) != int(tipo):
		frappe.throw(
			f"CAF {caf!r} es TD={caf_d.tipo_dte}, pero el documento pide TipoDTE {tipo}."
		)
	try:
		folio = allocate_next_folio(caf)
	except CAFNotFoundError as e:
		frappe.throw(str(e))
	except FolioExhaustedError as e:
		frappe.throw(str(e))
	if source_doctype == "Sales Invoice":
		data = sales_invoice_to_dte_data(doc, folio=folio, emisor=em)
	else:
		data = pos_invoice_to_dte_data(doc, folio=folio, emisor=em)
	data = _with_sii_cert_refs(data, cod_ref=final_cod, razon_ref=final_raz)
	data.validate()
	ver = _xsd_version()
	si_link = source_name if source_doctype == "Sales Invoice" else None
	pi_link = source_name if source_doctype == "POS Invoice" else None
	bol = _crear_o_recargar_dte_boleta(
		exist,
		sales_invoice=si_link,
		pos_invoice=pi_link,
		data=data,
		caf=caf,
		em=em,
		cert=cert,
		sii_urls_ok=bool(single),
	)
	if not exist:
		bol.insert(ignore_permissions=True)
	else:
		bol.save(ignore_permissions=True, ignore_version=True)
	bol.reload()
	_log = _Logger(bol.name)
	bol.set("estado_envio", "VALIDANDO")
	bol.set("error_log", None)
	bol.save(ignore_permissions=True, ignore_version=True)
	try:
		st = get_signing_material_or_throw(cert)
		st_rut = (frappe.get_doc("Certificado Digital", cert).rut_firmante or em.rut).strip()
		st_rut = st_rut.replace(" ", "").replace(".", "")
		validate_resolucion_para_caratula_envio_boleta()

		draft = xml_builder.build_dte(data)
		ted = build_signed_ted(draft.dd_data, caf_d, data.timestamp_firma)
		dte_pre = xml_builder.insert_ted(draft, ted, data.timestamp_firma)
		xml_builder.validate_dte_xml(dte_pre, version=ver)
		dte_f = xml_signer.sign_dte(
			dte_pre, st, reference_uri=draft.documento_id
		)
		tmst_env = _now_santiago()
		carat = CaratulaEmision(
			rut_emisor=em.rut,
			rut_envia=st_rut,
			rut_receptor=RUT_SII_CARATULA,
			fch_resol=em.resolucion_fecha,
			nro_resol=int(em.resolucion_numero or 0),
			tmst_firma_env=tmst_env,
			tipo_dte=int(data.tipo_dte),
			set_dte_id="SetDte1",
		)
		borr = build_envio_boleta_draft(dte_f, carat)
		sobre = xml_signer.sign_envio_boleta(
			borr, st, reference_uri=carat.set_dte_id
		)

		client = sii_client_from_sii_configuration()
		sem, tok, raw0, raw1 = client.get_semilla_y_token(st)
		_log.append("semilla", request_xml=raw0 or None, response_xml=raw0, estado="00")
		_log.append("token", request_xml=raw0 or None, response_xml=raw1, estado="00")

		bol = frappe.get_doc("DTE Boleta", bol.name)
		bol.set("xml_dte", _bytes_xml_log(dte_pre))
		bol.set("xml_dte_firmado", _bytes_xml_log(dte_f))
		bol.set("xml_sobre_firmado", _bytes_xml_log(sobre))
		bol.save(ignore_permissions=True, ignore_version=True)

		upload = client.enviar_sobre(sobre, token=tok, rut_emisor=em.rut)
		_log.append(
			"envio",
			request_xml=_bytes_xml_log(sobre)[:20000],
			response_xml=upload.response_text[:20000] if upload.response_text else None,
			estado=str(upload.status_code),
			glosa=upload.resumen,
		)
		bol = frappe.get_doc("DTE Boleta", bol.name)
		bol.set("estado_envio", "ENVIADO")
		bol.set("track_id", str(upload.track_id))
		bol.set("fecha_envio", now_datetime())
		bol.save(ignore_permissions=True, ignore_version=True)
	except Exception as exc:  # noqa: BLE001
		err = f"{type(exc).__name__}: {exc!s}"[:20000]
		b2 = frappe.get_doc("DTE Boleta", bol.name)
		b2.set("estado_envio", "RECHAZADO_LOCAL")
		b2.set("error_log", err)
		b2.save(ignore_permissions=True, ignore_version=True)
		raise
	return bol.name


class _Logger:
	"""Agrupa lineas a `DTE Respuesta SII` (despues de existir DTE Boleta)."""

	def __init__(self, dte_name: str) -> None:
		self._n = dte_name

	def append(
		self,
		accion: str,
		request_xml: str | None,
		*,
		response_xml: str | None = None,
		estado: str | None = None,
		glosa: str | None = None,
	) -> None:
		append_dte_respuesta_sii(
			self._n,
			accion=accion,
			request_xml=request_xml,
			response_xml=response_xml,
			estado=estado,
			glosa=glosa,
		)


def _now_santiago() -> datetime:
	return datetime.now(tz=_CL_TZ).replace(tzinfo=None)


def _tipo_preliminar(doc: Any) -> int:
	from frappe.utils import flt

	iva_ = int(round(flt(doc.total_taxes_and_charges)))
	if iva_ > 0:
		return int(constants.TIPO_DTE_BOLETA_AFECTA)
	return int(constants.TIPO_DTE_BOLETA_EXENTA)


def _crear_o_recargar_dte_boleta(
	exist: str | None,
	*,
	sales_invoice: str | None,
	pos_invoice: str | None,
	data: DTEBoletaData,
	caf: str,
	em: Emisor,
	cert: str,  # noqa: ARG001
	sii_urls_ok: bool,  # noqa: ARG001
) -> Document:
	"""Crea o reutiliza la fila DTE con totales; sin XML aun (salvo reintento en exist)."""
	cod_persist, raz_persist = "", ""
	if data.referencias:
		r0 = data.referencias[0]
		cod_persist = r0.cod_ref or ""
		raz_persist = r0.razon_ref or ""
	m = {
		"doctype": "DTE Boleta",
		"sales_invoice": sales_invoice,
		"pos_invoice": pos_invoice,
		"sii_cod_ref": cod_persist,
		"sii_razon_ref": raz_persist,
		"tipo_dte": str(data.tipo_dte),
		"folio": int(data.folio),
		"caf": caf,
		"fecha_emision": data.fecha_emision,
		"monto_neto": data.totales.monto_neto,
		"monto_iva": data.totales.iva,
		"monto_exento": data.totales.monto_exento,
		"monto_total": data.totales.monto_total,
		"estado_envio": "PENDIENTE",
	}
	if exist:
		b = frappe.get_doc("DTE Boleta", exist)
		b.update(m)
		return b
	return frappe.get_doc(m)


def encolar_emision_sii(
	sales_invoice_name: str | None = None,
	*,
	pos_invoice_name: str | None = None,
	caf_name: str | None = None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
) -> str:
	"""Encola el job; retorna el nombre de `frappe.enqueue`."""
	if sales_invoice_name and pos_invoice_name:
		frappe.throw("Indique solo sales_invoice o pos_invoice para encolar, no ambos.")
	if not sales_invoice_name and not pos_invoice_name:
		frappe.throw("Falta sales_invoice_name o pos_invoice_name para encolar.")
	if pos_invoice_name:
		job_name = f"emision_sii_pos_{pos_invoice_name}"
	else:
		job_name = f"emision_sii_{sales_invoice_name}"
	return str(
		frappe.enqueue(
			"pagosbf.pagosbf.boleta.emision.ejecutar_emision_sii",
			queue="default",
			job_name=job_name,
			sales_invoice_name=sales_invoice_name,
			pos_invoice_name=pos_invoice_name,
			caf_name=caf_name,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
			enqueue_after_commit=True,
		)
	)


def consultar_estado_dte(dte_boleta_name: str) -> dict:
	"""Obtiene token y consulta `getEstUp` para un `DTE Boleta` con `track_id`."""
	single = frappe.get_single("SII Configuration")
	cert = (single.get("certificado_digital") or "").strip()
	if not cert:
		frappe.throw("Configure certificado en SII Configuration.")
	b = frappe.get_doc("DTE Boleta", dte_boleta_name)
	if not frappe.has_permission("DTE Boleta", "read", b):
		frappe.throw("Sin permiso para DTE Boleta.", frappe.PermissionError)
	if not b.track_id:
		frappe.throw("DTE Boleta sin Track ID; no se puede consultar estado SII.")
	em = emisor_from_sii_configuration()
	st = get_signing_material_or_throw(cert)
	client = sii_client_from_sii_configuration()
	_, _tok, r0, r1 = client.get_semilla_y_token(st)
	tok = _tok
	append_dte_respuesta_sii(
		dte_boleta_name,
		accion="semilla",
		response_xml=r0,
		estado="00",
	)
	append_dte_respuesta_sii(
		dte_boleta_name,
		accion="token",
		response_xml=r1,
		estado="00",
	)
	raw = client.consultar_estado(b.track_id, token=tok, rut_emisor=em.rut)
	resp = parse_respuesta_sii(raw)
	append_dte_respuesta_sii(
		dte_boleta_name,
		accion="estado",
		response_xml=raw,
		estado=resp.estado,
		glosa=resp.glosa,
	)
	b = frappe.get_doc("DTE Boleta", dte_boleta_name)
	if resp.estado in ("0", "00", "EPR") or (resp.glosa and "ACEPT" in (resp.glosa or "").upper()):
		if resp.estado not in ("0", "00") and b.estado_envio == "ENVIADO":
			b.set("estado_envio", "EPR")
	elif "RCH" in (raw or "").upper() or resp.estado in ("RCH", "2", "-1"):
		b.set("estado_envio", "RCH")
	b.set("fecha_estado_final", now_datetime())
	b.save(ignore_permissions=True, ignore_version=True)
	return {
		"estado": resp.estado,
		"glosa": resp.glosa,
		"estado_dte_envio": b.estado_envio,
	}