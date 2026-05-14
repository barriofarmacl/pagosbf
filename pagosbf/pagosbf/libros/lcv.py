"""Libro de Ventas Electronico 4811535 desde `DTE Documento` aceptados."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

import frappe

from pagosbf.pagosbf.dte.constants import (
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from pagosbf.pagosbf.dte.libro_cv_builder import TotalesPeriodoLibroCV

TIPOS_DTE_LCV_CERTIFICACION = (
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
)
ESTADOS_DTE_ACEPTADOS_PARA_LCV = frozenset({"EPR", "ACEPTADO", "ACEPTADO_SII"})


@dataclass(frozen=True, slots=True)
class DTEDocumentoVenta:
	tipo_dte: int
	monto_neto: int
	monto_iva: int
	monto_exento: int
	monto_total: int
	estado_envio: str


def totales_periodo_ventas_desde_dte_documentos(
	documentos: Iterable[Any],
) -> tuple[TotalesPeriodoLibroCV, ...]:
	"""Agrupa `DTE Documento` aceptados para `ResumenPeriodo/TotalesPeriodo`.

	El Libro de Ventas de certificacion solo debe considerar documentos aceptados
	por SII. Los documentos enviados o pendientes quedan fuera para evitar reportar
	movimientos sin aceptacion operacional.
	"""
	acc: dict[int, dict[str, int]] = defaultdict(
		lambda: {"doc": 0, "exe": 0, "neto": 0, "iva": 0, "total": 0}
	)
	for raw in documentos:
		row = _normalizar_dte_documento(raw)
		if row.estado_envio not in ESTADOS_DTE_ACEPTADOS_PARA_LCV:
			continue
		if row.tipo_dte not in TIPOS_DTE_LCV_CERTIFICACION:
			continue
		bucket = acc[row.tipo_dte]
		bucket["doc"] += 1
		bucket["exe"] += row.monto_exento
		bucket["neto"] += row.monto_neto
		bucket["iva"] += row.monto_iva
		bucket["total"] += row.monto_total

	return tuple(
		TotalesPeriodoLibroCV(
			tpo_doc=tipo,
			tot_doc=values["doc"],
			tot_mnt_exe=values["exe"],
			tot_mnt_neto=values["neto"],
			tot_mnt_iva=values["iva"],
			tot_mnt_total=values["total"],
		)
		for tipo, values in sorted(acc.items())
	)


def advertencias_lcv_desde_dte_documentos(documentos: Iterable[Any]) -> list[str]:
	"""Advierte si el LCV 4811535 no tiene DTE aceptados como insumo."""
	if totales_periodo_ventas_desde_dte_documentos(documentos):
		return []
	return ["LCV 4811535 incompleto: no hay DTE Documento aceptados por SII para generar el libro."]


def cargar_dte_documentos_venta_aceptados(
	*,
	periodo_tributario: str | None = None,
) -> tuple[DTEDocumentoVenta, ...]:
	"""Lee `DTE Documento` aceptados desde Frappe, opcionalmente filtrados por periodo `YYYY-MM`."""
	filters: dict[str, Any] = {
		"tipo_dte": ["in", [str(t) for t in TIPOS_DTE_LCV_CERTIFICACION]],
		"estado_envio": ["in", list(ESTADOS_DTE_ACEPTADOS_PARA_LCV)],
	}
	if periodo_tributario:
		start, end = _periodo_bounds(periodo_tributario)
		filters["fecha_emision"] = ["between", [start.isoformat(), end.isoformat()]]

	rows = frappe.get_all(
		"DTE Documento",
		filters=filters,
		fields=["tipo_dte", "monto_neto", "monto_iva", "monto_exento", "monto_total", "estado_envio"],
		order_by="tipo_dte asc, folio asc",
	)
	return tuple(_normalizar_dte_documento(row) for row in rows)


def _normalizar_dte_documento(raw: Any) -> DTEDocumentoVenta:
	return DTEDocumentoVenta(
		tipo_dte=int(_get(raw, "tipo_dte") or 0),
		monto_neto=_int_clp(_get(raw, "monto_neto")),
		monto_iva=_int_clp(_get(raw, "monto_iva")),
		monto_exento=_int_clp(_get(raw, "monto_exento")),
		monto_total=_int_clp(_get(raw, "monto_total")),
		estado_envio=str(_get(raw, "estado_envio") or "").strip().upper(),
	)


def _periodo_bounds(periodo_tributario: str) -> tuple[date, date]:
	year_text, month_text = periodo_tributario.strip().split("-", 1)
	year, month = int(year_text), int(month_text)
	start = date(year, month, 1)
	end = date(year + (month // 12), 1 if month == 12 else month + 1, 1)
	return start, end


def _get(raw: Any, key: str) -> Any:
	if isinstance(raw, dict):
		return raw.get(key)
	if hasattr(raw, "get"):
		try:
			return raw.get(key)
		except TypeError:
			pass
	return getattr(raw, key, None)


def _int_clp(value: Any) -> int:
	return int(round(float(value or 0)))


__all__ = [
	"DTEDocumentoVenta",
	"ESTADOS_DTE_ACEPTADOS_PARA_LCV",
	"TIPOS_DTE_LCV_CERTIFICACION",
	"advertencias_lcv_desde_dte_documentos",
	"cargar_dte_documentos_venta_aceptados",
	"totales_periodo_ventas_desde_dte_documentos",
]
