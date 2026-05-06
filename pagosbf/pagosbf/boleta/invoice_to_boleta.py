"""Mapea `Sales Invoice` y `POS Invoice` (ERPNext) a `DTEBoletaData` (dominio puro)."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import frappe
from erpnext.accounts.doctype.pos_invoice.pos_invoice import POSInvoice
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from frappe.utils import flt

from pagosbf.pagosbf.dte import constants
from pagosbf.pagosbf.sii.rut import rut_para_dte_xml
from pagosbf.pagosbf.dte.types import (
	DetalleBoleta,
	DTEBoletaData,
	Emisor,
	Receptor,
	TotalesBoleta,
)


def _unidad_medida_item(it: Any) -> str | None:
	"""UnmdItem boleta (max 4). Preferimos UOM de linea, luego stock_uom."""
	u = getattr(it, "uom", None) or getattr(it, "stock_uom", None)
	if not u:
		return None
	s = str(u).strip()
	return (s[:4] if s else None)


def sales_invoice_to_dte_data(
	inv: SalesInvoice,
	*,
	folio: int,
	emisor: Emisor,
) -> DTEBoletaData:
	"""Proyecta lineas e impuestos. Tipo: 39 si IVA>0, si no 41 (exento)."""
	return _invoice_like_to_dte_data(inv, folio=folio, emisor=emisor, label="Sales Invoice")


def pos_invoice_to_dte_data(
	pos: POSInvoice,
	*,
	folio: int,
	emisor: Emisor,
) -> DTEBoletaData:
	"""Igual que Sales Invoice: neto/IVA/total e items desde POS."""
	return _invoice_like_to_dte_data(pos, folio=folio, emisor=emisor, label="POS Invoice")


def _invoice_like_to_dte_data(
	doc: Any,
	*,
	folio: int,
	emisor: Emisor,
	label: str,
) -> DTEBoletaData:
	neto_f = flt(doc.net_total)
	iva_f = flt(doc.total_taxes_and_charges)
	grand_f = flt(doc.grand_total)
	tipo = (
		constants.TIPO_DTE_BOLETA_AFECTA
		if int(round(iva_f)) > 0
		else constants.TIPO_DTE_BOLETA_EXENTA
	)
	items_seq = getattr(doc, "items", None)
	if items_seq is None and hasattr(doc, "get"):
		items_seq = doc.get("items")
	lines = _detalles_desde_items(list(items_seq or []), tipo_41=tipo == constants.TIPO_DTE_BOLETA_EXENTA)
	if not lines:
		frappe.throw(f"{label} sin lineas, no se puede timbrar boleta SII.")
	if tipo == constants.TIPO_DTE_BOLETA_EXENTA:
		tot = TotalesBoleta(
			monto_neto=0,
			iva=0,
			monto_exento=int(round(neto_f if neto_f else grand_f)),
			monto_total=int(round(grand_f)),
		)
		tot.validate()
	else:
		tot = TotalesBoleta(
			monto_neto=int(round(neto_f)),
			iva=int(round(iva_f)),
			monto_exento=0,
			monto_total=int(round(grand_f)),
		)
		tot.validate()
	recv = _receptor_desde_customer(doc.customer, doc.customer_name)
	return DTEBoletaData(
		tipo_dte=tipo,
		folio=folio,
		fecha_emision=_fecha_emision_doc(doc, label=label),
		emisor=emisor,
		receptor=recv,
		detalles=lines,
		totales=tot,
		ind_servicio=3,
		timestamp_firma=_timestamp_firma_doc(doc, label=label),
	)


def _fecha_emision_doc(doc: Any, *, label: str) -> date:
	d = doc.posting_date
	if not d:
		frappe.throw(f"{label} sin posting_date.")
	if isinstance(d, str):
		return date.fromisoformat(d[:10])
	if isinstance(d, date):
		return d
	raise TypeError("posting_date inesperado.")


def _timestamp_firma_doc(doc: Any, *, label: str) -> datetime:
	fe = _fecha_emision_doc(doc, label=label)
	tv = doc.posting_time
	if not tv:
		return datetime.combine(fe, time(12, 0, 0))
	if isinstance(tv, str):
		parts = tv.replace(".", ":").split(":")
		h, m, s = int(parts[0]), 0, 0
		if len(parts) > 1:
			m = int(parts[1])
		if len(parts) > 2:
			s = int(float(parts[2]))
		return datetime.combine(fe, time(h, m, s))
	if isinstance(tv, datetime):
		return tv
	if isinstance(tv, time):
		return datetime.combine(fe, tv)
	return datetime.combine(fe, time(12, 0, 0))


def _receptor_desde_customer(customer: str | None, customer_name: str | None) -> Receptor:
	rut = "66666666-6"
	if customer:
		crow = frappe.db.get_value("Customer", customer, "tax_id")
		if crow and str(crow).strip():
			try:
				rut = rut_para_dte_xml(str(crow))
			except ValueError as e:
				frappe.throw(
					f"RUT en Customer {customer!r} (tax_id) invalido para DTE: {crow!r}. {e!s}",
				)
	rzn = (customer_name or customer or "").strip()
	return Receptor(rut=rut, razon_social=rzn)


def _detalles_desde_items(items: list[Any], *, tipo_41: bool) -> tuple[DetalleBoleta, ...]:
	out: list[DetalleBoleta] = []
	for it in items:
		qty = Decimal(str(flt(it.qty) or 0))
		if qty <= 0:
			continue
		net = Decimal(str(flt(it.net_amount or 0)))
		tax = Decimal(str(flt(getattr(it, "item_tax_amount", None) or 0)))
		mrow = (net + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		monto_i = int(mrow) if mrow == mrow.to_integral() else int(mrow.to_integral())
		prc = mrow / qty if qty else mrow
		out.append(
			DetalleBoleta(
				nro_lin_det=len(out) + 1,
				nombre_item=(it.item_name or it.item_code or "Item")[:100],
				cantidad=qty,
				precio_item=prc,
				monto_item=Decimal(monto_i),
				indica_exento=tipo_41,
				unidad_medida=_unidad_medida_item(it),
			)
		)
	return tuple(out)


__all__ = ["pos_invoice_to_dte_data", "sales_invoice_to_dte_data"]
