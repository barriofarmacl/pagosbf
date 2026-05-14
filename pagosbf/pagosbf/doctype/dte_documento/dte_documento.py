"""DTE Documento: trazabilidad para factura 33, nota credito 61 y nota debito 56."""

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


class DTEDocumento(Document):
	def validate(self) -> None:
		if self.tipo_dte not in ("33", "61", "56"):
			frappe.throw("tipo_dte debe ser 33, 61 o 56 para DTE Documento.")
		if self.tipo_dte == "33" and not (self.sales_invoice or "").strip():
			frappe.throw("DTE Documento tipo 33 requiere Sales Invoice.")
		if self.monto_total is None:
			self.monto_total = (self.monto_neto or 0) + (self.monto_iva or 0) + (self.monto_exento or 0)
		self._validate_transition()

	def _validate_transition(self) -> None:
		if self.is_new():
			return
		previous = frappe.db.get_value("DTE Documento", self.name, "estado_envio")
		if not previous or previous == self.estado_envio:
			return
		allowed = VALID_TRANSITIONS.get(previous, set())
		if self.estado_envio not in allowed:
			frappe.throw(
				f"Transicion invalida de estado_envio '{previous}' a '{self.estado_envio}'. "
				f"Transiciones permitidas: {sorted(allowed) or 'ninguna (estado final)'}."
			)
