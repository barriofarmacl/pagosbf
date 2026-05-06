"""Utilidades de RUT chileno (split para campos SII: Rut, Dv)."""

from __future__ import annotations

import re

_RUT_RE = re.compile(r"^\s*(\d{1,8})\s*[-\s]?\s*([0-9Kk])")


def split_rut(rut: str) -> tuple[str, str]:
	"""Separa cuerpo y digito verificador: ``'12.345.678-5'`` -> ``('12345678', '5')``."""
	if not rut or not (m := _RUT_RE.match(rut.strip().replace(".", ""))):
		raise ValueError(f"RUT invalido: {rut!r}")
	body, dv = m.group(1), m.group(2).upper()
	if dv == "K":
		dv = "K"
	return body, dv


def rut_para_dte_xml(rut: str) -> str:
	"""Formato XSD SII (boleta/DTE): ``cuerpo-dv`` con dv en 0-9 o K.

	Acepta guion opcional y puntos (p. ej. ``76.957.985-0``, ``769579850``).
	"""
	if not rut or not str(rut).strip():
		return ""
	norm = str(rut).strip().replace(".", "").replace(" ", "")
	body, dv = split_rut(norm)
	return f"{body}-{dv}"


def rut_para_soap_empresa(rut: str) -> tuple[str, str]:
	"""Rut emisor 8 cifras (padding con ceros a la izq.) y DV, como pide SII en SOAP/HTTP.

	Algunas rutas requieren el numero sin padding; otras 8 cifras. Aqui: body
	zerofill a 8 cifras para DteUpload/QueryEstUp alineado a manuales SII.
	"""
	body, dv = split_rut(rut)
	return body.zfill(8), dv
