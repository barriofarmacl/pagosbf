"""Material de firma desde `Certificado Digital` con cache en proceso (TTL)."""

from __future__ import annotations

import re
import time

import frappe
from cryptography.x509 import Certificate

from pagosbf.pagosbf.dte.xml_signer import XMLSignerError, load_pfx, SigningMaterial
from pagosbf.pagosbf.sii.rut import rut_para_dte_xml

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


_RUT_IN_TEXT = re.compile(r"(?<!\d)(\d{7,8}-[\dkK])(?!\d)", re.IGNORECASE)


def rut_from_certificate_subject(certificate: Certificate) -> str | None:
	"""Intenta obtener RUN/RUT del firmante desde el subject del X.509 (PFX SII).

	Muchos certificados chilenos exponen el RUN en ``serialNumber`` o dentro del
	``CN``. Retorna formato ``cuerpo-dv`` o ``None`` si no hay patron reconocible.
	"""
	parts = [str(a.value) for a in certificate.subject]
	for raw in parts:
		norm = raw.strip().replace(".", "")
		norm = re.sub(r"(?i)^RUN\s*", "", norm).strip()
		try:
			return rut_para_dte_xml(norm)
		except ValueError:
			pass
	blob = " ".join(parts)
	for m in _RUT_IN_TEXT.finditer(blob.replace(".", "")):
		try:
			return rut_para_dte_xml(m.group(1))
		except ValueError:
			continue
	return None


def resolve_digitador_rut(
	cert_name: str,
	material: SigningMaterial,
	rut_emisor: str,
) -> str:
	"""RUT del digitador para caratula SII y campos ``rutSender``/``dvSender`` en DTEUpload.

	1. Campo ``rut_firmante`` en ``Certificado Digital`` si esta informado.
	2. RUN inferido del subject del certificado (PFX).
	3. Fallback al RUT emisor (solo valido si el certificado es del mismo contribuyente).
	"""
	doc = frappe.get_doc("Certificado Digital", cert_name)
	manual = (doc.rut_firmante or "").strip()
	if manual:
		return rut_para_dte_xml(
			manual.replace(" ", "").replace(".", ""),
		)
	from_cert = rut_from_certificate_subject(material.certificate)
	if from_cert:
		return from_cert
	return rut_para_dte_xml(rut_emisor)


__all__ = [
	"get_signing_material",
	"get_signing_material_or_throw",
	"rut_from_certificate_subject",
	"resolve_digitador_rut",
]
