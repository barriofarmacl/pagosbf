"""Dataclasses puras que representan el dominio boleta antes de serializar.

Evita acoplar `xml_builder` y `ted_generator` a `frappe.model.document.Document`,
habilitando tests unitarios sin bench. Los adaptadores ERPNext -> estos tipos
viven en `pagosbf.api.boleta` (fase 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Emisor:
	rut: str  # formato 99999999-K
	razon_social: str
	giro: str
	direccion_origen: str
	comuna_origen: str
	resolucion_numero: int
	resolucion_fecha: date
	# Opcionales XSD BOLETADefType / Emisor (minOccurs 0)
	ciudad_origen: str | None = None
	cdg_sii_sucur: int | None = None  # CdgSIISucur entregado por el SII


@dataclass(frozen=True)
class Receptor:
	rut: str  # "66666666-6" para boleta nominativa o "66666666-6" anonimo segun normativa
	razon_social: str = ""


@dataclass(frozen=True)
class BoletaReferencia:
	"""Referencia opcional en boleta (Set prueba BE: CodRef SET + RazonRef CASO-n)."""

	nro_lin_ref: int = 1
	cod_ref: str | None = None  # max 18 (EnvioBOLETA)
	razon_ref: str | None = None  # max 90

	def validate(self) -> None:
		if self.nro_lin_ref < 1 or self.nro_lin_ref > 40:
			raise ValueError("BoletaReferencia.nro_lin_ref debe estar entre 1 y 40")
		if self.cod_ref is not None and len(self.cod_ref) > 18:
			raise ValueError("BoletaReferencia.cod_ref max 18 caracteres")
		if self.razon_ref is not None and len(self.razon_ref) > 90:
			raise ValueError("BoletaReferencia.razon_ref max 90 caracteres")
		if not (self.cod_ref or self.razon_ref):
			raise ValueError("BoletaReferencia requiere cod_ref y/o razon_ref")


@dataclass(frozen=True)
class DetalleBoleta:
	nro_lin_det: int
	nombre_item: str
	cantidad: Decimal
	precio_item: Decimal
	monto_item: Decimal
	indica_exento: bool = False  # True solo para tipo_dte=41 o items exentos
	unidad_medida: str | None = None  # UnmdItem XSD boleta, max 4 (ej. Kg)

	def validate(self) -> None:
		if self.cantidad <= 0:
			raise ValueError(f"DetalleBoleta.cantidad debe ser > 0 (linea {self.nro_lin_det})")
		if self.precio_item < 0:
			raise ValueError(f"DetalleBoleta.precio_item no puede ser negativo (linea {self.nro_lin_det})")
		if self.unidad_medida is not None and len(self.unidad_medida) > 4:
			raise ValueError(f"DetalleBoleta.unidad_medida max 4 caracteres (linea {self.nro_lin_det})")


@dataclass(frozen=True)
class TotalesBoleta:
	monto_neto: int
	iva: int
	monto_exento: int
	monto_total: int
	tasa_iva: Decimal = Decimal("19.0")

	def validate(self) -> None:
		if self.monto_total != self.monto_neto + self.iva + self.monto_exento:
			raise ValueError(
				f"Totales inconsistentes: total={self.monto_total} "
				f"!= neto({self.monto_neto}) + iva({self.iva}) + exento({self.monto_exento})"
			)


@dataclass(frozen=True)
class DTEBoletaData:
	tipo_dte: int  # 39 | 41
	folio: int
	fecha_emision: date
	emisor: Emisor
	receptor: Receptor
	detalles: tuple[DetalleBoleta, ...]
	totales: TotalesBoleta
	# IndServicio (obligatorio en BOLETADefType):
	#   1 = Boleta de Servicios Periodicos
	#   2 = Boleta de Servicios Periodicos Domiciliarios
	#   3 = Boleta de Venta y Servicios  (default farmacia retail)
	#   4 = Boleta de Exportacion
	ind_servicio: int = 3
	timestamp_firma: datetime = field(default_factory=datetime.now)
	referencias: tuple[BoletaReferencia, ...] = ()

	def validate(self) -> None:
		from .constants import VALID_TIPOS_DTE

		if self.tipo_dte not in VALID_TIPOS_DTE:
			raise ValueError(f"tipo_dte {self.tipo_dte} no es boleta (39/41)")
		if self.folio <= 0:
			raise ValueError("folio debe ser positivo")
		if not self.detalles:
			raise ValueError("DTE sin detalles")
		for d in self.detalles:
			d.validate()
		for r in self.referencias:
			r.validate()
		self.totales.validate()


@dataclass(frozen=True)
class CAFData:
	"""Representacion parseada del XML CAF del SII.

	Se construye en `pagosbf.dte.caf_parser` (fase 3). `ted_generator` solo
	consume esta estructura (inyeccion de dependencias).
	"""

	tipo_dte: int
	rango_desde: int
	rango_hasta: int
	rut_emisor: str
	razon_social_emisor: str
	fecha_autorizacion: date
	caf_xml_element_str: str  # bloque <CAF> serializado exactamente como lo entrego SII
	rsa_private_key_pem: bytes  # clave privada RSA para firmar el DD del TED
	rsa_public_key_modulus_b64: str  # M del bloque <RSAPK>
	rsa_public_key_exponent_b64: str  # E del bloque <RSAPK>
	idk: str  # Identificador de la llave (IDK)
