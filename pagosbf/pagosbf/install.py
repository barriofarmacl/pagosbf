# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Hooks de instalacion/migracion pagosbf."""

from __future__ import annotations


def after_migrate() -> None:
	"""Print formats Jinja viven en JSON; forzar sync a BD tras migrate."""
	from pagosbf.pagosbf.utils.sync_print_formats import sync_all_boleta_print_formats

	sync_all_boleta_print_formats()
