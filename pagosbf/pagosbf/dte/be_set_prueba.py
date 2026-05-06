# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Datos DTE tipo 39 para el set de prueba BE del SII (Boleta Electronica VyS).

Montos del cuadro oficial: precio unitario **con IVA** (bruto). Nombres de items
alineados a `Set Prueba BE.txt` (sin tildes en el texto fuente).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from pagosbf.pagosbf.dte import constants
from pagosbf.pagosbf.dte.types import BoletaReferencia, DetalleBoleta, DTEBoletaData, Emisor, Receptor, TotalesBoleta

_RECEPTOR_BOLETA = Receptor(rut="77777777-7", razon_social="")


def _neto_desde_bruto(bruto: int) -> int:
	return int(
		(Decimal(bruto) / Decimal("1.19")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
	)


def _totales_solo_afecto(brutos_linea: list[int]) -> TotalesBoleta:
	monto_neto = sum(_neto_desde_bruto(b) for b in brutos_linea)
	monto_total = sum(brutos_linea)
	iva = monto_total - monto_neto
	t = TotalesBoleta(
		monto_neto=monto_neto,
		iva=iva,
		monto_exento=0,
		monto_total=monto_total,
	)
	t.validate()
	return t


def _det_afecto(
	nro: int,
	nombre: str,
	cantidad: Decimal,
	bruto_linea: int,
) -> DetalleBoleta:
	m = Decimal(bruto_linea)
	q = cantidad
	prc = (m / q).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return DetalleBoleta(
		nro_lin_det=nro,
		nombre_item=nombre,
		cantidad=q,
		precio_item=prc,
		monto_item=m,
		indica_exento=False,
	)


def _det_exento(nro: int, nombre: str, cantidad: Decimal, bruto_linea: int) -> DetalleBoleta:
	m = Decimal(bruto_linea)
	q = cantidad
	prc = (m / q).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return DetalleBoleta(
		nro_lin_det=nro,
		nombre_item=nombre,
		cantidad=q,
		precio_item=prc,
		monto_item=m,
		indica_exento=True,
	)


def be_set_prueba_dte_data(
	caso: int,
	*,
	emisor: Emisor,
	folio: int,
	fecha_emision: date,
	timestamp_firma: datetime,
) -> DTEBoletaData:
	"""Construye `DTEBoletaData` para CASO-1 .. CASO-5 del set de prueba BE."""
	ref = (BoletaReferencia(nro_lin_ref=1, cod_ref="SET", razon_ref=f"CASO-{caso}"),)

	if caso == 1:
		brutos = [19900, 9900]
		detalles = (
			_det_afecto(1, "Cambio de aceite", Decimal("1"), brutos[0]),
			_det_afecto(2, "Alineacion y balanceo", Decimal("1"), brutos[1]),
		)
		tot = _totales_solo_afecto(brutos)
	elif caso == 2:
		brutos = [17 * 120]
		detalles = (_det_afecto(1, "Papel de regalo", Decimal("17"), brutos[0]),)
		tot = _totales_solo_afecto(brutos)
	elif caso == 3:
		brutos = [2 * 1500, 2 * 550]
		detalles = (
			_det_afecto(1, "Sandwic", Decimal("2"), brutos[0]),
			_det_afecto(2, "Bebida", Decimal("2"), brutos[1]),
		)
		tot = _totales_solo_afecto(brutos)
	elif caso == 4:
		br_afecto = 8 * 1590
		br_exento = 2 * 1000
		monto_neto = _neto_desde_bruto(br_afecto)
		monto_total = br_afecto + br_exento
		iva = br_afecto - monto_neto
		tot = TotalesBoleta(
			monto_neto=monto_neto,
			iva=iva,
			monto_exento=br_exento,
			monto_total=monto_total,
		)
		tot.validate()
		detalles = (
			_det_afecto(1, "item afecto 1", Decimal("8"), br_afecto),
			_det_exento(2, "item exento 2", Decimal("2"), br_exento),
		)
	elif caso == 5:
		brutos = [5 * 700]
		detalles = (
			DetalleBoleta(
				nro_lin_det=1,
				nombre_item="Arroz",
				cantidad=Decimal("5"),
				precio_item=Decimal("700"),
				monto_item=Decimal(brutos[0]),
				indica_exento=False,
				unidad_medida="Kg",
			),
		)
		tot = _totales_solo_afecto(brutos)
	else:
		raise ValueError(f"caso debe ser 1..5, recibido: {caso}")

	data = DTEBoletaData(
		tipo_dte=constants.TIPO_DTE_BOLETA_AFECTA,
		folio=folio,
		fecha_emision=fecha_emision,
		emisor=emisor,
		receptor=_RECEPTOR_BOLETA,
		detalles=detalles,
		totales=tot,
		ind_servicio=3,
		timestamp_firma=timestamp_firma,
		referencias=ref,
	)
	data.validate()
	return data


__all__ = ["be_set_prueba_dte_data"]
