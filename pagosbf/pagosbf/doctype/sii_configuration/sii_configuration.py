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
		if self.ambiente == "Produccion" and (
			"pangal.sii.cl" in (self.url_envio or "") or "apicert.sii.cl" in (self.url_semilla or "")
		):
			frappe.throw("URL de boleta apunta a certificacion (pangal/apicert) pero ambiente es Produccion.")
		if int(self.habilitar_factura_electronica or 0) and (
			"boleta.electronica" in (self.url_envio or "")
			or "rahue.sii.cl" in (self.url_envio or "")
			or "pangal.sii.cl" in (self.url_envio or "")
		):
			frappe.throw(
				"URLs REST de boleta no sirven para factura 33. "
				"Desactive Habilitar factura electronica o use DTEWS/cgi_dte."
			)
