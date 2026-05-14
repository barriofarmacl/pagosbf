# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""API RPC para Factura Electronica 33 (`DTE Documento`)."""

from __future__ import annotations

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from pagosbf.pagosbf.facturacion import emision


@frappe.whitelist()
def emitir(
	sales_invoice: str | None = None,
	caf: str | None = None,
	en_background: int | str | None = None,
) -> str | dict:
	"""Emite Factura Electronica 33 desde una `Sales Invoice` enviada."""
	si = (sales_invoice or "").strip()
	if not si:
		frappe.throw("Falta sales_invoice (name).")
	_require_sales_invoice_permission(si)
	if int(en_background or 0) == 1:
		job = emision.encolar_emision_factura(si, caf_name=caf)
		return {"enqueued": True, "job": job, "sales_invoice": si}
	return emision.ejecutar_emision_factura(si, caf_name=caf)


@frappe.whitelist()
def consultar_estado(dte_documento: str | None = None) -> dict:
	"""Token fresco + `getEstUp` SII; actualiza `DTE Documento` y respuestas."""
	name = (dte_documento or "").strip()
	if not name:
		frappe.throw("Falta dte_documento (name).")
	doc = frappe.get_doc("DTE Documento", name)
	if not frappe.has_permission("DTE Documento", "read", doc):
		frappe.throw("Sin permiso DTE Documento.", frappe.PermissionError)
	return emision.consultar_estado_dte_documento(name)


def _require_sales_invoice_permission(name: str) -> None:
	inv: SalesInvoice = frappe.get_doc("Sales Invoice", name)
	if not frappe.has_permission("Sales Invoice", "read", inv):
		frappe.throw("Sin permiso para esta factura de venta.", frappe.PermissionError)
	if inv.docstatus != 1:
		frappe.throw("Solo se emiten DTEs para facturas confirmadas (enviadas).")


__all__ = ["consultar_estado", "emitir"]
