# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Renderizado PDF417 del string TED (ISO-8859-1) para timbre en ticket."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from pdf417gen import encode, render_image

if TYPE_CHECKING:
	pass

# PDF417 (pdf417gen) limite ~928 palabras codigo; TED C14N suele caber. Evitar payloads absurdos.
_MAX_PAYLOAD_CHARS = 1800


def ted_payload_to_png_bytes(
	payload: str,
	*,
	scale: int = 2,
	ratio: int = 3,
	padding: int = 12,
) -> bytes:
	"""Codifica ``payload`` (C14N del TED, texto ISO-8859-1) en PDF417 y devuelve PNG en bytes.

	Raises:
	    ValueError: payload vacio, demasiado largo, o no se logra un codigo valido (filas 3..90).
	"""
	s = (payload or "").strip()
	if not s:
		raise ValueError("Payload TED vacio.")
	if len(s) > _MAX_PAYLOAD_CHARS:
		raise ValueError("Payload TED excede limite seguro para PDF417.")

	codes = None
	last_err: Exception | None = None
	for security_level in (2, 1):
		for cols in range(16, 0, -1):
			try:
				codes = encode(s, columns=cols, security_level=security_level, encoding="iso-8859-1")
				break
			except ValueError as exc:
				last_err = exc
				continue
		if codes:
			break
	if not codes:
		raise ValueError(str(last_err) if last_err else "No se pudo generar PDF417.")

	image = render_image(codes, scale=scale, ratio=ratio, padding=padding)
	buf = io.BytesIO()
	image.save(buf, format="PNG", optimize=True)
	return buf.getvalue()


__all__ = ["ted_payload_to_png_bytes"]
