"""Emision Factura Electronica 33 con persistencia `DTE Documento`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import frappe
from frappe.model.document import Document
from frappe.utils import now, now_datetime

from pagosbf.pagosbf.boleta.caf_file import load_caf_data
from pagosbf.pagosbf.boleta.cert_utils import get_signing_material_or_throw, resolve_digitador_rut
from pagosbf.pagosbf.boleta.emision import (
	emisor_from_sii_configuration,
	resolve_caf_por_tipo_dte,
	validate_resolucion_para_caratula_envio_boleta,
)
from pagosbf.pagosbf.dte import factura_xml
from pagosbf.pagosbf.dte.caf_parser import CAFData
from pagosbf.pagosbf.dte.constants import TIPO_DTE_FACTURA_ELECTRONICA
from pagosbf.pagosbf.dte.envio_builder import RUT_SII_CARATULA, CaratulaEmision, build_envio_dte_draft
from pagosbf.pagosbf.dte.folio_allocator import CAFNotFoundError, FolioExhaustedError, allocate_next_folio
from pagosbf.pagosbf.dte.xml_signer import sign_envio_dte
from pagosbf.pagosbf.facturacion.invoice_to_factura import sales_invoice_to_factura_data
from pagosbf.pagosbf.sii.sii_client import SIIClientError
from pagosbf.pagosbf.sii.sii_frappe import sii_client_from_sii_configuration
from pagosbf.pagosbf.sii.sii_response_xml import parse_respuesta_sii

try:
	_CL_TZ = ZoneInfo("America/Santiago")
except Exception:  # noqa: BLE001
	_CL_TZ = timezone.utc


def ejecutar_emision_factura(
	sales_invoice_name: str,
	*,
	caf_name: str | None = None,
) -> str:
	"""Crea/actualiza `DTE Documento`, envia EnvioDTE al SII y retorna su `name`."""
	_require_factura_33_enabled()
	if not sales_invoice_name:
		frappe.throw("Falta sales_invoice_name para emitir Factura Electronica 33.")

	exist = frappe.db.get_value(
		"DTE Documento",
		{"sales_invoice": sales_invoice_name, "tipo_dte": str(TIPO_DTE_FACTURA_ELECTRONICA)},
		"name",
	)
	if exist:
		prev = frappe.get_doc("DTE Documento", exist)
		if prev.estado_envio == "ENVIADO" and prev.track_id:
			return prev.name
		if prev.estado_envio == "RECHAZADO_LOCAL":
			frappe.delete_doc(
				"DTE Documento",
				prev.name,
				force=1,
				ignore_permissions=True,
				flags={"ignore_links": 1},
			)
			exist = None

	inv = frappe.get_doc("Sales Invoice", sales_invoice_name)
	if inv.docstatus != 1:
		frappe.throw("Sales Invoice debe estar enviada (docstatus=1) para emitir DTE 33.")

	single = frappe.get_single("SII Configuration")
	cert = (single.get("certificado_digital") or "").strip()
	if not cert:
		frappe.throw("Configure `certificado_digital` en SII Configuration.")
	emisor = emisor_from_sii_configuration()
	caf = caf_name or resolve_caf_por_tipo_dte(TIPO_DTE_FACTURA_ELECTRONICA)
	caf_d: CAFData = load_caf_data(caf)
	if int(caf_d.tipo_dte) != TIPO_DTE_FACTURA_ELECTRONICA:
		frappe.throw(f"CAF {caf!r} es TD={caf_d.tipo_dte}, pero Factura Electronica requiere TD=33.")
	try:
		folio = allocate_next_folio(caf)
	except CAFNotFoundError as exc:
		frappe.throw(str(exc))
	except FolioExhaustedError as exc:
		frappe.throw(str(exc))

	data = sales_invoice_to_factura_data(
		inv,
		folio=folio,
		emisor=emisor,
		acteco=_acteco_from_sii_configuration(single),
	)
	doc = _crear_o_recargar_dte_documento(
		exist,
		sales_invoice=sales_invoice_name,
		data=data,
		caf=caf,
	)
	if not exist:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True, ignore_version=True)
	doc.reload()
	log = _Logger(doc.name)
	doc.set("estado_envio", "VALIDANDO")
	doc.set("error_log", None)
	doc.save(ignore_permissions=True, ignore_version=True)

	try:
		material = get_signing_material_or_throw(cert)
		st_rut = resolve_digitador_rut(cert, material, emisor.rut)
		validate_resolucion_para_caratula_envio_boleta()

		draft = factura_xml.build_factura_33_documento_draft(data)
		factura_xml.validate_dte_factura_xml(factura_xml._serialize(draft.dte_element))  # noqa: SLF001
		dte_signed = factura_xml.finalize_dte_signed(draft, caf_d, material, data.timestamp_firma)
		caratula = CaratulaEmision(
			rut_emisor=emisor.rut,
			rut_envia=st_rut,
			rut_receptor=RUT_SII_CARATULA,
			fch_resol=emisor.resolucion_fecha,
			nro_resol=int(emisor.resolucion_numero or 0),
			tmst_firma_env=_now_santiago(),
			tipo_dte=TIPO_DTE_FACTURA_ELECTRONICA,
			set_dte_id="SetDte1",
		)
		envio_draft = build_envio_dte_draft(dte_signed, caratula)
		sobre = sign_envio_dte(
			envio_draft,
			material,
			reference_uri=caratula.set_dte_id,
			# DTEUpload no requiere schemaLocation. Mantener el sobre sin esa
			# inyeccion evita alterar el contexto namespace del DTE ya firmado.
			inject_portal_schema_location=False,
		)

		client = sii_client_from_sii_configuration()
		_sem, token, raw_semilla, raw_token = client.get_semilla_y_token(material)
		log.append("semilla", request_xml=raw_semilla or None, response_xml=raw_semilla, estado="00")
		log.append("token", request_xml=raw_semilla or None, response_xml=raw_token, estado="00")

		doc = frappe.get_doc("DTE Documento", doc.name)
		doc.set("xml_dte_firmado", _bytes_xml_log(dte_signed))
		doc.set("xml_sobre_firmado", _bytes_xml_log(sobre))
		doc.save(ignore_permissions=True, ignore_version=True)

		upload = client.enviar_sobre(sobre, token=token, rut_emisor=emisor.rut, rut_digitador=st_rut)
		log.append(
			"envio",
			request_xml=_bytes_xml_log(sobre)[:20000],
			response_xml=upload.response_text[:20000] if upload.response_text else None,
			estado=str(upload.status_code),
			glosa=upload.resumen,
		)
		doc = frappe.get_doc("DTE Documento", doc.name)
		doc.set("estado_envio", "ENVIADO")
		doc.set("track_id", str(upload.track_id))
		doc.set("fecha_envio", now_datetime())
		doc.save(ignore_permissions=True, ignore_version=True)
	except Exception as exc:  # noqa: BLE001
		if isinstance(exc, SIIClientError):
			_append_respuestas_sii_client_error(log, exc)
		err = f"{type(exc).__name__}: {exc!s}"[:20000]
		failed = frappe.get_doc("DTE Documento", doc.name)
		failed.set("estado_envio", "RECHAZADO_LOCAL")
		failed.set("error_log", err)
		failed.save(ignore_permissions=True, ignore_version=True)
		raise

	return doc.name


def encolar_emision_factura(
	sales_invoice_name: str,
	*,
	caf_name: str | None = None,
) -> str:
	if not sales_invoice_name:
		frappe.throw("Falta sales_invoice_name para encolar Factura Electronica 33.")
	return str(
		frappe.enqueue(
			"pagosbf.pagosbf.facturacion.emision.ejecutar_emision_factura",
			queue="default",
			job_name=f"emision_sii_factura_{sales_invoice_name}",
			sales_invoice_name=sales_invoice_name,
			caf_name=caf_name,
			enqueue_after_commit=True,
		)
	)


def consultar_estado_dte_documento(dte_documento_name: str) -> dict:
	"""Consulta estado SII y registra la respuesta en `DTE Documento.respuestas`."""
	single = frappe.get_single("SII Configuration")
	cert = (single.get("certificado_digital") or "").strip()
	if not cert:
		frappe.throw("Configure certificado en SII Configuration.")
	doc = frappe.get_doc("DTE Documento", dte_documento_name)
	if not frappe.has_permission("DTE Documento", "read", doc):
		frappe.throw("Sin permiso para DTE Documento.", frappe.PermissionError)
	if not doc.track_id:
		frappe.throw("DTE Documento sin Track ID; no se puede consultar estado SII.")
	emisor = emisor_from_sii_configuration()
	material = get_signing_material_or_throw(cert)
	client = sii_client_from_sii_configuration()
	_, token, raw_semilla, raw_token = client.get_semilla_y_token(material)
	_log = _Logger(doc.name)
	_log.append("semilla", request_xml=None, response_xml=raw_semilla, estado="00")
	_log.append("token", request_xml=None, response_xml=raw_token, estado="00")
	raw = client.consultar_estado(doc.track_id, token=token, rut_emisor=emisor.rut)
	resp = parse_respuesta_sii(raw)
	_log.append("estado", request_xml=None, response_xml=raw, estado=resp.estado, glosa=resp.glosa)
	doc = frappe.get_doc("DTE Documento", dte_documento_name)
	if resp.estado in ("0", "00", "EPR") or (resp.glosa and "ACEPT" in resp.glosa.upper()):
		if resp.estado not in ("0", "00") and doc.estado_envio == "ENVIADO":
			doc.set("estado_envio", "EPR")
	elif "RCH" in (raw or "").upper() or resp.estado in ("RCH", "2", "-1"):
		doc.set("estado_envio", "RCH")
	doc.set("fecha_estado_final", now_datetime())
	doc.save(ignore_permissions=True, ignore_version=True)
	return {"estado": resp.estado, "glosa": resp.glosa, "estado_dte_envio": doc.estado_envio}


def _crear_o_recargar_dte_documento(
	exist: str | None,
	*,
	sales_invoice: str,
	data: Any,
	caf: str,
) -> Document:
	m = {
		"doctype": "DTE Documento",
		"sales_invoice": sales_invoice,
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
		doc = frappe.get_doc("DTE Documento", exist)
		doc.update(m)
		return doc
	return frappe.get_doc(m)


class _Logger:
	def __init__(self, dte_documento_name: str) -> None:
		self._name = dte_documento_name

	def append(
		self,
		accion: str,
		request_xml: str | None,
		*,
		response_xml: str | None = None,
		estado: str | None = None,
		glosa: str | None = None,
	) -> None:
		doc = frappe.get_doc("DTE Documento", self._name)
		doc.append(
			"respuestas",
			{
				"timestamp": now(),
				"accion": accion,
				"estado": estado or "",
				"glosa": glosa or "",
				"request_xml": request_xml or "",
				"response_xml": response_xml or "",
			},
		)
		doc.save(ignore_permissions=True, ignore_version=True)


def _append_respuestas_sii_client_error(log: _Logger, exc: SIIClientError) -> None:
	if exc.phase == "getSeed" and exc.raw_xml:
		log.append("semilla", request_xml=None, response_xml=exc.raw_xml, estado=exc.sii_estado, glosa=exc.sii_glosa)
	elif exc.phase == "getToken":
		if exc.raw_previous:
			log.append("semilla", request_xml=None, response_xml=exc.raw_previous, estado="00")
		if exc.raw_xml:
			glosa = exc.sii_glosa or ""
			if exc.semilla_obtenida:
				glosa = f"{glosa} | semilla_obtenida={exc.semilla_obtenida}" if glosa else f"semilla_obtenida={exc.semilla_obtenida}"
			log.append("token", request_xml=None, response_xml=exc.raw_xml, estado=exc.sii_estado, glosa=glosa or None)


def _require_factura_33_enabled() -> None:
	enabled = int(frappe.db.get_single_value("SII Configuration", "habilitar_factura_electronica") or 0) == 1
	if not enabled:
		frappe.throw(
			"Active `habilitar_factura_electronica` en SII Configuration antes de emitir Factura Electronica 33.",
			frappe.ValidationError,
		)


def _acteco_from_sii_configuration(single: Document) -> str:
	return ((single.get("acteco") or "").strip() or "477310")[:6]


def _bytes_xml_log(value: bytes) -> str:
	return value.decode("iso-8859-1", errors="replace")


def _now_santiago() -> datetime:
	return datetime.now(tz=_CL_TZ).replace(tzinfo=None)


__all__ = ["consultar_estado_dte_documento", "ejecutar_emision_factura", "encolar_emision_factura"]
