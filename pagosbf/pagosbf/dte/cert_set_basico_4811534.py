"""Datos del instructivo SII **Set Basico**, numero de atencion **4811534**.

Fuente: ``sii/SIISetDePruebas769579850.txt`` e instrucciones de construccion del SII.

- IVA 19%% sobre neto afecto: entero chileno ``int(round(neto * 19 / 100))``.
- Descuentos por linea: ``int(round(bruto * pct / 100))``; monto linea = bruto - descuento.
- Descuento global solo sobre items afectos (caso 4): mismo criterio de redondeo.

Receptores de facturas 33: RUT **distintos** por caso (requisito instructivo). Razones
sociales son glosa interna coherente con certificacion; el contribuyente debe usar
clientes existentes en su ambiente cuando el SII lo exija.

Referencias caratula envio: ``60803000-K`` (ver ``envio_builder.RUT_SII_CARATULA``).
"""

from __future__ import annotations

from dataclasses import dataclass

# Numero de atencion del set (encabezado instructivo).
SET_BASICO_NUMERO_ATENCION = "4811534"

# --- Textos exactos de items (orden y acentos segun TXT SII) ---
CASO_4811534_1_ID = "4811534-1"
CASO_4811534_1_LINEAS: tuple[tuple[str, int, int], ...] = (
	("Cajón AFECTO", 150, 2424),
	("Relleno AFECTO", 63, 4011),
)

CASO_4811534_2_LINEAS: tuple[tuple[str, int, int, float], ...] = (
	("Pañuelo AFECTO", 541, 4235, 7.0),
	("ITEM 2 AFECTO", 478, 3291, 16.0),
)

CASO_4811534_3_LINEAS: tuple[tuple[str, int, int, bool], ...] = (
	("Pintura B&W AFECTO", 41, 4949, False),
	("ITEM 2 AFECTO", 200, 3503, False),
	("ITEM 3 SERVICIO EXENTO", 1, 35048, True),
)

CASO_4811534_4_LINEAS: tuple[tuple[str, int, int, bool], ...] = (
	("ITEM 1 AFECTO", 276, 4155, False),
	("ITEM 2 AFECTO", 117, 4796, False),
	("ITEM 3 SERVICIO EXENTO", 2, 6806, True),
)

CASO_4811534_4_DESC_GLOBAL_AFECTO_PCT = 16.0

# NC devolucion parcial (caso 6): mismas lineas, PU y **porcentajes de descuento**
# que la factura caso 2 (7%% y 16%%). MontoItem = bruto - descuento por linea.
CASO_4811534_6_DEVOLUCION: tuple[tuple[str, int, int], ...] = (
	("Pañuelo AFECTO", 199, 4235),
	("ITEM 2 AFECTO", 324, 3291),
)


@dataclass(frozen=True, slots=True)
class ReceptorFacturaSet4811534:
	"""RUT y razon para un DTE 33 del set."""

	rut: str
	razon_social: str


# RUT distintos por factura (1..4). Formato DTE con guion y DV.
RECEPTOR_FACTURA_POR_CASO: dict[str, ReceptorFacturaSet4811534] = {
	"4811534-1": ReceptorFacturaSet4811534("77777777-7", "Receptor Certificacion SII"),
	"4811534-2": ReceptorFacturaSet4811534("12345678-5", "Receptor Certificacion Dos SPA"),
	"4811534-3": ReceptorFacturaSet4811534("66666666-6", "Receptor Certificacion Tres SPA"),
	"4811534-4": ReceptorFacturaSet4811534("13502949-5", "Receptor Certificacion Cuatro SPA"),
}

# Referencia a documento previo: misma razon social que la factura referenciada (NC/ND).
def receptor_para_caso_referenciado(caso_factura: str) -> ReceptorFacturaSet4811534:
	"""Receptor a usar en NC/ND que referencia una factura del set."""
	return RECEPTOR_FACTURA_POR_CASO[caso_factura]


def referencia_set_caso_razon(caso_id: str) -> str:
	"""Texto ``RazonRef`` para la primera linea de referencia (instructivo SET)."""
	return f"CASO {caso_id}"


# --- Funciones de totales (valores esperados en DTE) ---


def monto_linea_caso_4811534_1(line_index: int) -> int:
	_, qty, prc = CASO_4811534_1_LINEAS[line_index]
	return int(qty * prc)


def neto_total_caso_4811534_1() -> int:
	return sum(monto_linea_caso_4811534_1(i) for i in range(len(CASO_4811534_1_LINEAS)))


def iva_19_desde_neto_chile(neto: int) -> int:
	"""IVA 19%% en pesos enteros, redondeo estandar al entero mas cercano."""
	return int(round(neto * 19 / 100.0))


def totales_caso_4811534_1() -> tuple[int, int, int]:
	"""``(MntNeto, IVA, MntTotal)`` — sin exento."""
	n = neto_total_caso_4811534_1()
	iva = iva_19_desde_neto_chile(n)
	return n, iva, n + iva


def lineas_caso_4811534_2() -> list[tuple[int, int, int, float, int]]:
	"""Por linea: ``(qty, prc, bruto, pct_dscto, monto_neto_linea)``."""
	out: list[tuple[int, int, int, float, int]] = []
	for _nmb, qty, prc, pct in CASO_4811534_2_LINEAS:
		bruto = int(qty * prc)
		dscto = int(round(bruto * pct / 100.0))
		neto = bruto - dscto
		out.append((qty, prc, bruto, pct, neto))
	return out


def totales_caso_4811534_2() -> tuple[int, int, int]:
	"""``(MntNeto, IVA, MntTotal)`` — solo afectas."""
	lines = lineas_caso_4811534_2()
	n = sum(x[4] for x in lines)
	iva = iva_19_desde_neto_chile(n)
	return n, iva, n + iva


def lineas_caso_4811534_3() -> list[tuple[str, int, int, bool, int]]:
	"""``(nombre, qty, prc, exento, monto_linea)``."""
	out: list[tuple[str, int, int, bool, int]] = []
	for nmb, qty, prc, exe in CASO_4811534_3_LINEAS:
		out.append((nmb, qty, prc, exe, int(qty * prc)))
	return out


def totales_caso_4811534_3() -> tuple[int, int, int, int]:
	"""``(MntNeto, MntExe, IVA, MntTotal)``."""
	lines = lineas_caso_4811534_3()
	neto = sum(m for _, _, _, exe, m in lines if not exe)
	exe = sum(m for _, _, _, ex, m in lines if ex)
	iva = iva_19_desde_neto_chile(neto)
	return neto, exe, iva, neto + iva + exe


def lineas_caso_4811534_4() -> tuple[list[tuple[str, int, int, bool, int]], int]:
	"""``(lineas, desc_global_afecto)`` — lineas con montos antes del D/R global.

	El descuento global aplica solo al total afecto bruto (items no exentos).
	"""
	rows: list[tuple[str, int, int, bool, int]] = []
	bruto_afecto = 0
	for nmb, qty, prc, exe in CASO_4811534_4_LINEAS:
		m = int(qty * prc)
		rows.append((nmb, qty, prc, exe, m))
		if not exe:
			bruto_afecto += m
	dscto_glob = int(round(bruto_afecto * CASO_4811534_4_DESC_GLOBAL_AFECTO_PCT / 100.0))
	return rows, dscto_glob


def totales_caso_4811534_4() -> tuple[int, int, int, int]:
	"""``(MntNeto, MntExe, IVA, MntTotal)`` tras descuento global en afectos."""
	lines, dscto_glob = lineas_caso_4811534_4()
	bruto_afecto = sum(m for _, _, _, exe, m in lines if not exe)
	neto = bruto_afecto - dscto_glob
	exe = sum(m for _, _, _, ex, m in lines if ex)
	iva = iva_19_desde_neto_chile(neto)
	return neto, exe, iva, neto + iva + exe


def lineas_caso_4811534_6_nc() -> list[tuple[str, int, int, float, int, int, int]]:
	"""Devolucion caso 6 alineada a factura 2: ``(nmb, qty, prc, pct, bruto, dscto, neto)``."""
	out: list[tuple[str, int, int, float, int, int, int]] = []
	for (nmb_f, _qf, prc_f, pct), (nmb_d, qty_d, prc_d) in zip(
		CASO_4811534_2_LINEAS, CASO_4811534_6_DEVOLUCION, strict=True
	):
		if nmb_f != nmb_d or prc_f != prc_d:
			raise ValueError("Caso 6: linea de devolucion no coincide con caso 2")
		bruto = int(qty_d * prc_d)
		dscto = int(round(bruto * pct / 100.0))
		neto = bruto - dscto
		out.append((nmb_d, qty_d, prc_d, pct, bruto, dscto, neto))
	return out


def totales_caso_4811534_6_nc_devolucion() -> tuple[int, int, int]:
	"""NC caso 6 — neto por linea tras los mismos descuentos %% que la factura 2."""
	neto = sum(row[-1] for row in lineas_caso_4811534_6_nc())
	iva = iva_19_desde_neto_chile(neto)
	return neto, iva, neto + iva


def totales_caso_4811534_7_nc_anula() -> tuple[int, int, int, int]:
	"""Mismos totales que factura caso 3 (anulacion total)."""
	return totales_caso_4811534_3()
