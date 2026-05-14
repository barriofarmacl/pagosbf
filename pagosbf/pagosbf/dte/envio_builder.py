"""Arma sobres `EnvioBOLETA` (boleta) y `EnvioDTE` (documentos estandar) sin firma del sobre.

La firma final es `xml_signer.sign_envio_boleta` / `xml_signer.sign_envio_dte`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from lxml import etree

from .constants import (
	NS_SII_DTE,
	SII_XML_ENCODING,
)
from .sii_xml_bytes import finalize_sii_xml_bytes

# RUT SII en Caratula (receptor del intercambio); practica habitual.
RUT_SII_CARATULA = "60803000-K"

# Solo namespace SII al armar el borrador en lxml. `xmlns:xsi` / `xsi:schemaLocation`
# los anade `sign_envio_boleta` **antes** de firmar (sustitucion por bytes en el
# abridor de raiz), para SCH-00001 sin romper el digest del sobre (RFR si se inyecta
# post-firma). Los <DTE> se incrustan como bytes para no reintroducir DTE-3-505.
_NS_ENVIO = {None: NS_SII_DTE}

_CARATULA_END = b"</Caratula>"


def _strip_xml_declaration_fragment(raw: bytes) -> bytes:
	"""Quita la declaracion XML inicial de un fragmento <DTE> para incrustarlo en SetDTE."""
	s = raw.lstrip()
	if s.startswith(b"<?xml"):
		end = s.find(b"?>")
		if end != -1:
			s = s[end + 2 :].lstrip()
	return s


@dataclass(frozen=True, slots=True)
class CaratulaEmision:
	"""Valores de `Caratula` para un envio con una boleta o DTE estandar."""

	rut_emisor: str
	rut_envia: str
	rut_receptor: str
	fch_resol: date
	nro_resol: int
	tmst_firma_env: datetime
	tipo_dte: int
	nro_dtes: int = 1
	set_dte_id: str = "SetDte1"
	# Si se informa, reempluye el unico SubTotDTE (tipo_dte, nro_dtes) por varias filas
	# (p. ej. EnvioDTE con Factura 33 + NC 61 + ND 56). La suma de NroDTE debe coincidir
	# con la cantidad de fragmentos <DTE> en el sobre.
	subtot_dtes: tuple[tuple[int, int], ...] | None = None

	def subtot_rows(self) -> tuple[tuple[int, int], ...]:
		if self.subtot_dtes is not None:
			return self.subtot_dtes
		return ((self.tipo_dte, self.nro_dtes),)

	def expected_dte_count(self) -> int:
		return sum(int(n) for _, n in self.subtot_rows())


def build_envio_boleta_draft(
	signed_dte_bytes: bytes,
	caratula: CaratulaEmision,
) -> bytes:
	"""Arma `EnvioBOLETA` con un solo `DTE` firmado. Ver `build_envio_boleta_draft_multi`."""
	return build_envio_boleta_draft_multi((signed_dte_bytes,), caratula)


def build_envio_boleta_draft_multi(
	signed_dte_bytes_seq: tuple[bytes, ...] | list[bytes],
	caratula: CaratulaEmision,
) -> bytes:
	"""Arma `EnvioBOLETA` con `SetDTE` (Caratula + N DTE firmados) sin `ds:Signature` del sobre.

	El XSD permite `DTE` con ``maxOccurs="unbounded"``. `CaratulaEmision.nro_dtes` debe
	coincidir con ``len(signed_dte_bytes_seq)`` (tipicamente todos mismo `TipoDTE`).

	Args:
	    signed_dte_bytes_seq: XML de cada `DTE` completo (ya firmado a nivel documento),
	        en el orden de envio (CASO-1 ... CASO-5 en set de certificacion BE).
	    caratula: Caratula y atributo `ID` de `SetDTE` (referencia de firma en `sign_envio_boleta`).

	Raises:
	    ValueError: si la secuencia esta vacia o algun XML no es raiz `DTE`.
	"""
	if not signed_dte_bytes_seq:
		raise ValueError("Se requiere al menos un DTE firmado para el sobre.")
	if int(caratula.expected_dte_count()) != len(signed_dte_bytes_seq):
		raise ValueError(
			f"Suma SubTotDTE (NroDTE) ({caratula.expected_dte_count()}) != "
			f"cantidad de DTE ({len(signed_dte_bytes_seq)})."
		)

	s_ns = f"{{{NS_SII_DTE}}}"
	envio = etree.Element(
		"%sEnvioBOLETA" % s_ns,
		nsmap=_NS_ENVIO,
		version="1.0",
	)
	setdte = etree.SubElement(
		envio, "%sSetDTE" % s_ns, ID=caratula.set_dte_id
	)

	ca = etree.SubElement(setdte, "%sCaratula" % s_ns, version="1.0")
	etree.SubElement(ca, "%sRutEmisor" % s_ns).text = _norm_rut(caratula.rut_emisor)
	etree.SubElement(ca, "%sRutEnvia" % s_ns).text = _norm_rut(caratula.rut_envia)
	etree.SubElement(ca, "%sRutReceptor" % s_ns).text = _norm_rut(caratula.rut_receptor)
	etree.SubElement(ca, "%sFchResol" % s_ns).text = caratula.fch_resol.isoformat()
	etree.SubElement(ca, "%sNroResol" % s_ns).text = str(int(caratula.nro_resol))
	etree.SubElement(ca, "%sTmstFirmaEnv" % s_ns).text = _fmt_tms(
		caratula.tmst_firma_env
	)
	for tpo, nro in caratula.subtot_rows():
		std = etree.SubElement(ca, "%sSubTotDTE" % s_ns)
		etree.SubElement(std, "%sTpoDTE" % s_ns).text = str(int(tpo))
		etree.SubElement(std, "%sNroDTE" % s_ns).text = str(int(nro))

	# Sin re-parsear cada <DTE>: `setdte.append(etree.fromstring(raw))` + `tostring(envio)`
	# altera namespaces en <DTE> (p. ej. xmlns:xsi heredado) y **invalida XMLDSig** del
	# Documento — mismo sintoma que rechazo SII **DTE-3-505**. Se insertan los bytes
	# firmados tal cual tras </Caratula>.
	inner = etree.tostring(
		envio,
		encoding=SII_XML_ENCODING,
		xml_declaration=False,
		pretty_print=False,
	)
	idx = inner.find(_CARATULA_END)
	if idx == -1:
		raise ValueError("EnvioBOLETA: no se encontro cierre </Caratula> para incrustar DTE.")
	frags: list[bytes] = []
	for raw in signed_dte_bytes_seq:
		frag = _strip_xml_declaration_fragment(raw)
		if not frag.startswith(b"<DTE"):
			raise ValueError("Cada DTE firmado debe ser un XML con raiz <DTE> (tras quitar prolog).")
		frags.append(frag)
	dte_concat = b"".join(frags)
	combined = inner[: idx + len(_CARATULA_END)] + dte_concat + inner[idx + len(_CARATULA_END) :]
	prolog = b'<?xml version="1.0" encoding="ISO-8859-1"?>'
	return finalize_sii_xml_bytes(prolog + combined)


def build_envio_dte_draft(
	signed_dte_bytes: bytes,
	caratula: CaratulaEmision,
) -> bytes:
	"""Arma `EnvioDTE` con un solo `DTE` firmado. Ver `build_envio_dte_draft_multi`."""
	return build_envio_dte_draft_multi((signed_dte_bytes,), caratula)


def build_envio_dte_draft_multi(
	signed_dte_bytes_seq: tuple[bytes, ...] | list[bytes],
	caratula: CaratulaEmision,
) -> bytes:
	"""Arma `EnvioDTE` con `SetDTE` (Caratula + N DTE firmados) sin `ds:Signature` del sobre.

	Misma estrategia que `build_envio_boleta_draft_multi`: incrusta cada ``<DTE>``
	como bytes tras ``</Caratula>`` para no invalidar XMLDSig del documento.
	"""
	if not signed_dte_bytes_seq:
		raise ValueError("Se requiere al menos un DTE firmado para el sobre.")
	if int(caratula.expected_dte_count()) != len(signed_dte_bytes_seq):
		raise ValueError(
			f"Suma SubTotDTE (NroDTE) ({caratula.expected_dte_count()}) != "
			f"cantidad de DTE ({len(signed_dte_bytes_seq)})."
		)

	s_ns = f"{{{NS_SII_DTE}}}"
	envio = etree.Element(
		"%sEnvioDTE" % s_ns,
		nsmap=_NS_ENVIO,
		version="1.0",
	)
	setdte = etree.SubElement(
		envio, "%sSetDTE" % s_ns, ID=caratula.set_dte_id
	)

	ca = etree.SubElement(setdte, "%sCaratula" % s_ns, version="1.0")
	etree.SubElement(ca, "%sRutEmisor" % s_ns).text = _norm_rut(caratula.rut_emisor)
	etree.SubElement(ca, "%sRutEnvia" % s_ns).text = _norm_rut(caratula.rut_envia)
	etree.SubElement(ca, "%sRutReceptor" % s_ns).text = _norm_rut(caratula.rut_receptor)
	etree.SubElement(ca, "%sFchResol" % s_ns).text = caratula.fch_resol.isoformat()
	etree.SubElement(ca, "%sNroResol" % s_ns).text = str(int(caratula.nro_resol))
	etree.SubElement(ca, "%sTmstFirmaEnv" % s_ns).text = _fmt_tms(
		caratula.tmst_firma_env
	)
	for tpo, nro in caratula.subtot_rows():
		std = etree.SubElement(ca, "%sSubTotDTE" % s_ns)
		etree.SubElement(std, "%sTpoDTE" % s_ns).text = str(int(tpo))
		etree.SubElement(std, "%sNroDTE" % s_ns).text = str(int(nro))

	inner = etree.tostring(
		envio,
		encoding=SII_XML_ENCODING,
		xml_declaration=False,
		pretty_print=False,
	)
	idx = inner.find(_CARATULA_END)
	if idx == -1:
		raise ValueError("EnvioDTE: no se encontro cierre </Caratula> para incrustar DTE.")
	frags: list[bytes] = []
	for raw in signed_dte_bytes_seq:
		frag = _strip_xml_declaration_fragment(raw)
		if not frag.startswith(b"<DTE"):
			raise ValueError("Cada DTE firmado debe ser un XML con raiz <DTE> (tras quitar prolog).")
		frags.append(frag)
	dte_concat = b"".join(frags)
	combined = inner[: idx + len(_CARATULA_END)] + dte_concat + inner[idx + len(_CARATULA_END) :]
	prolog = b'<?xml version="1.0" encoding="ISO-8859-1"?>'
	return finalize_sii_xml_bytes(prolog + combined)


def _norm_rut(r: str) -> str:
	return (r or "").replace(".", "").replace(" ", "").strip()


def _fmt_tms(dt: datetime) -> str:
	"""SII: `AAAA-MM-DDTHH:MM:SS` (sin Z; uso hora local al emitir)."""
	return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


__all__ = [
	"RUT_SII_CARATULA",
	"CaratulaEmision",
	"build_envio_boleta_draft",
	"build_envio_boleta_draft_multi",
	"build_envio_dte_draft",
	"build_envio_dte_draft_multi",
]
