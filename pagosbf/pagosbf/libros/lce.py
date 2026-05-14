"""Libro de Compras Electronico 4811536: movimientos y calculos certificados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from pagosbf.pagosbf.dte.libro_cv_builder import (
	CaratulaLibroCV,
	TotalesPeriodoLibroCV,
	build_libro_cv_draft_bytes,
)

IVA_TASA = Decimal("0.19")
LCE_FACTOR_IVA_USO_COMUN = Decimal("0.60")
LCE_4811536_MOVIMIENTOS_ESPERADOS = 7


@dataclass(frozen=True, slots=True)
class MovimientoCompraCertificacion:
	tipo_documento: int
	folio: str
	observacion: str
	monto_exento: int = 0
	monto_afecto: int = 0
	iva_uso_comun: bool = False


@dataclass(frozen=True, slots=True)
class CalculoIvaUsoComun:
	tipo_documento: int
	folio: str
	monto_afecto: int
	iva: int
	factor: Decimal
	credito_iva_uso_comun: int


def movimientos_set_4811536() -> tuple[MovimientoCompraCertificacion, ...]:
	"""Movimientos del TXT oficial SII para atencion 4811536."""
	return (
		MovimientoCompraCertificacion(
			tipo_documento=30,
			folio="234",
			observacion="FACTURA DEL GIRO CON DERECHO A CREDITO",
			monto_afecto=63_287,
		),
		MovimientoCompraCertificacion(
			tipo_documento=33,
			folio="32",
			observacion="FACTURA DEL GIRO CON DERECHO A CREDITO",
			monto_exento=11_195,
			monto_afecto=13_026,
		),
		MovimientoCompraCertificacion(
			tipo_documento=30,
			folio="781",
			observacion="FACTURA CON IVA USO COMUN",
			monto_afecto=30_291,
			iva_uso_comun=True,
		),
		MovimientoCompraCertificacion(
			tipo_documento=60,
			folio="451",
			observacion="NOTA DE CREDITO POR DESCUENTO A FACTURA 234",
			monto_afecto=2_994,
		),
		MovimientoCompraCertificacion(
			tipo_documento=33,
			folio="67",
			observacion="ENTREGA GRATUITA DEL PROVEEDOR",
			monto_afecto=12_798,
		),
		MovimientoCompraCertificacion(
			tipo_documento=46,
			folio="9",
			observacion="COMPRA CON RETENCION TOTAL DEL IVA",
			monto_afecto=10_964,
		),
		MovimientoCompraCertificacion(
			tipo_documento=60,
			folio="211",
			observacion="NOTA DE CREDITO POR DESCUENTO FACTURA ELECTRONICA 32",
			monto_afecto=10_493,
		),
	)


def calculos_iva_uso_comun_4811536(
	movimientos: tuple[MovimientoCompraCertificacion, ...] | list[MovimientoCompraCertificacion],
	*,
	factor: Decimal = LCE_FACTOR_IVA_USO_COMUN,
) -> tuple[CalculoIvaUsoComun, ...]:
	"""Calcula y registra IVA uso comun con factor proporcional 0.60 para el LCE."""
	out: list[CalculoIvaUsoComun] = []
	for mov in movimientos:
		if not mov.iva_uso_comun:
			continue
		iva = _clp(Decimal(mov.monto_afecto) * IVA_TASA)
		out.append(
			CalculoIvaUsoComun(
				tipo_documento=mov.tipo_documento,
				folio=mov.folio,
				monto_afecto=mov.monto_afecto,
				iva=iva,
				factor=factor,
				credito_iva_uso_comun=_clp(Decimal(iva) * factor),
			)
		)
	return tuple(out)


def advertencias_lce_4811536(
	movimientos: tuple[MovimientoCompraCertificacion, ...] | list[MovimientoCompraCertificacion],
) -> list[str]:
	"""Advierte antes de generar/enviar LCE incompleto respecto del set 4811536."""
	if not movimientos:
		return ["LCE 4811536 incompleto: cargue movimientos de compra antes de generar el libro."]
	if len(movimientos) < LCE_4811536_MOVIMIENTOS_ESPERADOS:
		return [
			"LCE 4811536 incompleto: "
			f"se esperaban {LCE_4811536_MOVIMIENTOS_ESPERADOS} movimientos de compra y hay {len(movimientos)}."
		]
	if not calculos_iva_uso_comun_4811536(movimientos):
		return ["LCE 4811536 incompleto: falta movimiento marcado con IVA uso comun factor 0.60."]
	return []


def totales_periodo_set_4811536_compras() -> tuple[TotalesPeriodoLibroCV, ...]:
	"""Totales LibroCV desde movimientos oficiales 4811536."""
	movimientos = movimientos_set_4811536()
	return (
		_total_por_tipo(movimientos, 30),
		_total_por_tipo(movimientos, 33),
		_total_por_tipo(movimientos, 46),
		_total_por_tipo(movimientos, 60),
	)


def build_libro_compras_4811536_draft_bytes(
	*,
	rut_emisor_libro: str,
	rut_envia: str,
	periodo_tributario: str,
	fch_resol: str,
	nro_resol: int,
	tmst_firma: datetime | None = None,
	envio_libro_id: str = "LIBROCOMPRA",
	tipo_libro: str = "MENSUAL",
	tipo_envio: str = "TOTAL",
) -> bytes:
	"""Genera el XML `LibroCompraVenta` sin firma para la atencion 4811536."""
	car = CaratulaLibroCV(
		rut_emisor_libro=rut_emisor_libro.strip(),
		rut_envia=rut_envia.strip(),
		periodo_tributario=periodo_tributario.strip(),
		fch_resol=fch_resol.strip(),
		nro_resol=int(nro_resol),
		tipo_operacion="COMPRA",
		tipo_libro=tipo_libro.strip().upper(),
		tipo_envio=tipo_envio.strip().upper(),
	)
	return build_libro_cv_draft_bytes(
		car,
		list(totales_periodo_set_4811536_compras()),
		tmst_firma=(tmst_firma or datetime.now()).replace(microsecond=0),
		envio_libro_id=envio_libro_id.strip() or "LIBROCOMPRA",
	)


def _total_por_tipo(
	movimientos: tuple[MovimientoCompraCertificacion, ...],
	tipo_documento: int,
) -> TotalesPeriodoLibroCV:
	rows = [m for m in movimientos if m.tipo_documento == tipo_documento]
	neto = sum(m.monto_afecto for m in rows)
	exento = sum(m.monto_exento for m in rows)
	iva = _clp(Decimal(neto) * IVA_TASA)
	return TotalesPeriodoLibroCV(
		tpo_doc=tipo_documento,
		tot_doc=len(rows),
		tot_mnt_exe=exento,
		tot_mnt_neto=neto,
		tot_mnt_iva=iva,
		tot_mnt_total=exento + neto + iva,
	)


def _clp(value: Decimal) -> int:
	return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


__all__ = [
	"CalculoIvaUsoComun",
	"LCE_4811536_MOVIMIENTOS_ESPERADOS",
	"LCE_FACTOR_IVA_USO_COMUN",
	"MovimientoCompraCertificacion",
	"advertencias_lce_4811536",
	"build_libro_compras_4811536_draft_bytes",
	"calculos_iva_uso_comun_4811536",
	"movimientos_set_4811536",
	"totales_periodo_set_4811536_compras",
]
