"""Certificado Digital: PFX + password para firma XMLDSig SII.

Spec pagosbf-sii-boleta R2.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class CertificadoDigital(Document):
	"""Certificado PKCS#12 del firmante autorizado ante SII."""

	def validate(self) -> None:
		if self.vigencia_desde and self.vigencia_hasta and self.vigencia_hasta < self.vigencia_desde:
			frappe.throw("Vigencia hasta debe ser posterior a vigencia desde.")

	def get_signing_material(self):
		"""Retorna `SigningMaterial` PFX; alias util para servicios fase 5."""
		from pagosbf.pagosbf.boleta.cert_utils import get_signing_material

		return get_signing_material(self.name)
