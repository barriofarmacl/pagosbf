"""ted_generator: construye el Timbre Electronico (TED) firmado con clave del CAF.

Spec pagosbf-sii-boleta R6. Diferencia critica respecto a `xml_signer`:

- El TED se firma con la **clave privada del CAF** (extraida del XML CAF
  entregado por el SII), NO con el certificado digital PFX del emisor.
- Algoritmo: `SHA1withRSA`, PKCS#1 v1.5, output binario codificado en base64
  colocado dentro de `<FRMT algoritmo="SHA1withRSA">`.
- La cadena firmada es el bloque `<DD>` canonicalizado tal cual queda en el
  DTE final; cualquier diferencia de whitespace invalida la firma.

Estructura del TED:

```xml
<TED version="1.0">
  <DD>
    <RE>76000000-0</RE>
    <TD>39</TD>
    <F>1</F>
    <FE>2026-04-24</FE>
    <RR>66666666-6</RR>
    <RSR>Cliente</RSR>
    <MNT>1190</MNT>
    <IT1>Producto 1</IT1>
    <CAF version="1.0">...el bloque exacto del CAF SII...</CAF>
    <TSTED>2026-04-24T12:00:00</TSTED>
  </DD>
  <FRMT algoritmo="SHA1withRSA">base64...</FRMT>
</TED>
```
"""

from __future__ import annotations

import base64
from datetime import datetime

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from lxml import etree

from .constants import NS_SII_DTE
from .types import CAFData
from .xml_builder import DDData


class TEDGenerationError(Exception):
	"""Error al generar o firmar el TED."""


def build_signed_ted(
	dd_data: DDData,
	caf: CAFData,
	timestamp: datetime,
) -> etree._Element:
	"""Retorna `<TED>` completo: DD + CAF + TSTED firmados con la clave del CAF.

	Raises:
	    TEDGenerationError: si tipo_dte o rango del CAF no concuerdan con el
	        folio solicitado, o si la firma RSA falla.
	"""
	if dd_data.tipo_dte != caf.tipo_dte:
		raise TEDGenerationError(
			f"tipo_dte del DTE ({dd_data.tipo_dte}) no coincide con el CAF ({caf.tipo_dte})"
		)
	if not (caf.rango_desde <= dd_data.folio <= caf.rango_hasta):
		raise TEDGenerationError(
			f"folio {dd_data.folio} fuera del rango CAF [{caf.rango_desde}, {caf.rango_hasta}]"
		)

	ted = etree.Element("TED", version="1.0")  # TED es sin namespace (se hereda del DTE)
	dd = etree.SubElement(ted, "DD")

	etree.SubElement(dd, "RE").text = dd_data.rut_emisor
	etree.SubElement(dd, "TD").text = str(dd_data.tipo_dte)
	etree.SubElement(dd, "F").text = str(dd_data.folio)
	etree.SubElement(dd, "FE").text = dd_data.fecha_emision
	etree.SubElement(dd, "RR").text = dd_data.rut_receptor
	etree.SubElement(dd, "RSR").text = dd_data.razon_social_receptor or "Sin nombre"
	etree.SubElement(dd, "MNT").text = str(dd_data.monto_total)
	etree.SubElement(dd, "IT1").text = dd_data.descripcion_item_1 or "Sin descripcion"

	# CAF: mismo contenido semantico que entrega el SII, compactado (sin textos solo-blanco).
	try:
		caf_fragment = etree.fromstring(caf.caf_xml_element_str.encode("ISO-8859-1"))
	except etree.XMLSyntaxError as exc:
		raise TEDGenerationError(f"Bloque CAF del XML no parsea: {exc}") from exc
	dd.append(caf_fragment)

	etree.SubElement(dd, "TSTED").text = timestamp.strftime("%Y-%m-%dT%H:%M:%S")

	signature_b64 = _sign_dd(dd, caf.rsa_private_key_pem)
	frmt = etree.SubElement(ted, "FRMT", algoritmo="SHA1withRSA")
	frmt.text = signature_b64

	return ted


def _sign_dd(dd_element: etree._Element, rsa_private_key_pem: bytes) -> str:
	"""Firma el DD canonicalizado con SHA1withRSA y retorna base64.

	El SII define la cadena a firmar como el bloque `<DD>` serializado con
	`etree.tostring(method='c14n')`. Probado con la exclusiva C14N para
	compatibilidad con el set de certificacion.
	"""
	try:
		private_key = serialization.load_pem_private_key(rsa_private_key_pem, password=None)
	except Exception as exc:  # noqa: BLE001 -- superficie de errores cryptography heterogenea
		raise TEDGenerationError(f"No se pudo cargar la clave privada del CAF: {exc}") from exc

	if not isinstance(private_key, rsa.RSAPrivateKey):
		raise TEDGenerationError("La clave del CAF no es RSA.")

	canonical = etree.tostring(dd_element, method="c14n", exclusive=True, with_comments=False)
	signature = private_key.sign(canonical, padding.PKCS1v15(), hashes.SHA1())
	return base64.b64encode(signature).decode("ascii")


def serialize_ted_for_pdf417(ted: etree._Element) -> str:
	"""Serializa `<TED>` como string listo para codificar en PDF417 en el print.

	Se usa en `printing/` (fuera de scope de este change) para imprimir el
	timbre en la boleta. Lo exponemos aqui para no duplicar la canonicalizacion.
	"""
	return etree.tostring(ted, method="c14n", exclusive=True, with_comments=False).decode("ISO-8859-1", errors="replace")


__all__ = ["TEDGenerationError", "build_signed_ted", "serialize_ted_for_pdf417"]
