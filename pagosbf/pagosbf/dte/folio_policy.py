"""Reglas puras (sin Frappe) para asignar folio dentro de un rango de CAF.

El SII asigna un rango [D, H]. El primer folio utilizable es D cuando
`folios_consumidos` es 0. Tras asignar el folio F, se incrementa el contador
de consumo en 1; cuando el total consumido alcanza el cupo, el CAF queda
agotado.
"""

from __future__ import annotations

from dataclasses import dataclass


def cupo_folios(rango_desde: int, rango_hasta: int) -> int:
	"""Numero de folios autorizados (incluye extremos)."""
	if rango_hasta < rango_desde or rango_desde < 1:
		raise ValueError("Rango de folios invalido")
	return rango_hasta - rango_desde + 1


def folio_a_asignar(rango_desde: int, folios_consumidos: int) -> int:
	"""Folio a usar si aun no se ha incrementado el contador (estado leido bajo lock)."""
	if folios_consumidos < 0:
		raise ValueError("folios_consumidos no puede ser negativo")
	return rango_desde + folios_consumidos


def queda_cupo(
	rango_desde: int, rango_hasta: int, folios_consumidos: int
) -> bool:
	"""Indica si aun se puede asignar al menos un folio mas."""
	return folios_consumidos < cupo_folios(rango_desde, rango_hasta)


def agotado_despues_de_asignar(
	rango_desde: int, rango_hasta: int, consumidos_antes: int
) -> bool:
	"""Tras asignar un folio, el nuevo consumo es consumidos_antes + 1."""
	if not queda_cupo(rango_desde, rango_hasta, consumidos_antes):
		raise ValueError("No queda folio bajo el estado dado (pre-incremento).")
	return consumidos_antes + 1 >= cupo_folios(rango_desde, rango_hasta)


@dataclass(frozen=True, slots=True)
class FolioSnapshot:
	"""Lectura coherente de rango y consumo (p. ej. bajo `FOR UPDATE`)."""

	rango_desde: int
	rango_hasta: int
	folios_consumidos: int
	agotado: bool

	def puede_asignar(self) -> bool:
		if self.agotado:
			return False
		return queda_cupo(self.rango_desde, self.rango_hasta, self.folios_consumidos)


__all__ = [
	"FolioSnapshot",
	"agotado_despues_de_asignar",
	"cupo_folios",
	"folio_a_asignar",
	"queda_cupo",
]
