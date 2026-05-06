# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Sobre `EnvioBOLETA` con los 5 DTE del set de prueba BE (firmados DTE + sobre)."""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe
from frappe.utils import getdate

from pagosbf.pagosbf.dte.be_set_prueba import be_set_prueba_dte_data
from pagosbf.pagosbf.boleta.caf_file import load_caf_data
from pagosbf.pagosbf.boleta.cert_utils import get_signing_material_or_throw
from pagosbf.pagosbf.boleta import emision
from pagosbf.pagosbf.dte import constants, xml_builder, xml_signer
from pagosbf.pagosbf.dte.envio_builder import RUT_SII_CARATULA, CaratulaEmision, build_envio_boleta_draft_multi
from pagosbf.pagosbf.dte.ted_generator import build_signed_ted

_DEFAULT_FOLIOS = (11, 12, 13, 14, 15)


def construir_sobre_set_prueba_be(
	*,
	folios: list[int] | tuple[int, ...] | None = None,
	caf_name: str | None = None,
	firmar: bool = True,
	fecha_emision: str | date | None = None,
) -> dict[str, Any]:
	"""Arma 5 DTE (CASO-1..5), timbra con CAF, firma cada DTE y firma el sobre.

	No consume folios en la base ni llama al SII. Requiere CAF tipo 39 que cubra
	todos los folios indicados y certificado en SII Configuration si ``firmar``.

	Args:
	    folios: exactamente 5 enteros (por defecto 11-15). Deben estar en el rango del CAF.
	    caf_name: name del DocType CAF; si no, el primero no agotado para tipo 39.
	    firmar: si False, solo devuelve XML DTE con TED (sin firmas XMLDSig).
	    fecha_emision: opcional YYYY-MM-DD; si se omite, se usa la fecha (Santiago)
	        correspondiente a ``timestamp_firma`` (``_now_santiago()``) del momento del
	        armado, alineada con el plazo de envio SII (evita reparo DTE-1-650 por FE
	        desfasada respecto al envio).

	Returns:
	    Dict con ``casos`` (lista de dicts por CASO), ``xml_sobre`` (borrador sin firma sobre),
	    ``xml_sobre_firmado``, ``caf_usado``, ``folios``.
	"""
	if folios is None:
		folios_t = _DEFAULT_FOLIOS
	else:
		folios_t = tuple(int(x) for x in folios)
	if len(folios_t) != 5:
		frappe.throw("Se requieren exactamente 5 folios (CASO-1 a CASO-5).")

	em = emision.emisor_from_sii_configuration()
	tipo = int(constants.TIPO_DTE_BOLETA_AFECTA)
	caf = caf_name or emision.resolve_caf_por_tipo_dte(tipo)
	caf_d = load_caf_data(caf)
	if int(caf_d.tipo_dte) != tipo:
		frappe.throw(f"CAF {caf!r} es TD={caf_d.tipo_dte}, se espera {tipo}.")

	r0, r1 = int(caf_d.rango_desde), int(caf_d.rango_hasta)
	for i, f in enumerate(folios_t):
		if not (r0 <= f <= r1):
			frappe.throw(f"Folio {f} (CASO-{i + 1}) fuera del CAF {caf!r} ({r0}-{r1}).")

	ts = emision._now_santiago()  # noqa: SLF001 — misma base horaria que emision SII real
	if fecha_emision is None:
		# Misma fecha calendario que TmstFirma/TED/Caratula evita DTE-1-650 (plazo envio vs FE).
		fe = ts.date()
	elif isinstance(fecha_emision, date):
		fe = fecha_emision
	else:
		fe = getdate(fecha_emision)
	ver = emision._xsd_version()  # noqa: SLF001

	casos_out: list[dict[str, str]] = []
	dtes_firmados: list[bytes] = []

	cert_name = ""
	st = None
	if firmar:
		cert_name = (frappe.get_single("SII Configuration").get("certificado_digital") or "").strip()
		if not cert_name:
			frappe.throw("firmar=True requiere Certificado Digital en SII Configuration.")
		st = get_signing_material_or_throw(cert_name)

	for idx, folio in enumerate(folios_t):
		caso_n = idx + 1
		data = be_set_prueba_dte_data(
			caso_n,
			emisor=em,
			folio=int(folio),
			fecha_emision=fe,
			timestamp_firma=ts,
		)
		draft = xml_builder.build_dte(data)
		ted = build_signed_ted(draft.dd_data, caf_d, data.timestamp_firma)
		dte_pre = xml_builder.insert_ted(draft, ted, data.timestamp_firma)
		xml_builder.validate_dte_xml(dte_pre, version=ver)
		entry: dict[str, str] = {
			"caso": f"CASO-{caso_n}",
			"folio": str(folio),
			"xml_dte": emision._bytes_xml_log(dte_pre),  # noqa: SLF001
			"xml_dte_firmado": "",
		}
		if st is not None:
			dte_f = xml_signer.sign_dte(dte_pre, st, reference_uri=draft.documento_id)
			dtes_firmados.append(dte_f)
			entry["xml_dte_firmado"] = emision._bytes_xml_log(dte_f)  # noqa: SLF001
		casos_out.append(entry)

	xml_sobre = ""
	xml_sobre_firmado = ""

	if firmar and dtes_firmados:
		assert st is not None
		emision.validate_resolucion_para_caratula_envio_boleta()
		st_rut = (frappe.get_doc("Certificado Digital", cert_name).rut_firmante or em.rut).strip()
		st_rut = st_rut.replace(" ", "").replace(".", "")
		tmst_env = emision._now_santiago()  # noqa: SLF001
		carat = CaratulaEmision(
			rut_emisor=em.rut,
			rut_envia=st_rut,
			rut_receptor=RUT_SII_CARATULA,
			fch_resol=em.resolucion_fecha,
			nro_resol=int(em.resolucion_numero or 0),
			tmst_firma_env=tmst_env,
			tipo_dte=tipo,
			nro_dtes=5,
			set_dte_id="SetDte1",
		)
		borr = build_envio_boleta_draft_multi(dtes_firmados, carat)
		xml_sobre = emision._bytes_xml_log(borr)  # noqa: SLF001
		sobre = xml_signer.sign_envio_boleta(borr, st, reference_uri=carat.set_dte_id)
		xml_sobre_firmado = emision._bytes_xml_log(sobre)  # noqa: SLF001

	return {
		"casos": casos_out,
		"xml_sobre": xml_sobre,
		"xml_sobre_firmado": xml_sobre_firmado,
		"caf_usado": caf,
		"folios": [str(x) for x in folios_t],
		"firmado": bool(firmar and xml_sobre_firmado),
	}


__all__ = ["construir_sobre_set_prueba_be"]
