# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Emision y consulta DTE boleta (SII) desde Frappe. Ver design ADR-B6."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import frappe
from erpnext.accounts.doctype.pos_invoice.pos_invoice import POSInvoice
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from pagosbf.pagosbf.boleta import emision, xml_preview
from pagosbf.pagosbf.boleta.be_set_batch import construir_sobre_set_prueba_be


@frappe.whitelist()
def emitir(
	sales_invoice: str | None = None,
	pos_invoice: str | None = None,
	caf: str | None = None,
	en_background: int | str | None = None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
) -> str | dict:
	"""Orquesta DTE+SII para una ``Sales Invoice`` o ``POS Invoice`` enviada (docstatus=1).

	Debe indicarse exactamente uno de ``sales_invoice`` o ``pos_invoice`` (no ambos ni ninguno).
	El primer argumento posicional sigue mapeando a ``sales_invoice`` (compatibilidad con llamadas
	previas como ``emitir('SINV-…')``).

	Args:
	    sales_invoice: name de ``Sales Invoice``.
	    pos_invoice: name de ``POS Invoice``.
	    caf: opcional, name de ``CAF`` (mismo TipoDTE que el calculado desde IVA).
	    en_background: si truthy, encola job y retorna ``dict`` con ``enqueued``, ``job`` y el origen.
	    sii_cod_ref / sii_razon_ref: opcional, referencia en XML (set BE: ``SET`` / ``CASO-n``). Si se omiten,
	        se reutilizan los valores en ``DTE Boleta`` cuando ya exista borrador.

	Returns:
	    Nombre de ``DTE Boleta`` o dict de encolado.
	"""
	si = (sales_invoice or "").strip() or None
	pi = (pos_invoice or "").strip() or None
	if bool(si) == bool(pi):
		frappe.throw(
			"Indique exactamente sales_invoice o pos_invoice (no ambos ni ninguno).",
		)
	if si:
		_require_source_permission("Sales Invoice", si)
	else:
		assert pi is not None
		_require_source_permission("POS Invoice", pi)

	bg = int(en_background or 0) == 1
	if bg:
		if si:
			job = emision.encolar_emision_sii(
				si,
				caf_name=caf,
				sii_cod_ref=sii_cod_ref,
				sii_razon_ref=sii_razon_ref,
			)
			return {"enqueued": True, "job": job, "sales_invoice": si}
		job = emision.encolar_emision_sii(
			pos_invoice_name=pi,
			caf_name=caf,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
		)
		return {"enqueued": True, "job": job, "pos_invoice": pi}
	if si:
		return emision.ejecutar_emision_sii(
			si,
			caf_name=caf,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
		)
	return emision.ejecutar_emision_sii(
		pos_invoice_name=pi,
		caf_name=caf,
		sii_cod_ref=sii_cod_ref,
		sii_razon_ref=sii_razon_ref,
	)


@frappe.whitelist()
def vista_previa_xml_boleta(
	pos_invoice: str | None = None,
	sales_invoice: str | None = None,
	folio: int | None = None,
	caf: str | None = None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
	firmar: int | str | None = 1,
) -> dict[str, str]:
	"""Genera XML DTE (y opcionalmente DTE firmado + sobre) sin consumir folio ni llamar al SII.

	Indique exactamente uno de ``pos_invoice`` o ``sales_invoice``. Debe pasar ``folio`` explicito
	dentro del rango del CAF (no se incrementa ``folios_consumidos``).

	Returns:
	    Dict con ``xml_dte``, ``xml_dte_firmado``, ``xml_sobre_firmado``, ``caf_usado``, ``tipo_dte``, ``folio``.
	"""
	si = (sales_invoice or "").strip() or None
	pi = (pos_invoice or "").strip() or None
	if bool(si) == bool(pi):
		frappe.throw("Indique exactamente sales_invoice o pos_invoice (no ambos ni ninguno).")
	if folio is None or int(folio) < 1:
		frappe.throw("Indique folio (entero >= 1) dentro del rango del CAF.")
	if si:
		_require_source_permission("Sales Invoice", si)
		return xml_preview.preview_boleta_xml(
			source_doctype="Sales Invoice",
			source_name=si,
			folio=int(folio),
			caf_name=caf,
			sii_cod_ref=sii_cod_ref,
			sii_razon_ref=sii_razon_ref,
			firmar=bool(int(firmar or 1)),
		)
	assert pi is not None
	_require_source_permission("POS Invoice", pi)
	return xml_preview.preview_boleta_xml(
		source_doctype="POS Invoice",
		source_name=pi,
		folio=int(folio),
		caf_name=caf,
		sii_cod_ref=sii_cod_ref,
		sii_razon_ref=sii_razon_ref,
		firmar=bool(int(firmar or 1)),
	)


@frappe.whitelist()
def sobre_set_prueba_be(
	folios: list | tuple | str | None = None,
	caf: str | None = None,
	firmar: int | str | None = 1,
	fecha_emision: str | None = None,
) -> dict:
	"""Arma los 5 DTE del set BE (CASO-1..5), timbrados y firmados, mas sobre firmado.

	No consume folios en BD ni llama al SII. Uso: certificacion manual (subir XML al portal).

	Args:
	    folios: lista de 5 folios (default 11-15). Puede venir como JSON string desde el cliente.
	    caf: opcional, name del DocType CAF (tipo 39).
	    firmar: si 0, solo XML con TED sin XMLDSig.
	    fecha_emision: opcional YYYY-MM-DD. Si se omite, se usa la fecha en America/Santiago
	        alineada al timbre/firma del armado (mismo criterio que ``construir_sobre_set_prueba_be``).

	Returns:
	    Dict con ``casos``, ``xml_sobre``, ``xml_sobre_firmado``, ``caf_usado``, ``folios``, ``firmado``.
	"""
	if not frappe.has_permission("SII Configuration", "read"):
		frappe.throw("Se requiere permiso de lectura sobre SII Configuration.", frappe.PermissionError)
	parsed_folios = folios
	if isinstance(folios, str) and folios.strip():
		parsed_folios = frappe.parse_json(folios)
	return construir_sobre_set_prueba_be(
		folios=parsed_folios,
		caf_name=caf,
		firmar=bool(int(firmar or 1)),
		fecha_emision=fecha_emision,
	)


@frappe.whitelist()
def datos_impresion_boleta_pos(pos_invoice: str | None = None) -> dict:
	"""Datos de timbre / DTE para ticket o integraciones; no importable desde barriofarma_app (usar frappe.call).

	Returns:
	    Dict con ``ok`` (bool), ``pos_invoice``, y si hay DTE: ``dte_boleta``, ``tipo_dte``, ``folio``,
	    ``track_id``, ``estado_envio``, ``rut_emisor_fmt``, ``ted_compact``, ``ted_pdf417_payload``.
	"""
	from pagosbf.pagosbf.boleta.print_context import get_pos_invoice_sii_block

	pi = (pos_invoice or "").strip()
	if not pi:
		frappe.throw("Falta pos_invoice (name).")
	_require_source_permission("POS Invoice", pi)
	blk = get_pos_invoice_sii_block(SimpleNamespace(name=pi))
	if not blk:
		return {
			"ok": False,
			"mensaje": "Sin DTE Boleta vinculada a este POS Invoice.",
			"pos_invoice": pi,
		}
	out = dict(blk)
	dt_name = out.pop("name", None)
	out["ok"] = True
	out["pos_invoice"] = pi
	out["dte_boleta"] = dt_name
	return out


@frappe.whitelist()
def timbre_pdf417_data_url(pos_invoice: str | None = None) -> dict:
	"""PNG del timbre PDF417 (data URL) para impresion / Print Format.

	Requiere ``DTE Boleta`` con ``ted_pdf417_payload`` (mismo criterio que ``datos_impresion_boleta_pos``).

	Returns:
	    ``ok``, ``data_url`` (``data:image/png;base64,...``) o ``mensaje`` en error.
	"""
	from pagosbf.pagosbf.boleta.pdf417_render import ted_payload_to_png_bytes
	from pagosbf.pagosbf.boleta.print_context import get_pos_invoice_sii_block

	pi = (pos_invoice or "").strip()
	if not pi:
		frappe.throw("Falta pos_invoice (name).")
	_require_source_permission("POS Invoice", pi)
	blk = get_pos_invoice_sii_block(SimpleNamespace(name=pi))
	if not blk:
		return {"ok": False, "mensaje": "Sin DTE Boleta vinculada a este POS Invoice.", "pos_invoice": pi}
	payload = (blk.get("ted_pdf417_payload") or "").strip()
	if not payload:
		return {"ok": False, "mensaje": "Sin payload TED para PDF417.", "pos_invoice": pi}
	try:
		raw = ted_payload_to_png_bytes(payload)
	except ValueError as exc:
		return {"ok": False, "mensaje": str(exc)[:500], "pos_invoice": pi}
	b64 = base64.b64encode(raw).decode("ascii")
	return {
		"ok": True,
		"pos_invoice": pi,
		"data_url": f"data:image/png;base64,{b64}",
	}


@frappe.whitelist()
def consultar_estado(dte_boleta: str) -> dict:
	"""Token fresco + `getEstUp` SII; actualiza `DTE Boleta` y tabla de respuestas."""
	if not dte_boleta:
		frappe.throw("Falta dte_boleta (name).")
	b = frappe.get_doc("DTE Boleta", dte_boleta)
	if not frappe.has_permission("DTE Boleta", "read", b):
		frappe.throw("Sin permiso DTE Boleta.", frappe.PermissionError)
	return emision.consultar_estado_dte(dte_boleta)


@frappe.whitelist()
def on_sales_invoice_submit(doc, _method: str | None = None) -> None:
	"""Registrado en hooks; no invocar directo. Encola emision segun SII Configuration."""
	if doc.doctype != "Sales Invoice":
		return
	if getattr(doc, "is_consolidated", 0):
		return
	encolar = int(frappe.db.get_single_value("SII Configuration", "encolar_emision_en_submit") or 0) == 1
	if not encolar or doc.flags.get("skip_pagosbf_boleta_sii"):
		return
	if doc.docstatus != 1 or getattr(doc, "is_return", 0):
		return
	if not frappe.db.get_single_value("SII Configuration", "certificado_digital"):
		return
	row = frappe.db.get_value(
		"DTE Boleta",
		{"sales_invoice": doc.name},
		["estado_envio"],
		as_dict=True,
	)
	if row and row.get("estado_envio") == "ENVIADO":
		return
	emision.encolar_emision_sii(doc.name)


@frappe.whitelist()
def on_pos_invoice_submit(doc, _method: str | None = None) -> None:
	"""Registrado en hooks; encola emision SII para POS Invoice (misma politica que Sales Invoice)."""
	if doc.doctype != "POS Invoice":
		return
	encolar = int(frappe.db.get_single_value("SII Configuration", "encolar_emision_en_submit") or 0) == 1
	if not encolar or doc.flags.get("skip_pagosbf_boleta_sii"):
		return
	if doc.docstatus != 1 or getattr(doc, "is_return", 0):
		return
	if not frappe.db.get_single_value("SII Configuration", "certificado_digital"):
		return
	row = frappe.db.get_value(
		"DTE Boleta",
		{"pos_invoice": doc.name},
		["estado_envio"],
		as_dict=True,
	)
	if row and row.get("estado_envio") == "ENVIADO":
		return
	emision.encolar_emision_sii(pos_invoice_name=doc.name)


def _require_source_permission(doctype: str, name: str) -> None:
	if doctype == "Sales Invoice":
		inv: SalesInvoice = frappe.get_doc("Sales Invoice", name)
		if not frappe.has_permission("Sales Invoice", "read", inv):
			frappe.throw("Sin permiso para esta factura de venta.", frappe.PermissionError)
		if inv.docstatus != 1:
			frappe.throw("Solo se emiten DTEs para facturas confirmadas (enviadas).")
		return
	if doctype == "POS Invoice":
		pos: POSInvoice = frappe.get_doc("POS Invoice", name)
		if not frappe.has_permission("POS Invoice", "read", pos):
			frappe.throw("Sin permiso para esta factura POS.", frappe.PermissionError)
		if pos.docstatus != 1:
			frappe.throw("Solo se emiten DTEs para POS Invoice confirmadas (enviadas).")
		return
	frappe.throw(f"DocType origen no soportado: {doctype!r}.", frappe.ValidationError)
