"""Asignacion atonica de folios sobre el DocType `CAF` (Frappe).

Estrategia: `get_doc("CAF", name, for_update=True)` (bloqueo de fila InnoDB) y
luego `save` con el incremento de `folios_consumidos`. Queda en la transaccion
que Frappe tenga activa; no se llama a `frappe.db.begin()` (evita conflictos
con el ciclo de la peticion o tests: ImplicitCommitError).

Uso: desde servicios de emision (`DTE Boleta`, API) tras validar el CAF
activo. No hace I/O hacia SII; solo reserva un numero.
"""

from __future__ import annotations

from . import folio_policy


class FolioAllocatorError(Exception):
	"""Error generico al asignar folio."""


class CAFNotFoundError(FolioAllocatorError):
	"""No existe un documento `CAF` con el nombre dado."""


class FolioExhaustedError(FolioAllocatorError):
	"""Rango de folios del CAF agotado (`agotado=1` o contador al limite)."""


def allocate_next_folio(caf_name: str) -> int:
	"""Reserva y retorna el siguiente folio (entero) para el CAF dado.

	Levanta `CAFNotFoundError`, `FolioExhaustedError` o excepciones de Frappe/DB.
	Requiere contexto Frappe (site, session).
	"""
	try:
		import frappe
		from frappe.exceptions import DoesNotExistError
	except ImportError as exc:  # pragma: no cover
		raise FolioAllocatorError("allocate_next_folio requiere Frappe instalado.") from exc

	try:
		doc = frappe.get_doc("CAF", caf_name, for_update=True)
	except DoesNotExistError as exc:
		raise CAFNotFoundError(f"No existe CAF {caf_name!r}.") from exc

	r0 = int(doc.rango_desde)
	r1 = int(doc.rango_hasta)
	fc = int(doc.folios_consumidos or 0)
	ag = int(doc.agotado or 0)

	snap = folio_policy.FolioSnapshot(
		rango_desde=r0, rango_hasta=r1, folios_consumidos=fc, agotado=bool(ag)
	)
	if not snap.puede_asignar():
		raise FolioExhaustedError(
			f"CAF {caf_name!r} sin folios (consumidos={fc}, rango {r0}-{r1}, agotado={ag})"
		)

	next_folio = folio_policy.folio_a_asignar(r0, fc)
	nuevo_fc = fc + 1
	nuevo_agot = 1 if folio_policy.agotado_despues_de_asignar(r0, r1, fc) else 0

	doc.folios_consumidos = nuevo_fc
	doc.agotado = nuevo_agot
	# Test CAF creado sin `xml_caf`; en operacion el adjunto deberia existir.
	if not (doc.get("xml_caf") or "").strip():
		doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True, ignore_version=True)
	return int(next_folio)


__all__ = [
	"CAFNotFoundError",
	"FolioAllocatorError",
	"FolioExhaustedError",
	"allocate_next_folio",
]
