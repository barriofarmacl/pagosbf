# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Genera XML DTE/sobre localmente sin consumir folio ni llamar al SII."""

from __future__ import annotations

import frappe

from pagosbf.pagosbf.boleta.caf_file import load_caf_data
from pagosbf.pagosbf.boleta.cert_utils import get_signing_material_or_throw
from pagosbf.pagosbf.boleta.invoice_to_boleta import pos_invoice_to_dte_data, sales_invoice_to_dte_data
from pagosbf.pagosbf.dte.envio_builder import RUT_SII_CARATULA, CaratulaEmision, build_envio_boleta_draft
from pagosbf.pagosbf.dte.ted_generator import build_signed_ted
from pagosbf.pagosbf.dte import xml_builder, xml_signer

from . import emision


def preview_boleta_xml(
	*,
	source_doctype: str,
	source_name: str,
	folio: int,
	caf_name: str | None = None,
	sii_cod_ref: str | None = None,
	sii_razon_ref: str | None = None,
	firmar: bool = True,
) -> dict[str, str]:
	"""Arma DTE + TED; opcional firma DTE y sobre. No asigna folio en CAF ni envia al SII.

	Args:
	    source_doctype: ``POS Invoice`` o ``Sales Invoice``.
	    source_name: name del documento origen (debe estar enviado).
	    folio: numero a usar en el XML (debe estar dentro del rango del CAF indicado).
	    caf_name: opcional; si no, se elige CAF activo por tipo DTE.
	    sii_cod_ref / sii_razon_ref: referencia certificacion (SET / CASO-n).
	    firmar: si True y hay certificado en SII Configuration, firma DTE y EnvioBOLETA.

	Returns:
	    Dict con claves ``xml_dte`` (previo firma documento), ``xml_dte_firmado``, ``xml_sobre_firmado``
	    (vacios si ``firmar=False`` o sin certificado).
	"""
	if source_doctype not in ("POS Invoice", "Sales Invoice"):
		frappe.throw(f"Origen no soportado: {source_doctype!r}")
	if folio < 1:
		frappe.throw("folio debe ser >= 1.")

	doc = frappe.get_doc(source_doctype, source_name)
	if doc.docstatus != 1:
		frappe.throw(f"{source_doctype} debe estar enviado (docstatus=1).")

	em = emision.emisor_from_sii_configuration()
	tipo = emision._tipo_preliminar(doc)  # noqa: SLF001
	caf = caf_name or emision.resolve_caf_por_tipo_dte(tipo)
	caf_d = load_caf_data(caf)
	if int(caf_d.tipo_dte) != int(tipo):
		frappe.throw(
			f"CAF {caf!r} es TD={caf_d.tipo_dte}, pero el documento pide TipoDTE {tipo}."
		)
	r0, r1 = int(caf_d.rango_desde), int(caf_d.rango_hasta)
	if not (r0 <= int(folio) <= r1):
		frappe.throw(
			f"Folio {folio} fuera del rango del CAF {caf!r} ({r0}-{r1})."
		)

	if source_doctype == "Sales Invoice":
		data = sales_invoice_to_dte_data(doc, folio=int(folio), emisor=em)
	else:
		data = pos_invoice_to_dte_data(doc, folio=int(folio), emisor=em)

	cod = (sii_cod_ref or "").strip() or None
	raz = (sii_razon_ref or "").strip() or None
	data = emision._with_sii_cert_refs(data, cod_ref=cod, razon_ref=raz)  # noqa: SLF001
	data.validate()

	ver = emision._xsd_version()  # noqa: SLF001
	draft = xml_builder.build_dte(data)
	ted = build_signed_ted(draft.dd_data, caf_d, data.timestamp_firma)
	dte_pre = xml_builder.insert_ted(draft, ted, data.timestamp_firma)
	xml_builder.validate_dte_xml(dte_pre, version=ver)
	out: dict[str, str] = {
		"xml_dte": emision._bytes_xml_log(dte_pre),  # noqa: SLF001
		"xml_dte_firmado": "",
		"xml_sobre_firmado": "",
		"caf_usado": caf,
		"tipo_dte": str(tipo),
		"folio": str(folio),
	}

	if not firmar:
		return out

	cert = (frappe.get_single("SII Configuration").get("certificado_digital") or "").strip()
	if not cert:
		return out

	st = get_signing_material_or_throw(cert)
	st_rut = (frappe.get_doc("Certificado Digital", cert).rut_firmante or em.rut).strip()
	st_rut = st_rut.replace(" ", "").replace(".", "")
	emision.validate_resolucion_para_caratula_envio_boleta()
	dte_f = xml_signer.sign_dte(dte_pre, st, reference_uri=draft.documento_id)
	tmst_env = emision._now_santiago()  # noqa: SLF001
	carat = CaratulaEmision(
		rut_emisor=em.rut,
		rut_envia=st_rut,
		rut_receptor=RUT_SII_CARATULA,
		fch_resol=em.resolucion_fecha,
		nro_resol=int(em.resolucion_numero or 0),
		tmst_firma_env=tmst_env,
		tipo_dte=int(data.tipo_dte),
		set_dte_id="SetDte1",
	)
	borr = build_envio_boleta_draft(dte_f, carat)
	sobre = xml_signer.sign_envio_boleta(borr, st, reference_uri=carat.set_dte_id)
	out["xml_dte_firmado"] = emision._bytes_xml_log(dte_f)  # noqa: SLF001
	out["xml_sobre_firmado"] = emision._bytes_xml_log(sobre)  # noqa: SLF001
	return out


__all__ = ["preview_boleta_xml"]
