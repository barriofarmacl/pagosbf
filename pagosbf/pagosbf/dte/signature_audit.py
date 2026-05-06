"""Auditoria de firma XMLDSig en DTE Boleta (diagnostico local, sin Frappe).

Para depurar rechazos tipo **DTE-3-505** en cliente antes de contrastar con el SII:

1. **KeyValue vs X509**: el modulo en ``KeyValue/RSAKeyValue/Modulus`` debe coincidir con la clave publica del certificado DER en ``X509Certificate``.
2. **Verificacion XMLDSig**: ``signxml.XMLVerifier`` sobre el elemento ``<DTE>`` usando el certificado embebido (misma familia que ``xml_signer.verify_signature``).

Si (1) y (2) pasan aqui y el SII sigue en 505, el desacuerdo suele estar en reglas propias del motor SII (no en este arbol).
"""

from __future__ import annotations

from base64 import b64decode
import copy
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from lxml import etree
from signxml import XMLVerifier

from .constants import NS_SII_DTE, NS_XMLDSIG
from .xml_signer import _sii_verify_config

_DS_NS = {"ds": NS_XMLDSIG}


@dataclass(frozen=True)
class DteSignatureAudit:
	"""Resultado por un ``<DTE>`` firmado."""

	folio: str | None
	modulus_matches_x509: bool
	xmldsig_verifies: bool
	detail: str


def _int_from_dsig_b64(text: str | None) -> int | None:
	if not text:
		return None
	raw = b64decode("".join(text.split()))
	return int.from_bytes(raw, "big")


def _rsa_public_from_x509_certificate_element(cert_el: etree._Element | None) -> rsa.RSAPublicKey | None:
	if cert_el is None or not cert_el.text:
		return None
	try:
		der = b64decode("".join(cert_el.text.split()))
		cert = x509.load_der_x509_certificate(der)
	except Exception:
		return None
	pk = cert.public_key()
	return pk if isinstance(pk, rsa.RSAPublicKey) else None


def _certificate_pem_from_x509_certificate_element(cert_el: etree._Element | None) -> bytes | None:
	if cert_el is None or not cert_el.text:
		return None
	try:
		der = b64decode("".join(cert_el.text.split()))
		cert = x509.load_der_x509_certificate(der)
	except Exception:
		return None
	return cert.public_bytes(encoding=serialization.Encoding.PEM)


def keyinfo_pubkey_matches_embedded_x509(signature_el: etree._Element) -> bool:
	"""True si ``Modulus`` (KeyValue) == clave publica del ``X509Certificate`` embebido."""
	mod_el = signature_el.find(".//ds:RSAKeyValue/ds:Modulus", namespaces=_DS_NS)
	cert_el = signature_el.find(".//ds:X509Data/ds:X509Certificate", namespaces=_DS_NS)
	n_kv = _int_from_dsig_b64(mod_el.text if mod_el is not None else None)
	pub = _rsa_public_from_x509_certificate_element(cert_el)
	if n_kv is None or pub is None:
		return False
	return pub.public_numbers().n == n_kv


def _folio_from_dte(dte_el: etree._Element) -> str | None:
	folio_el = dte_el.find(
		f".//{{{NS_SII_DTE}}}Documento/{{{NS_SII_DTE}}}Encabezado/{{{NS_SII_DTE}}}IdDoc/{{{NS_SII_DTE}}}Folio"
	)
	if folio_el is None or not folio_el.text:
		return None
	return folio_el.text.strip()


def _first_signature_under_dte(dte_el: etree._Element) -> etree._Element | None:
	return dte_el.find(".//ds:Signature", namespaces=_DS_NS)


def audit_boleta_dte_element(dte_el: etree._Element) -> DteSignatureAudit:
	"""Audita el primer ``ds:Signature`` encontrado bajo ``dte_el``.

	La verificacion XMLDSig se hace sobre una copia **desconectada** del ``DTE``
	(sin padre en el arbol del ``EnvioBOLETA``). Con C14N inclusive, namespaces
	heredados desde ancestros fuera del ``DTE`` (p. ej. ``xmlns:xsi`` solo en la
	raiz del envio) alteran el digest respecto al XML con el que se firmo el
	documento en standalone; el SII valida el fragmento del documento con la
	misma referencia que verificar el ``DTE`` aislado.
	"""
	folio = _folio_from_dte(dte_el)
	sig = _first_signature_under_dte(dte_el)
	if sig is None:
		return DteSignatureAudit(
			folio=folio,
			modulus_matches_x509=False,
			xmldsig_verifies=False,
			detail="no hay ds:Signature descendiente del DTE",
		)

	mod_ok = keyinfo_pubkey_matches_embedded_x509(sig)
	cert_pem = _certificate_pem_from_x509_certificate_element(
		sig.find(".//ds:X509Data/ds:X509Certificate", namespaces=_DS_NS)
	)
	if cert_pem is None:
		return DteSignatureAudit(
			folio=folio,
			modulus_matches_x509=mod_ok,
			xmldsig_verifies=False,
			detail="X509Certificate ilegible o ausente",
		)

	cfg = _sii_verify_config()
	try:
		detached = copy.deepcopy(dte_el)
		XMLVerifier().verify(
			detached,
			x509_cert=cert_pem,
			expect_config=cfg,
			validate_schema=False,
		)
		xml_ok = True
		exc_text = ""
	except Exception as exc:
		xml_ok = False
		exc_text = f"{type(exc).__name__}: {exc}"

	parts: list[str] = []
	if not mod_ok:
		parts.append("Modulus KeyValue no coincide con X509")
	if not xml_ok:
		parts.append(f"XMLVerifier fallo ({exc_text})")
	detail = "; ".join(parts) if parts else "KeyInfo consistente y XMLDSig verifica localmente"

	return DteSignatureAudit(
		folio=folio,
		modulus_matches_x509=mod_ok,
		xmldsig_verifies=xml_ok,
		detail=detail,
	)


def iter_boleta_dte_elements(root: etree._Element) -> list[etree._Element]:
	"""Lista nodos ``<DTE>`` bajo una raiz ``EnvioBOLETA`` o un unico DTE."""
	tag = etree.QName(root.tag)
	if tag.localname == "DTE" and tag.namespace == NS_SII_DTE:
		return [root]
	return root.findall(f".//{{{NS_SII_DTE}}}DTE")


def audit_boleta_xml_bytes(xml_bytes: bytes) -> list[DteSignatureAudit]:
	"""Parsea XML y audita cada ``<DTE>``."""
	try:
		root = etree.fromstring(xml_bytes)
	except etree.XMLSyntaxError:
		return [
			DteSignatureAudit(
				folio=None,
				modulus_matches_x509=False,
				xmldsig_verifies=False,
				detail="XML mal formado",
			)
		]

	out: list[DteSignatureAudit] = []
	for dte in iter_boleta_dte_elements(root):
		out.append(audit_boleta_dte_element(dte))
	return out


__all__ = [
	"DteSignatureAudit",
	"audit_boleta_dte_element",
	"audit_boleta_xml_bytes",
	"iter_boleta_dte_elements",
	"keyinfo_pubkey_matches_embedded_x509",
]
