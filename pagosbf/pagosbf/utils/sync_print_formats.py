# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Sincroniza Print Formats empaquetados en JSON hacia la BD del sitio."""

from __future__ import annotations

import frappe


def sync_pos_invoice_boleta_sii_print_format() -> str:
	"""Importa POS Invoice Boleta SII desde el JSON de la app (dev tras editar plantilla)."""
	frappe.reload_doc("pagosbf", "print_format", "pos_invoice_boleta_sii", force=True)
	frappe.clear_cache()
	return "POS Invoice Boleta SII synced from pagosbf package"


def sync_all_boleta_print_formats() -> str:
	"""Sincroniza print formats de boleta POS empaquetados en pagosbf."""
	for name in ("pos_invoice_boleta_sii", "pos_invoice_sii_boleta"):
		frappe.reload_doc("pagosbf", "print_format", name, force=True)
	frappe.clear_cache()
	return "pagosbf boleta print formats synced"

