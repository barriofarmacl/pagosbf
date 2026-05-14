"""Tipos puros para construir Factura Electronica SII tipo 33."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from pagosbf.pagosbf.dte.constants import (
	TIPO_DTE_FACTURA_ELECTRONICA,
	TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
	TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
)
from pagosbf.pagosbf.dte.types import Emisor, Receptor

TIPOS_DTE_FACTURACION_ERP = frozenset(
	{
		TIPO_DTE_FACTURA_ELECTRONICA,
		TIPO_DTE_NOTA_CREDITO_ELECTRONICA,
		TIPO_DTE_NOTA_DEBITO_ELECTRONICA,
	}
)


@dataclass(frozen=True)
class DetalleFactura:
	nro_lin_det: int
	nombre_item: str
	cantidad: Decimal
	precio_item: Decimal
	monto_item: int
	descuento_pct: Decimal | None = None
	descuento_monto: int | None = None
	indica_exento: bool = False
	unidad_medida: str | None = None

	def validate(self) -> None:
		if self.nro_lin_det < 1:
			raise ValueError("DetalleFactura.nro_lin_det debe ser positivo")
		if self.cantidad <= 0:
			raise ValueError(f"DetalleFactura.cantidad debe ser > 0 (linea {self.nro_lin_det})")
		if self.precio_item < 0:
			raise ValueError(f"DetalleFactura.precio_item no puede ser negativo (linea {self.nro_lin_det})")
		if self.monto_item < 0:
			raise ValueError(f"DetalleFactura.monto_item no puede ser negativo (linea {self.nro_lin_det})")


@dataclass(frozen=True)
class TotalesFactura:
	monto_neto: int
	iva: int
	monto_exento: int
	monto_total: int
	tasa_iva: Decimal = Decimal("19.00")

	def validate(self) -> None:
		if self.monto_total != self.monto_neto + self.iva + self.monto_exento:
			raise ValueError(
				f"Totales factura inconsistentes: total={self.monto_total} "
				f"!= neto({self.monto_neto}) + iva({self.iva}) + exento({self.monto_exento})"
			)


@dataclass(frozen=True)
class ReferenciaFactura:
	nro_lin_ref: int
	tpo_doc_ref: str
	folio_ref: str
	fecha_ref: date
	cod_ref: int | None = None
	razon_ref: str | None = None


@dataclass(frozen=True)
class Factura33Data:
	tipo_dte: int
	folio: int
	fecha_emision: date
	emisor: Emisor
	receptor: Receptor
	detalles: tuple[DetalleFactura, ...]
	totales: TotalesFactura
	acteco: str | None = None
	timestamp_firma: datetime = field(default_factory=datetime.now)
	referencias: tuple[ReferenciaFactura, ...] = ()

	def validate(self) -> None:
		if self.tipo_dte not in TIPOS_DTE_FACTURACION_ERP:
			raise ValueError("Factura33Data.tipo_dte debe ser 33, 61 o 56")
		if self.folio <= 0:
			raise ValueError("Factura33Data.folio debe ser positivo")
		if not self.detalles:
			raise ValueError("Factura33Data requiere al menos un detalle")
		for detalle in self.detalles:
			detalle.validate()
		self.totales.validate()


__all__ = [
	"DetalleFactura",
	"Factura33Data",
	"ReferenciaFactura",
	"TIPOS_DTE_FACTURACION_ERP",
	"TotalesFactura",
]
