"""Constantes SII Chile para DTE (Boleta, factura y documentos asociados).

Referencias:
- https://www.sii.cl/servicios_online/1039-formato_xml-1184.html
- "Formato Documentos Tributarios Electronicos" v2.3
- "Descripcion servicios web DTE" v1.4
"""

from __future__ import annotations

from pathlib import Path

# Encoding obligatorio del XML DTE segun SII (latin-1, NO UTF-8).
SII_XML_ENCODING = "ISO-8859-1"

# Namespaces oficiales.
NS_SII_DTE = "http://www.sii.cl/SiiDte"
NS_XMLDSIG = "http://www.w3.org/2000/09/xmldsig#"
NS_XML_SCHEMA_INSTANCE = "http://www.w3.org/2001/XMLSchema-instance"

# Portal SII / validadores externos suelen exigir `xsi:schemaLocation` en la raiz del sobre
# para reconocer el XSD (evita SCH-00001 Invalid Schema Name en carga manual).
ENVIO_BOLETA_SCHEMA_LOCATION = f"{NS_SII_DTE} EnvioBOLETA_v11.xsd"

# Sobre estandar DTE (factura 33 y demas) — `EnvioDTE_v10.xsd` en `public/xsd/factura/`.
ENVIO_DTE_SCHEMA_LOCATION = f"{NS_SII_DTE} EnvioDTE_v10.xsd"

# RCOF (Consumo de Folios) — schema oficial SII `ConsumoFolio_v10.xsd`.
CONSUMO_FOLIOS_SCHEMA_LOCATION = f"{NS_SII_DTE} ConsumoFolio_v10.xsd"

# IECV (Libro de Compras y Ventas) — schema oficial `LibroCV_v10.xsd`.
LIBRO_CV_SCHEMA_LOCATION = f"{NS_SII_DTE} LibroCV_v10.xsd"

# Algoritmos obligatorios (SII rechaza SHA-256 en boletas v2.3).
SIGN_ALGORITHM = "rsa-sha1"
DIGEST_ALGORITHM = "sha1"
CANONICALIZATION_METHOD = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"

# Tipos DTE soportados por este modulo.
TIPO_DTE_BOLETA_AFECTA = 39
TIPO_DTE_BOLETA_EXENTA = 41
# Factura / NC / ND electronicas (XSD `DTE_v10.xsd`; set certificacion basico SII).
TIPO_DTE_FACTURA_ELECTRONICA = 33
TIPO_DTE_NOTA_CREDITO_ELECTRONICA = 61
TIPO_DTE_NOTA_DEBITO_ELECTRONICA = 56
VALID_TIPOS_DTE = frozenset({TIPO_DTE_BOLETA_AFECTA, TIPO_DTE_BOLETA_EXENTA})
# Alcance certificacion issue #54 (fases A+B): documentos distintos a boleta 39/41.
TIPOS_DTE_CERT_SET_BASICO_FACTURACION = frozenset(
	{
		TIPO_DTE_FACTURA_ELECTRONICA,
		TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
		TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
	}
)
# Tipos DTE para los que existe flujo CAF + TED en codigo (boleta, factura 33, NC 61, ND 56).
CAF_SUPPORTED_TIPOS_DTE = frozenset(
	{
		TIPO_DTE_BOLETA_AFECTA,
		TIPO_DTE_BOLETA_EXENTA,
		TIPO_DTE_FACTURA_ELECTRONICA,
		TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
		TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
	}
)

# Tasa IVA Chile (porcentaje, puede cambiar por ley).
IVA_RATE = 19.0

# Limites de longitud segun SII.
MAX_RSR_LENGTH = 40  # Razon Social Receptor en TED
MAX_IT1_LENGTH = 40  # Descripcion primer item en TED

# Paths XSD: el modulo vive en pagosbf/pagosbf/pagosbf/dte/, los XSD estan en
# pagosbf/pagosbf/public/xsd/ (convencion Frappe para assets del app).
_XSD_BASE = Path(__file__).resolve().parents[2] / "public" / "xsd"


def xsd_path(version: str = "boleta") -> Path:
	"""Retorna el directorio XSD para la version indicada.

	Default `boleta` apunta a `public/xsd/boleta/`. Use ``consumo_folio`` para
	``ConsumoFolio_v10.xsd``. Si en el futuro SII publica ``boleta_v12``, se crea
	otra carpeta y se cambia ``SII Configuration.version_schema``.
	"""
	return _XSD_BASE / version


def xsd_file(name: str, version: str = "boleta") -> Path:
	"""Retorna el path absoluto a un XSD dado su nombre (sin sufijo)."""
	return xsd_path(version) / name
