"""SII Configuration (Single): parametros SII del emisor.

Spec pagosbf-sii-boleta R1. Los defaults apuntan a maullin.sii.cl cuando
ambiente = Certificacion.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class SIIConfiguration(Document):
	def validate(self) -> None:
		if self.ambiente == "Produccion" and "maullin.sii.cl" in (self.url_envio or ""):
			frappe.throw("URL de envio apunta a maullin (certificacion) pero ambiente es Produccion.")
