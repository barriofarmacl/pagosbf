"""Material de firma desde `Certificado Digital` con cache en proceso (TTL)."""

from __future__ import annotations

import time

import frappe

from pagosbf.pagosbf.dte.xml_signer import XMLSignerError, load_pfx, SigningMaterial

_TTL = 300.0
# name_cert -> (monotonic_ts, file_signature, material)
cache: dict[str, tuple[float, str, SigningMaterial]] = {}


def get_signing_material(cert_name: str) -> SigningMaterial:
	"""Carga PFX de `Certificado Digital` (cache ~300s por revision de archivo)."""
	fd = _file_doc_for_attach(cert_name)
	if not fd:
		frappe.throw(f"No se pudo localizar el archivo PFX de Certificado {cert_name!r}.")
	sig = f"{fd.name}|{getattr(fd, 'modified', '') or ''}"
	now = time.monotonic()
	if cert_name in cache:
		t0, s2, m = cache[cert_name]
		if s2 == sig and now - t0 < _TTL:
			return m
	try:
		pfx = fd.get_content()
		doc = frappe.get_doc("Certificado Digital", cert_name)
		pw = doc.get_password("password")
		mat = load_pfx(pfx, pw)
	except XMLSignerError as exc:
		frappe.throw(f"PFX invalido: {exc}")
	else:
		cache[cert_name] = (now, sig, mat)
		return mat


def _file_doc_for_attach(cert_name: str):
	doc = frappe.get_doc("Certificado Digital", cert_name)
	url = (doc.archivo_pfx or "").strip()
	if not url:
		return None
	fname = frappe.db.get_value("File", {"file_url": url}, "name")
	if not fname:
		return None
	return frappe.get_doc("File", fname)


def get_signing_material_or_throw(cert_name: str) -> SigningMaterial:
	if not cert_name:
		frappe.throw("Falta Certificado Digital en SII Configuration.")
	return get_signing_material(cert_name)


__all__ = ["get_signing_material", "get_signing_material_or_throw"]
