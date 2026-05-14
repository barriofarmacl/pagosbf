"""Mapea `Sales Invoice` ERPNext a datos puros de Factura Electronica 33."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from frappe.utils import flt

from pagosbf.pagosbf.dte.constants import (
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from pagosbf.pagosbf.dte.types import Emisor, Receptor
from pagosbf.pagosbf.sii.rut import rut_para_dte_xml

from .types import DetalleFactura, Factura33Data, ReferenciaFactura, TotalesFactura


def sales_invoice_to_factura_data(
	inv: SalesInvoice,
	*,
	folio: int,
	emisor: Emisor,
	acteco: str | None = None,
) -> Factura33Data:
	"""Proyecta una `Sales Invoice` enviada a `Factura33Data`.

	La separacion afecta/exenta se calcula por linea: una linea con impuesto de item en cero
	se informa con `IndExe=1` y suma a `MntExe`; las demas suman a `MntNeto`.
	"""
	items_seq = getattr(inv, "items", None)
	if items_seq is None and hasattr(inv, "get"):
		items_seq = inv.get("items")
	detalles = _detalles_desde_items(list(items_seq or []))
	if not detalles:
		frappe.throw("Sales Invoice sin lineas, no se puede emitir Factura Electronica 33.")

	monto_neto = sum(d.monto_item for d in detalles if not d.indica_exento)
	monto_exento = sum(d.monto_item for d in detalles if d.indica_exento)
	iva = int(round(flt(getattr(inv, "total_taxes_and_charges", 0) or 0)))
	grand_total = int(round(flt(getattr(inv, "grand_total", 0) or 0)))
	total_calculado = monto_neto + monto_exento + iva
	totales = TotalesFactura(
		monto_neto=int(monto_neto),
		iva=int(iva),
		monto_exento=int(monto_exento),
		monto_total=grand_total or total_calculado,
	)
	totales.validate()

	data = Factura33Data(
		tipo_dte=TIPO_DTE_FACTURA_ELECTRONICA,
		folio=int(folio),
		fecha_emision=_fecha_emision_doc(inv),
		emisor=emisor,
		receptor=_receptor_desde_customer(getattr(inv, "customer", None), getattr(inv, "customer_name", None)),
		detalles=tuple(detalles),
		totales=totales,
		acteco=(acteco or "").strip() or None,
		timestamp_firma=_timestamp_firma_doc(inv),
	)
	data.validate()
	return data


def sales_invoice_to_nota_credito_debito_data(
	inv: SalesInvoice,
	*,
	folio: int,
	emisor: Emisor,
	acteco: str | None = None,
	referencia_tipo_dte: int | str | None = None,
	referencia_folio: int | str | None = None,
	referencia_fecha: date | str | None = None,
	cod_ref: int | None = None,
	razon_ref: str | None = None,
) -> Factura33Data:
	"""Proyecta `Sales Invoice` ERPNext a Nota de Credito 61 o Nota de Debito 56.

	ERPNext v15 modela la Nota de Credito como `Sales Invoice.is_return=1` y la
	Nota de Debito como `Sales Invoice.is_debit_note=1`. Las referencias SII se
	pueden derivar desde `DTE Documento` del `return_against` o informarse
	explicitamente para casos como NDE contra una NCE.
	"""
	tipo_dte = _tipo_nota_desde_sales_invoice(inv)
	items_seq = getattr(inv, "items", None)
	if items_seq is None and hasattr(inv, "get"):
		items_seq = inv.get("items")
	detalles = _detalles_desde_items(list(items_seq or []), absolute_values=True)
	if not detalles:
		frappe.throw("Sales Invoice de nota sin lineas, no se puede mapear DTE 61/56.")

	monto_neto = sum(d.monto_item for d in detalles if not d.indica_exento)
	monto_exento = sum(d.monto_item for d in detalles if d.indica_exento)
	iva = int(round(abs(flt(getattr(inv, "total_taxes_and_charges", 0) or 0))))
	grand_total = int(round(abs(flt(getattr(inv, "grand_total", 0) or 0))))
	total_calculado = monto_neto + monto_exento + iva
	totales = TotalesFactura(
		monto_neto=int(monto_neto),
		iva=int(iva),
		monto_exento=int(monto_exento),
		monto_total=grand_total if grand_total or not total_calculado else total_calculado,
	)
	totales.validate()

	data = Factura33Data(
		tipo_dte=tipo_dte,
		folio=int(folio),
		fecha_emision=_fecha_emision_doc(inv),
		emisor=emisor,
		receptor=_receptor_desde_customer(getattr(inv, "customer", None), getattr(inv, "customer_name", None)),
		detalles=tuple(detalles),
		totales=totales,
		acteco=(acteco or "").strip() or None,
		timestamp_firma=_timestamp_firma_doc(inv),
		referencias=(
			_referencia_nota_desde_erpnext(
				inv,
				tipo_dte=tipo_dte,
				referencia_tipo_dte=referencia_tipo_dte,
				referencia_folio=referencia_folio,
				referencia_fecha=referencia_fecha,
				cod_ref=cod_ref,
				razon_ref=razon_ref,
			),
		),
	)
	data.validate()
	return data


def _tipo_nota_desde_sales_invoice(inv: SalesInvoice) -> int:
	is_return = int(flt(getattr(inv, "is_return", 0) or 0)) == 1
	is_debit_note = int(flt(getattr(inv, "is_debit_note", 0) or 0)) == 1
	if is_return and is_debit_note:
		frappe.throw("Sales Invoice no puede ser simultaneamente Nota de Credito y Nota de Debito.")
	if is_return:
		return TIPO_DTE_NOTA_CREDITO_ELECTRONICA
	if is_debit_note:
		return TIPO_DTE_NOTA_DEBITO_ELECTRONICA
	frappe.throw("Sales Invoice debe tener is_return=1 o is_debit_note=1 para mapear DTE 61/56.")
	raise AssertionError("unreachable")


def _referencia_nota_desde_erpnext(
	inv: SalesInvoice,
	*,
	tipo_dte: int,
	referencia_tipo_dte: int | str | None,
	referencia_folio: int | str | None,
	referencia_fecha: date | str | None,
	cod_ref: int | None,
	razon_ref: str | None,
) -> ReferenciaFactura:
	if referencia_tipo_dte is None or referencia_folio is None or referencia_fecha is None:
		derived = _referencia_desde_dte_documento_return_against(inv)
		if referencia_tipo_dte is None:
			referencia_tipo_dte = derived.tipo_dte
		if referencia_folio is None:
			referencia_folio = derived.folio
		if referencia_fecha is None:
			referencia_fecha = derived.fecha_emision

	if referencia_tipo_dte is None or referencia_folio is None or referencia_fecha is None:
		frappe.throw("Nota 61/56 requiere referencia SII completa (tipo, folio y fecha).")

	ref_date = _coerce_date(referencia_fecha)
	default_cod = 3 if int(tipo_dte) == TIPO_DTE_NOTA_CREDITO_ELECTRONICA else 1
	return ReferenciaFactura(
		nro_lin_ref=1,
		tpo_doc_ref=str(referencia_tipo_dte).strip(),
		folio_ref=str(referencia_folio).strip(),
		fecha_ref=ref_date,
		cod_ref=cod_ref if cod_ref is not None else default_cod,
		razon_ref=(razon_ref or getattr(inv, "remarks", None) or "").strip() or None,
	)


def _referencia_desde_dte_documento_return_against(inv: SalesInvoice) -> frappe._dict:
	return_against = (getattr(inv, "return_against", None) or "").strip()
	if not return_against:
		frappe.throw("Sales Invoice de nota requiere return_against o referencia SII explicita.")
	row = frappe.db.get_value(
		"DTE Documento",
		{"sales_invoice": return_against},
		["tipo_dte", "folio", "fecha_emision"],
		as_dict=True,
		order_by="creation desc",
	)
	if not row:
		frappe.throw(
			f"No existe DTE Documento para return_against {return_against!r}; "
			"informe referencia_tipo_dte/referencia_folio/referencia_fecha manualmente."
		)
	return row


def _fecha_emision_doc(doc: Any) -> date:
	d = doc.posting_date
	if not d:
		frappe.throw("Sales Invoice sin posting_date.")
	if isinstance(d, str):
		return date.fromisoformat(d[:10])
	if isinstance(d, date):
		return d
	raise TypeError("posting_date inesperado.")


def _coerce_date(value: date | str) -> date:
	if isinstance(value, str):
		return date.fromisoformat(value[:10])
	if isinstance(value, date):
		return value
	raise TypeError("fecha referencia inesperada.")


def _timestamp_firma_doc(doc: Any) -> datetime:
	fe = _fecha_emision_doc(doc)
	tv = getattr(doc, "posting_time", None)
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
			except ValueError as exc:
				frappe.throw(
					f"RUT en Customer {customer!r} (tax_id) invalido para DTE 33: {crow!r}. {exc!s}",
				)
	rzn = (customer_name or customer or "").strip() or "Receptor sin razon social"
	return Receptor(rut=rut, razon_social=rzn)


def _detalles_desde_items(items: list[Any], *, absolute_values: bool = False) -> list[DetalleFactura]:
	out: list[DetalleFactura] = []
	for it in items:
		raw_qty = Decimal(str(flt(getattr(it, "qty", 0) or 0)))
		qty = abs(raw_qty) if absolute_values else raw_qty
		if qty <= 0 and absolute_values:
			qty = Decimal("1")
		if qty <= 0:
			continue
		raw_rate = flt(getattr(it, "rate", None) or getattr(it, "net_rate", None) or 0)
		rate = Decimal(str(abs(raw_rate) if absolute_values else raw_rate))
		raw_net_amount = flt(getattr(it, "net_amount", 0) or 0)
		net_amount = int(round(abs(raw_net_amount) if absolute_values else raw_net_amount))
		raw_discount_pct = flt(getattr(it, "discount_percentage", 0) or 0)
		discount_pct = Decimal(str(abs(raw_discount_pct) if absolute_values else raw_discount_pct))
		discount_amount = None
		if discount_pct > 0:
			bruto = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			discount_amount = int((bruto * discount_pct / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
		raw_item_tax = flt(getattr(it, "item_tax_amount", 0) or 0)
		item_tax = int(round(abs(raw_item_tax) if absolute_values else raw_item_tax))
		out.append(
			DetalleFactura(
				nro_lin_det=len(out) + 1,
				nombre_item=(getattr(it, "item_name", None) or getattr(it, "item_code", None) or "Item")[:80],
				cantidad=qty,
				precio_item=rate,
				monto_item=net_amount,
				descuento_pct=discount_pct if discount_pct > 0 else None,
				descuento_monto=discount_amount,
				indica_exento=item_tax == 0,
				unidad_medida=_unidad_medida_item(it),
			)
		)
	return out


def _unidad_medida_item(it: Any) -> str | None:
	u = getattr(it, "uom", None) or getattr(it, "stock_uom", None)
	if not u:
		return None
	s = str(u).strip()
	return s[:4] if s else None


__all__ = ["sales_invoice_to_factura_data", "sales_invoice_to_nota_credito_debito_data"]
