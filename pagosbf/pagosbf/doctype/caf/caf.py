"""CAF: Codigo de Autorizacion de Folios del SII.

Spec pagosbf-sii-boleta R3. El parseo del XML y la extraccion de la clave
privada para el TED se implementan en fase 3 (pagosbf.dte.caf_parser).
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class CAF(Document):
	def validate(self) -> None:
		if self.rango_desde is None or self.rango_hasta is None:
			return
		if self.rango_hasta < self.rango_desde:
			frappe.throw("Folio Hasta debe ser mayor o igual a Folio Desde.")
		cupo = self.rango_hasta - self.rango_desde + 1
		fc = self.folios_consumidos or 0
		if fc > cupo:
			frappe.throw("Folios consumidos excede el rango del CAF.")
		# Si el cupo se lleno por contador, siempre agotado.
		if fc >= cupo:
			self.agotado = 1
		# Si fc < cupo, no forzar agotado=0: permite marcar Agotado en Desk (CAF retirado,
		# pruebas sin pasar por allocate_next_folio, alinear con uso real de folios).

	def asignar_siguiente_folio(self) -> int:
		"""Bloquea el registro, incrementa el consumo y retorna el folio a usar (DTE)."""
		from pagosbf.pagosbf.dte.folio_allocator import allocate_next_folio

		return allocate_next_folio(self.name)
