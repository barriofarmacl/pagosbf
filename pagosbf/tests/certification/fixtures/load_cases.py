# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Carga `manifest.json` y construye `DTEBoletaData` para el runner de certificacion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pagosbf.pagosbf.dte.types import BoletaReferencia, DetalleBoleta, DTEBoletaData, TotalesBoleta

_MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"


@dataclass(frozen=True)
class CertificationCase:
	case_id: str
	data: DTEBoletaData


def load_manifest_path(path: Path | None = None) -> dict:
	p = path or _MANIFEST_PATH
	with open(p, encoding="utf-8") as f:
		return json.load(f)


def iter_cases(
	emisor_factory,
	receptor_factory,
	fixed_date,
	fixed_ts: datetime,
	manifest_path: Path | None = None,
) -> tuple[CertificationCase, ...]:
	"""Construye casos desde manifest usando factories de emisor/receptor/fecha."""
	raw = load_manifest_path(manifest_path)
	version = raw.get("version")
	if version != 1:
		raise ValueError(f"manifest.json version no soportada: {version!r}")

	emisor = emisor_factory()
	receptor = receptor_factory()
	out: list[CertificationCase] = []

	for row in raw["cases"]:
		case_id = row["id"]
		tipo_dte = int(row["tipo_dte"])
		folio = int(row["folio"])
		ind_servicio = int(row.get("ind_servicio", 3))

		detalles = tuple(
			DetalleBoleta(
				nro_lin_det=int(d["nro_lin_det"]),
				nombre_item=str(d["nombre_item"]),
				cantidad=Decimal(str(d["cantidad"])),
				precio_item=Decimal(str(d["precio_item"])),
				monto_item=Decimal(str(d["monto_item"])),
				indica_exento=bool(d.get("indica_exento", False)),
				unidad_medida=(str(d["unidad_medida"]).strip()[:4] if d.get("unidad_medida") else None),
			)
			for d in row["detalles"]
		)

		referencias = tuple(
			BoletaReferencia(
				nro_lin_ref=int(r.get("nro_lin_ref", 1)),
				cod_ref=(str(r["cod_ref"]).strip() if r.get("cod_ref") else None),
				razon_ref=(str(r["razon_ref"]).strip() if r.get("razon_ref") else None),
			)
			for r in row.get("referencias") or []
		)

		t = row["totales"]
		totales = TotalesBoleta(
			monto_neto=int(t["monto_neto"]),
			iva=int(t["iva"]),
			monto_exento=int(t["monto_exento"]),
			monto_total=int(t["monto_total"]),
		)

		data = DTEBoletaData(
			tipo_dte=tipo_dte,
			folio=folio,
			fecha_emision=fixed_date,
			emisor=emisor,
			receptor=receptor,
			detalles=detalles,
			totales=totales,
			ind_servicio=ind_servicio,
			timestamp_firma=fixed_ts,
			referencias=referencias,
		)
		out.append(CertificationCase(case_id=case_id, data=data))

	return tuple(out)
