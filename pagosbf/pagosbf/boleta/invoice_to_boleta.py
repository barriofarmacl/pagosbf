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
	lines = _detalles_desde_items(
		list(items_seq or []),
		tipo_41=tipo == constants.TIPO_DTE_BOLETA_EXENTA,
		total_iva_documento=int(round(iva_f)) if tipo == constants.TIPO_DTE_BOLETA_AFECTA else None,
	)
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
	if tv:
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
	# Sin posting_time (POS comun): no usar 12:00 fijo; desincroniza TED/DTE vs
	# TmstFirmaEnv del sobre (hora real) y Maullin puede rechazar el upload.
	from zoneinfo import ZoneInfo

	now = datetime.now(tz=ZoneInfo("America/Santiago")).replace(tzinfo=None)
	if now.date() == fe:
		return now.replace(microsecond=0)
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


def _allocate_iva_por_neto(nets: list[Decimal], total_iva: int) -> list[int]:
	"""Reparte IVA en pesos enteros entre lineas (mayor resto), suma = total_iva."""
	if total_iva <= 0 or not nets:
		return [0] * len(nets)
	den = sum(nets)
	if den <= 0:
		return [0] * len(nets)
	tiva = Decimal(total_iva)
	raw = [tiva * n / den for n in nets]
	fl = [int(r) for r in raw]
	rem = total_iva - sum(fl)
	order = sorted(range(len(nets)), key=lambda i: raw[i] - fl[i], reverse=True)
	for k in range(rem):
		fl[order[k]] += 1
	return fl


def _detalles_desde_items(
	items: list[Any],
	*,
	tipo_41: bool,
	total_iva_documento: int | None = None,
) -> tuple[DetalleBoleta, ...]:
	"""MontoItem boleta afecta (39) debe sumar MntTotal; POS Item no trae item_tax_amount."""
	rows: list[tuple[Any, Decimal, Decimal, Decimal]] = []
	for it in items:
		qty = Decimal(str(flt(it.qty) or 0))
		if qty <= 0:
			continue
		net = Decimal(str(flt(it.net_amount or 0)))
		tax = Decimal(str(flt(getattr(it, "item_tax_amount", None) or 0)))
		rows.append((it, qty, net, tax))

	out: list[DetalleBoleta] = []
	if tipo_41:
		for it, qty, net, _tax in rows:
			mrow = net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
			monto_i = int(mrow) if mrow == mrow.to_integral() else int(mrow.to_integral())
			prc = mrow / qty if qty else mrow
			out.append(
				DetalleBoleta(
					nro_lin_det=len(out) + 1,
					nombre_item=(it.item_name or it.item_code or "Item")[:100],
					cantidad=qty,
					precio_item=prc,
					monto_item=Decimal(monto_i),
					indica_exento=True,
					unidad_medida=_unidad_medida_item(it),
				)
			)
		return tuple(out)

	iva_doc = int(total_iva_documento or 0)
	explicit_sum = int(round(float(sum(r[3] for r in rows))))
	pool = max(0, iva_doc - explicit_sum)
	nets_sin_tax = [r[2] for r in rows if r[3] == 0]
	alloc = _allocate_iva_por_neto(nets_sin_tax, pool) if nets_sin_tax else []
	ai = 0
	for it, qty, net, tax in rows:
		if tax > 0:
			mrow = (net + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		else:
			iva_linea = Decimal(alloc[ai]) if ai < len(alloc) else Decimal(0)
			ai += 1
			mrow = (net + iva_linea).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
		monto_i = int(mrow) if mrow == mrow.to_integral() else int(mrow.to_integral())
		prc = mrow / qty if qty else mrow
		out.append(
			DetalleBoleta(
				nro_lin_det=len(out) + 1,
				nombre_item=(it.item_name or it.item_code or "Item")[:100],
				cantidad=qty,
				precio_item=prc,
				monto_item=Decimal(monto_i),
				indica_exento=False,
				unidad_medida=_unidad_medida_item(it),
			)
		)
	return tuple(out)


__all__ = ["pos_invoice_to_dte_data", "sales_invoice_to_dte_data"]
