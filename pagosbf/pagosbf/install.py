# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Hooks de instalacion pagosbf."""

from __future__ import annotations


def before_tests() -> None:
	"""No sembrar companies ERPNext fixture en sitios operativos Barriofarma."""
	from pagosbf.pagosbf.utils.test_site_company_guard import apply_test_site_guards

	apply_test_site_guards()
