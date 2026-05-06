"""DTE Boleta: entidad unitaria que representa una boleta electronica 39/41.

Spec pagosbf-sii-boleta R4..R8. El ciclo completo (build, TED, firma, envio,
consulta) se implementa en fases 2-5; esta clase provee el contrato de
persistencia y transiciones de estado basicas.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


VALID_TRANSITIONS = {
	"PENDIENTE": {"VALIDANDO", "RECHAZADO_LOCAL"},
	"VALIDANDO": {"ENVIADO", "RECHAZADO_LOCAL"},
	"ENVIADO": {"EPR", "RCH", "RFR", "RSC"},
	"RECHAZADO_LOCAL": set(),
	"EPR": set(),
	"RCH": set(),
	"RFR": set(),
	"RSC": set(),
}


class DTEBoleta(Document):
	def validate(self) -> None:
		si = (self.sales_invoice or "").strip()
		pi = (self.pos_invoice or "").strip()
		if bool(si) == bool(pi):
			frappe.throw(
				"Indique exactamente un origen: Sales Invoice o POS Invoice (no ambos ni ninguno)."
			)
		if self.tipo_dte not in ("39", "41"):
			frappe.throw("tipo_dte debe ser 39 o 41 para boletas.")
		if self.monto_total is None:
			self.monto_total = (self.monto_neto or 0) + (self.monto_iva or 0) + (self.monto_exento or 0)
		self._validate_transition()

	def _validate_transition(self) -> None:
		if self.is_new():
			return
		previous = frappe.db.get_value("DTE Boleta", self.name, "estado_envio")
		if not previous or previous == self.estado_envio:
			return
		allowed = VALID_TRANSITIONS.get(previous, set())
		if self.estado_envio not in allowed:
			frappe.throw(
				f"Transicion invalida de estado_envio '{previous}' a '{self.estado_envio}'. "
				f"Transiciones permitidas: {sorted(allowed) or 'ninguna (estado final)'}."
			)
