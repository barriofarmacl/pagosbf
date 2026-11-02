# -*- coding: utf-8 -*-
# Copyright (c) 2026, Barrio Farma and Contributors
# See license.txt

"""
Evita que el preload de Frappe/ERPNext (`make_test_records("Company")`) siembre
companies de `erpnext/setup/doctype/company/test_records.json` (Wind Power LLC,
Best Test, etc.) en sitios operativos con Barriofarma.

Origen: Frappe v16 `compat_preload_test_records_upfront` + dependencias de
IntegrationTestCase llaman `make_test_records`, que sincroniza todo el JSON.
"""

from __future__ import annotations

import frappe

PRODUCTION_COMPANIES = frozenset({"Barriofarma"})

# Doctypes cuyo preload completo no debe correr en sitio Barriofarma (Issue #58 / verify 16.53).
SKIP_TEST_RECORD_DOCTYPES_ON_OPERATIONAL_SITE = frozenset({"Company"})

_MAKE_TEST_RECORDS_PATCHED = False
_CLEANUP_PATCHED = False


def is_barriofarma_operational_site() -> bool:
	"""Sitio clon/UAT/DEV con company productiva Barriofarma."""
	if not frappe.db:
		return False
	return bool(frappe.db.exists("Company", "Barriofarma"))


def get_non_production_companies():
	"""Companies que no son la company operativa del sitio."""
	if not frappe.db:
		return []
	names = frappe.get_all("Company", pluck="name")
	return [n for n in names if n not in PRODUCTION_COMPANIES]


def cleanup_non_production_companies(max_passes: int = 8) -> list[str]:
	"""
	Elimina companies de fixture ERPNext. Reintenta por jerarquía parent/child.
	Returns: nombres eliminados.
	"""
	if not is_barriofarma_operational_site():
		return []

	deleted: list[str] = []
	to_remove = get_non_production_companies()
	if not to_remove:
		return deleted

	for _ in range(max_passes):
		if not to_remove:
			break
		progress = False
		for name in list(to_remove):
			try:
				frappe.delete_doc("Company", name, force=True, ignore_permissions=True)
				deleted.append(name)
				to_remove.remove(name)
				progress = True
			except Exception:
				frappe.db.rollback()
		if progress:
			frappe.db.commit()
		else:
			break

	if deleted:
		frappe.db.commit()
	return deleted


def _should_skip_test_records(doctype: str) -> bool:
	return (
		is_barriofarma_operational_site()
		and doctype in SKIP_TEST_RECORD_DOCTYPES_ON_OPERATIONAL_SITE
	)


def patch_make_test_records_company_guard():
	"""No cargar test_records.json de Company en sitio Barriofarma."""
	global _MAKE_TEST_RECORDS_PATCHED
	if _MAKE_TEST_RECORDS_PATCHED:
		return

	import frappe.tests.utils as tests_utils
	import frappe.tests.utils.generators as generators

	original = generators.make_test_records

	def guarded_make_test_records(doctype, force=False, commit=False):
		if _should_skip_test_records(doctype):
			if doctype not in frappe.local.test_objects:
				frappe.local.test_objects[doctype] = []
			return []
		return original(doctype, force=force, commit=commit)

	guarded_make_test_records._barriofarma_company_guard = True
	generators.make_test_records = guarded_make_test_records
	tests_utils.make_test_records = guarded_make_test_records
	_MAKE_TEST_RECORDS_PATCHED = True


def patch_compat_preload_skip_company():
	"""No disparar make_test_records(Company) desde test_dependencies en preload."""
	import json
	import os
	import re

	import frappe.deprecation_dumpster as dd
	from frappe.tests.utils import make_test_records

	if getattr(dd.compat_preload_test_records_upfront, "_barriofarma_company_skip", False):
		return

	original = dd.compat_preload_test_records_upfront

	def _preload(candidates):
		for module, path, filename in candidates:
			if hasattr(module, "test_dependencies"):
				for doctype in module.test_dependencies:
					if _should_skip_test_records(doctype):
						continue
					make_test_records(doctype, commit=True)
			if hasattr(module, "EXTRA_TEST_RECORD_DEPENDENCIES"):
				for doctype in module.EXTRA_TEST_RECORD_DEPENDENCIES:
					if _should_skip_test_records(doctype):
						continue
					make_test_records(doctype, commit=True)

			if os.path.basename(os.path.dirname(path)) != "doctype":
				continue

			test_record_filename = re.sub("^test_", "", filename).replace(".py", ".json")
			test_record_file_path = os.path.join(path, test_record_filename)
			if not os.path.exists(test_record_file_path):
				continue

			with open(test_record_file_path) as f:
				payload = json.load(f)
			if isinstance(payload, list):
				continue
			if payload.get("doctype") == "DocType":
				continue
			doctype = payload.get("name")
			if doctype and _should_skip_test_records(doctype):
				continue
			if doctype:
				make_test_records(doctype, commit=True)

	_preload._barriofarma_company_skip = True
	dd.compat_preload_test_records_upfront = _preload


def patch_test_run_cleanup():
	"""Tras cada `bench run-tests`, quitar companies ERPNext si quedaron."""
	global _CLEANUP_PATCHED
	if _CLEANUP_PATCHED:
		return

	import frappe.testing.environment as env

	original = env._cleanup_after_tests

	def wrapped_cleanup():
		try:
			original()
		finally:
			if frappe.db and is_barriofarma_operational_site():
				try:
					cleanup_non_production_companies()
				except Exception:
					frappe.logger().exception(
						"BarrioFarma: cleanup companies tras tests falló"
					)

	wrapped_cleanup._barriofarma_wrapped = True
	env._cleanup_after_tests = wrapped_cleanup
	_CLEANUP_PATCHED = True


def apply_test_site_guards():
	"""Registrar parches idempotentes (before_tests)."""
	patch_make_test_records_company_guard()
	patch_compat_preload_skip_company()
	patch_test_run_cleanup()
