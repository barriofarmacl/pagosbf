"""xml_signer: firma XMLDSig de DTE Boleta y sobres EnvioBOLETA.

``EnvioBOLETA_v11.xsd`` / ``BOLETADefType``: bajo ``<DTE>`` va ``<Documento>`` y luego
``<ds:Signature>`` como hermano. Con signxml **enveloped** hay que pasar la raiz ``<DTE>`` y
``reference_uri`` = ``Id`` del ``Documento``: la libreria resuelve la referencia al ``Documento``,
pone la firma como hijo del ``DTE`` (no dentro del ``Documento``), y el digest usa la cadena de
Transforms del perfil SII sobre ese fragmento.

Sobre ``EnvioBOLETA`` / semilla ``getToken``: enveloped RSA-SHA1; el sobre DTE/DTEUpload sigue con
prefijo ``ds:``. El XML de ``getToken`` para AUTAUTOM usa **sin** prefijo ``ds:`` y ``xmlns`` en
``Signature`` (alineado a manuales / xmlsec del SII).

Perfil ``xmldsignature_v10.xsd`` (portal) para Reference del DTE:
- ``CanonicalizationMethod`` = ``REC-xml-c14n-20010315``.
- Una sola ``Transform`` envelopeada (sin segundo Transform ``exc-c14n``).
- ``KeyInfo``: ``KeyValue`` antes de ``X509Data``.

Uso tipico::

    signed_dte = sign_dte(dte_bytes, material, reference_uri="BOL39-1")
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509 import Certificate
from lxml import etree
from signxml import (
	CanonicalizationMethod,
	DigestAlgorithm,
	SignatureConstructionMethod,
	SignatureMethod,
	XMLSigner,
	XMLVerifier,
)
from signxml.util import namespaces as signxml_namespaces
from signxml.verifier import SignatureConfiguration

from .constants import NS_SII_DTE, SII_XML_ENCODING
from .sii_xml_bytes import (
	finalize_sii_xml_bytes,
	inject_consumo_folios_xsi_schema_declaration,
	inject_envio_boleta_xsi_schema_declaration,
	inject_envio_dte_xsi_schema_declaration,
	inject_libro_cv_xsi_schema_declaration,
)


class XMLSignerError(Exception):
	"""Error en carga PKCS#12, firma o verificacion XMLDSig."""


def inject_dte_xsi_namespace(data: bytes) -> bytes:
	"""Declara ``xmlns:xsi`` en la raiz ``<DTE>`` antes de firmar.

	El sobre ``EnvioBOLETA`` necesita ``xsi:schemaLocation`` para no caer en
	``SCH-00001``. Con canonicalizacion inclusiva, ese ``xmlns:xsi`` ancestro
	cambia el digest del ``Documento`` si el DTE se firmo sin ese namespace en
	contexto. Declararlo en el DTE antes de firmar mantiene estable la firma al
	embeberlo dentro del sobre con ``schemaLocation``.
	"""
	target = b'<DTE xmlns="http://www.sii.cl/SiiDte" version="1.0">'
	replacement = (
		b'<DTE xmlns="http://www.sii.cl/SiiDte" '
		b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="1.0">'
	)
	if b"xmlns:xsi=" in data[:500]:
		return data
	return data.replace(target, replacement, 1)


def _isolate_documento_subtree_for_digest(dte_root: etree._Element, documento_id: str) -> None:
	"""Desconecta el ``Documento`` del contexto de namespaces del padre antes de firmar.

	``signxml`` calcula el digest del payload sin round-trip previo; el verificador (local y
	posiblemente el SII) serializa el subarbol referenciado y reparsed antes de C14N. En arboles
	lxml eso puede cambiar declaraciones ``xmlns`` vacias en descendientes y producir digest distinto.
	Sustituimos el nodo por una copia parseada desde sus propios bytes (misma idea que el verificador).
	"""
	doc_tag = f"{{{NS_SII_DTE}}}Documento"
	for doc in dte_root.iterdescendants(tag=doc_tag):
		rid = doc.get("ID") or doc.get("Id") or doc.get("id")
		if rid != documento_id:
			continue
		parent = doc.getparent()
		if parent is None:
			return
		idx = parent.index(doc)
		blob = etree.tostring(doc, encoding="utf-8", xml_declaration=False)
		isolated = etree.fromstring(blob, parser=etree.XMLParser(resolve_entities=False))
		parent[idx] = isolated
		return
	raise XMLSignerError(f"No hay <Documento> con ID={documento_id!r} bajo <DTE>")


@dataclass(frozen=True)
class SigningMaterial:
	"""Material criptografico extraido del PFX listo para firmar."""

	private_key: object  # RSAPrivateKey; tipado opaco para no acoplar al API interno
	certificate: Certificate
	chain: tuple[Certificate, ...]

	@property
	def cert_pem(self) -> bytes:
		from cryptography.hazmat.primitives.serialization import Encoding

		return self.certificate.public_bytes(Encoding.PEM)


def load_pfx(pfx_bytes: bytes, password: str | None) -> SigningMaterial:
	"""Carga un PKCS#12 con `cryptography` y retorna `SigningMaterial`.

	Raises:
	    XMLSignerError: si el archivo no es un PKCS#12 valido o la password es
	        incorrecta.
	"""
	try:
		pwd = password.encode("utf-8") if password else None
		key, cert, additional = pkcs12.load_key_and_certificates(pfx_bytes, pwd)
	except Exception as exc:  # noqa: BLE001 -- cryptography eleva varias excepciones
		raise XMLSignerError(f"No se pudo cargar PKCS#12: {exc}") from exc

	if key is None or cert is None:
		raise XMLSignerError("PKCS#12 no contiene clave privada o certificado.")

	return SigningMaterial(
		private_key=key,
		certificate=cert,
		chain=tuple(additional or ()),
	)


class _SiiXMLSigner(XMLSigner):
	"""XMLSigner que autoriza explicitamente RSA-SHA1 requerido por SII boletas.

	signxml >= 4 bloquea por defecto algoritmos basados en SHA1. El SII exige
	`rsa-sha1` y `sha1` en Boleta Electronica (Formato DTE v2.3); estos valores
	no son negociables y la mitigacion de seguridad correspondiente es aplicar
	controles fuera de banda (TLS, certificados confiables, perimetro).
	"""

	def check_deprecated_methods(self):  # noqa: D401 - override
		# Suppressed intentionally: SII impone SHA1 en DTE 39/41.
		return


def _signer_envio_y_semilla() -> XMLSigner:
	"""Firma enveloped RSA-SHA1 con C14N XML 1.0 (`xmldsignature_v10.xsd`)."""
	return _SiiXMLSigner(
		method=SignatureConstructionMethod.enveloped,
		signature_algorithm=SignatureMethod.RSA_SHA1,
		digest_algorithm=DigestAlgorithm.SHA1,
		c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
	)


def _signer_sii_get_token() -> XMLSigner:
	"""Igual que envio/semilla pero XMLDSig sin prefijo ``ds:`` (manual AUTAUTOM / xmlsec SII)."""
	s = _SiiXMLSigner(
		method=SignatureConstructionMethod.enveloped,
		signature_algorithm=SignatureMethod.RSA_SHA1,
		digest_algorithm=DigestAlgorithm.SHA1,
		c14n_algorithm=CanonicalizationMethod.CANONICAL_XML_1_0,
	)
	s.namespaces = {None: signxml_namespaces.ds}
	return s


def _sign_kw_envio() -> dict:
	"""Reference: solo Transform enveloped; KeyInfo con KeyValue + X509Data."""
	return {
		"exclude_c14n_transform_element": True,
		"always_add_key_value": True,
	}


def _sii_verify_config() -> SignatureConfiguration:
	"""SignatureConfiguration que permite RSA-SHA1/SHA1 en verificacion (SII).

	Sin Transform de C14N en Reference, signxml verifica el digest usando
	``default_reference_c14n_method``; debe coincidir con la C14N usada al firmar.
	"""
	return SignatureConfiguration(
		signature_methods=frozenset({SignatureMethod.RSA_SHA1, SignatureMethod.RSA_SHA256}),
		digest_algorithms=frozenset({DigestAlgorithm.SHA1, DigestAlgorithm.SHA256}),
		# Solo usado cuando Reference no incluye Transform de C14N (sobre / semilla).
		default_reference_c14n_method=CanonicalizationMethod.CANONICAL_XML_1_0,
	)


def sign_dte(
	dte_xml_bytes: bytes,
	material: SigningMaterial,
	reference_uri: str,
) -> bytes:
	"""Firma XMLDSig el ``Documento`` (via ``reference_uri``) y deja ``Signature`` hijo de ``DTE``.

	Requisito: ``dte_xml_bytes`` debe ser la raiz ``<DTE>``. La firma **no** va dentro del
	``Documento``; signxml enveloped + referencia explicita adjunta ``ds:Signature`` al ``DTE``.

	Args:
	    dte_xml_bytes: XML del DTE con TED ya embebido (output de `xml_builder.insert_ted`).
	    material: clave y certificado cargados desde PFX.
	    reference_uri: el ID del `<Documento>`, por ejemplo `"BOL39-1"` (sin `#`).

	Returns:
	    XML firmado en encoding ISO-8859-1.

	Raises:
	    XMLSignerError: si la firma falla por clave, cert o algoritmo.
	"""
	try:
		root = etree.fromstring(dte_xml_bytes)
	except etree.XMLSyntaxError as exc:
		raise XMLSignerError(f"DTE XML mal formado: {exc}") from exc

	_isolate_documento_subtree_for_digest(root, reference_uri)

	try:
		signed = _signer_envio_y_semilla().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=reference_uri,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma XMLDSig fallo: {exc}") from exc

	return finalize_sii_xml_bytes(
		etree.tostring(
			signed,
			encoding=SII_XML_ENCODING,
			xml_declaration=True,
			standalone=None,
		)
	)


def sign_envio_boleta(
	envio_xml_bytes: bytes,
	material: SigningMaterial,
	reference_uri: str = "",
	*,
	inject_portal_schema_location: bool = True,
) -> bytes:
	"""Firma el sobre `<EnvioBOLETA>` enveloped bajo `<SetDTE ID="...">`.

	Se firma con el mismo certificado que los DTE individuales. El SII valida
	que el RUT del firmante del sobre coincida con `Caratula/RutEnvia`.

	Args:
		inject_portal_schema_location: Si True (default), declara en la raiz
		    ``xmlns:xsi`` y ``xsi:schemaLocation`` **antes** de parsear y firmar
		    (evita SCH-00001 en carga manual). Debe ser pre-firma: con C14N
		    inclusive el digest de ``#SetDte1`` incluye namespace nodes de la
		    raiz; inyectarlo **despues** de firmar invalida el sobre (RFR Error
		    en Firma). El payload desde ``<SetDTE`` sigue igual en bytes salvo
		    normalizacion de ``lxml`` al serializar el arbol completo.
	"""
	data = envio_xml_bytes
	if inject_portal_schema_location:
		data = inject_envio_boleta_xsi_schema_declaration(data)
	try:
		root = etree.fromstring(data)
	except etree.XMLSyntaxError as exc:
		raise XMLSignerError(f"EnvioBOLETA XML mal formado: {exc}") from exc

	try:
		signed = _signer_envio_y_semilla().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=reference_uri,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma XMLDSig del sobre fallo: {exc}") from exc

	out = etree.tostring(
		signed,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
	)
	out = finalize_sii_xml_bytes(out)
	return out


def sign_envio_dte(
	envio_xml_bytes: bytes,
	material: SigningMaterial,
	reference_uri: str = "",
	*,
	inject_portal_schema_location: bool = True,
) -> bytes:
	"""Firma el sobre ``<EnvioDTE>`` enveloped bajo ``<SetDTE ID=...>``.

	Mismo perfil XMLDSig que boleta; ``Caratula/RutEnvia`` debe coincidir con el
	firmante del certificado (PFX).
	"""
	data = envio_xml_bytes
	if inject_portal_schema_location:
		data = inject_envio_dte_xsi_schema_declaration(data)
	try:
		root = etree.fromstring(data)
	except etree.XMLSyntaxError as exc:
		raise XMLSignerError(f"EnvioDTE XML mal formado: {exc}") from exc

	try:
		signed = _signer_envio_y_semilla().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=reference_uri,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma XMLDSig del sobre EnvioDTE fallo: {exc}") from exc

	out = etree.tostring(
		signed,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
	)
	out = finalize_sii_xml_bytes(out)
	return out


def sign_consumo_folios(
	consumo_xml_bytes: bytes,
	material: SigningMaterial,
	reference_uri: str = "RCOF_01",
	*,
	inject_portal_schema_location: bool = True,
) -> bytes:
	"""Firma ``ConsumoFolios`` enveloped con referencia al ``DocumentoConsumoFolios``.

	El XSD exige ``ds:Signature`` como segundo hijo de ``ConsumoFolios``;
	``signxml`` adjunta la firma al final del elemento raiz (orden Documento + Signature).

	Args:
	    consumo_xml_bytes: XML sin firma (salida de ``build_consumo_folios_draft_bytes``).
	    reference_uri: valor del atributo ``ID`` del ``DocumentoConsumoFolios``.
	    inject_portal_schema_location: declara ``xmlns:xsi`` y ``xsi:schemaLocation`` en la
	        raiz **antes** de parsear (misma regla que ``sign_envio_boleta``).
	"""
	data = consumo_xml_bytes
	if inject_portal_schema_location:
		data = inject_consumo_folios_xsi_schema_declaration(data)
	try:
		root = etree.fromstring(data)
	except etree.XMLSyntaxError as exc:
		raise XMLSignerError(f"ConsumoFolios XML mal formado: {exc}") from exc

	try:
		signed = _signer_envio_y_semilla().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=reference_uri,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma XMLDSig ConsumoFolios fallo: {exc}") from exc

	out = etree.tostring(
		signed,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
	)
	out = finalize_sii_xml_bytes(out)
	return out


def sign_libro_compra_venta(
	libro_xml_bytes: bytes,
	material: SigningMaterial,
	reference_uri: str = "LIBROVENTA",
	*,
	inject_portal_schema_location: bool = True,
) -> bytes:
	"""Firma ``LibroCompraVenta`` enveloped con referencia al nodo ``EnvioLibro``."""
	data = libro_xml_bytes
	if inject_portal_schema_location:
		data = inject_libro_cv_xsi_schema_declaration(data)
	try:
		root = etree.fromstring(data)
	except etree.XMLSyntaxError as exc:
		raise XMLSignerError(f"LibroCompraVenta XML mal formado: {exc}") from exc

	try:
		signed = _signer_envio_y_semilla().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=reference_uri,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma XMLDSig LibroCompraVenta fallo: {exc}") from exc

	out = etree.tostring(
		signed,
		encoding=SII_XML_ENCODING,
		xml_declaration=True,
		standalone=None,
	)
	out = finalize_sii_xml_bytes(out)
	return out


def verify_signature(signed_xml_bytes: bytes, material: SigningMaterial | None = None) -> bool:
	"""Verifica firma XMLDSig contra el certificado del `SigningMaterial`.

	Si `material` es `None`, se usa el certificado embebido en `<KeyInfo>`.
	Util para tests unitarios (round-trip sign -> verify).
	"""
	try:
		tree = etree.fromstring(signed_xml_bytes)
	except etree.XMLSyntaxError:
		return False

	try:
		config = _sii_verify_config()
		if material is not None:
			XMLVerifier().verify(tree, x509_cert=material.cert_pem, expect_config=config)
		else:
			XMLVerifier().verify(tree, expect_config=config)
		return True
	except Exception:  # noqa: BLE001 -- cualquier fallo = no verifica
		return False


def sign_sii_get_token_envelope(semilla: str, material: SigningMaterial) -> str:
	"""Arma el XML `getToken` con firma XMLDSig para `GetTokenFromSeed`.

	Perfil del manual SII / AUTAUTOM (cap. 8): raíz ``getToken``, hijo ``item`` con
	``Semilla``, y ``Signature`` como **hermano** de ``item`` (mismo nivel bajo
	``getToken``), no dentro de ``item``. ``signxml`` con ``reference_uri=None``
	sobre ``getToken`` reproduce ese layout (Reference sin URI con enveloped).

	El string se envía en ``pszXml`` a SOAP (UTF-8).
	"""
	root = etree.Element("getToken")
	item = etree.SubElement(root, "item")
	sem_el = etree.SubElement(item, "Semilla")
	sem_el.text = semilla
	try:
		signed_root = _signer_sii_get_token().sign(
			root,
			key=material.private_key,
			cert=material.cert_pem,
			reference_uri=None,
			**_sign_kw_envio(),
		)
	except Exception as exc:  # noqa: BLE001
		raise XMLSignerError(f"Firma de semilla (getToken) fallo: {exc}") from exc
	return etree.tostring(
		signed_root,
		encoding="utf-8",
		xml_declaration=True,
		pretty_print=False,
	).decode("utf-8")


__all__ = [
	"SigningMaterial",
	"XMLSignerError",
	"inject_dte_xsi_namespace",
	"load_pfx",
	"sign_dte",
	"sign_envio_boleta",
	"sign_envio_dte",
	"sign_consumo_folios",
	"sign_libro_compra_venta",
	"sign_sii_get_token_envelope",
	"verify_signature",
]
