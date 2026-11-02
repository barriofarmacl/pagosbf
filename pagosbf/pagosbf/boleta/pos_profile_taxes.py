# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Copia la plantilla de impuestos del POS Profile al POS Invoice si falta IVA.

Causa (E2 / whiteboard #69): ERPNext `AccountsController.set_taxes()` solo llama
`append_taxes_from_master` cuando `is_new()`. El POS de mostrador guarda el
documento y deja `taxes` vacio; `pagosbf` interpreta IVA=0 como DTE 41.

No forkea el POS: reutiliza `append_taxes_from_master` del controller ERPNext.
"""

from __future__ import annotations

from typing import Any

import frappe


def pos_invoice_needs_profile_taxes(doc: Any, profile_taxes_and_charges: str | None) -> bool:
	"""True si el documento es POS Invoice afecta-esperada sin filas de impuesto."""
	if getattr(doc, "doctype", None) != "POS Invoice":
		return False
	if int(getattr(doc, "is_return", 0) or 0):
		return False
	taxes = doc.get("taxes") if hasattr(doc, "get") else getattr(doc, "taxes", None)
	if taxes:
		return False
	if not (getattr(doc, "pos_profile", None) or "").strip():
		return False
	return bool((profile_taxes_and_charges or "").strip())


def ensure_pos_profile_taxes(doc: Any) -> bool:
	"""Aplica `POS Profile.taxes_and_charges` al POS Invoice si `taxes` esta vacio.

	No calcula totales: `validate` de ERPNext llama `calculate_taxes_and_totals`.
	Returns True si se copiaron filas desde la plantilla.
	"""
	profile = (getattr(doc, "pos_profile", None) or "").strip()
	tmpl = None
	if profile:
		tmpl = frappe.db.get_value("POS Profile", profile, "taxes_and_charges")
	if not pos_invoice_needs_profile_taxes(doc, tmpl):
		return False
	doc.taxes_and_charges = tmpl
	doc.append_taxes_from_master()
	return True


def ensure_pos_profile_taxes_event(doc: Any, _method: str | None = None) -> None:
	"""Hook `POS Invoice.before_validate` (hooks.py)."""
	ensure_pos_profile_taxes(doc)


def false_exenta_if_profile_has_iva_reason(
	doc: Any,
	profile_taxes_and_charges: str | None,
) -> str | None:
	"""Glosa si IVA=0 pero el POS Profile tiene plantilla (falso DTE 41).

	None = no bloquear (exenta legitima o ya afecta).
	"""
	from frappe.utils import flt

	if getattr(doc, "doctype", None) != "POS Invoice":
		return None
	# Misma regla que emision._tipo_preliminar: IVA redondeado > 0 => afecta (39).
	if int(round(flt(getattr(doc, "total_taxes_and_charges", 0) or 0))) > 0:
		return None
	tmpl = (profile_taxes_and_charges or "").strip()
	if not tmpl:
		return None
	name = getattr(doc, "name", None) or "(sin name)"
	profile = (getattr(doc, "pos_profile", None) or "").strip() or "(sin perfil)"
	iva = flt(getattr(doc, "total_taxes_and_charges", 0) or 0)
	return (
		f"POS Invoice {name} tiene total_taxes_and_charges={iva} (TipoDTE 41) "
		f"pero POS Profile {profile} usa plantilla {tmpl}. "
		f"No se emite DTE 41: aplique IVA en caja o quite la plantilla del perfil si la venta es exenta."
	)
