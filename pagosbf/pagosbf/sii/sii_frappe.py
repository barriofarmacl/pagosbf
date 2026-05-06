"""Puente Frappe: `SIIClient` desde Single y logging a `DTE Boleta.respuestas`."""

from __future__ import annotations

from .sii_client import SIIClient, SIIClientConfig


def sii_client_from_sii_configuration() -> SIIClient:
	"""Instancia `SIIClient` con URLs del Single `SII Configuration`."""
	import frappe  # lazy: tests sin bench siguen importando sii.sii_client

	c = frappe.get_single("SII Configuration")
	base = SIIClientConfig()
	sem = (c.get("url_semilla") or base.url_semilla).strip() or base.url_semilla
	tok = (c.get("url_token") or base.url_token).strip() or base.url_token
	env = (c.get("url_envio") or base.url_envio).strip() or base.url_envio
	ces = (c.get("url_consulta_estado") or base.url_consulta).strip() or base.url_consulta
	return SIIClient(
		SIIClientConfig(
			url_semilla=sem,
			url_token=tok,
			url_envio=env,
			url_consulta=ces,
		)
	)


def append_dte_respuesta_sii(
	dte_boleta_name: str,
	*,
	accion: str,
	request_xml: str | None = None,
	response_xml: str | None = None,
	estado: str | None = None,
	glosa: str | None = None,
) -> None:
	"""Anexa un renglon a la tabla hija `respuestas` de `DTE Boleta` (auditoria SII)."""
	import frappe
	from frappe.utils import now

	doc = frappe.get_doc("DTE Boleta", dte_boleta_name)
	doc.append(
		"respuestas",
		{
			"timestamp": now(),
			"accion": accion,
			"estado": estado or "",
			"glosa": glosa or "",
			"request_xml": request_xml or "",
			"response_xml": response_xml or "",
		},
	)
	doc.save(ignore_permissions=True, ignore_version=True)


__all__ = ["append_dte_respuesta_sii", "sii_client_from_sii_configuration"]
