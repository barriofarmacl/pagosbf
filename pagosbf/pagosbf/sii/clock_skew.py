# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Diagnóstico opcional de desfase de reloj vs referencia (SII / semilla-token).

Ejemplo::

	bench --site <sitio> execute pagosbf.pagosbf.sii.clock_skew.diagnostic

No invoca CrSeed/GetToken; compara reloj local con API pública o cabecera ``Date`` de maullin.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime


def _unix_from_http_date_header(url: str, timeout: float = 15) -> int | None:
	"""Lee cabecera Date de una respuesta HTTP y devuelve unix UTC."""
	try:
		req = urllib.request.Request(
			url,
			method="HEAD",
			headers={"User-Agent": "pagosbf-clock-skew/1.0"},
		)
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			ds = resp.headers.get("Date")
		if not ds:
			return None
		dt = parsedate_to_datetime(ds)
		if dt is None:
			return None
		return int(dt.timestamp())
	except (urllib.error.URLError, TimeoutError, OSError, TypeError, ValueError):
		return None


def _unix_from_worldtimeapi(timeout: float = 15) -> int | None:
	url = "https://worldtimeapi.org/api/timezone/America/Santiago"
	try:
		req = urllib.request.Request(
			url,
			headers={"User-Agent": "pagosbf-clock-skew/1.0", "Accept": "application/json"},
			method="GET",
		)
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			payload = json.loads(resp.read().decode("utf-8"))
		return int(payload["unixtime"])
	except (urllib.error.URLError, json.JSONDecodeError, KeyError, TimeoutError, OSError):
		return None


def diagnostic(limit_seconds: int = 120) -> str:
	"""JSON con skew local vs referencia (API Chile o Date HTTP maullin).

	Args:
	    limit_seconds: umbral de advertencia (valor absoluto de skew).

	Returns:
	    String JSON formateado.
	"""
	local = int(time.time())
	remote = _unix_from_worldtimeapi()
	source = "worldtimeapi.org America/Santiago"
	if remote is None:
		remote = _unix_from_http_date_header("https://maullin.sii.cl/")
		source = "HEAD Date https://maullin.sii.cl/"
	if remote is None:
		return json.dumps(
			{
				"ok": False,
				"local_unix": local,
				"error": "No se pudo obtener hora de referencia (API ni maullin).",
				"hint": "Revise red/firewall. En host: scripts/check_time_skew_sii.sh o NTP/chrony. "
				"Ver .cursor/docs/devops/sii_contenedor_sincronia_horaria.md",
			},
			indent=2,
			ensure_ascii=False,
		)
	skew = int(remote - local)
	out: dict = {
		"ok": abs(skew) <= int(limit_seconds),
		"local_unix": local,
		"reference_unix": remote,
		"reference_source": source,
		"skew_seconds": skew,
		"limit_seconds": int(limit_seconds),
	}
	if not out["ok"]:
		out["mensaje"] = (
			"Desfase alto vs referencia. Sincronice NTP o reinicie WSL/Docker. "
			"Ver .cursor/docs/devops/sii_contenedor_sincronia_horaria.md"
		)
	return json.dumps(out, indent=2, ensure_ascii=False)


__all__ = ["diagnostic"]
