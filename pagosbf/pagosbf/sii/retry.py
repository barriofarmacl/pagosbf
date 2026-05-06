"""Reintentos con backoff para llamadas a SII (5/10/20 s, max 3 intentos)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_BACKOFF = (5.0, 10.0, 20.0)
DEFAULT_MAX = 3


def call_with_retry(
	func: Callable[[], T],
	*,
	backoff_s: tuple[float, ...] = DEFAULT_BACKOFF,
	max_attempts: int = DEFAULT_MAX,
) -> T:
	"""Reintenta `func` ante fallos de transporte (5xx, timeout, corte, zeep)."""
	import requests
	from zeep.exceptions import TransportError

	last: BaseException | None = None
	for attempt in range(max_attempts):
		try:
			return func()
		except (TransportError, requests.RequestException, OSError) as exc:
			last = exc
			if attempt + 1 >= max_attempts:
				break
			time.sleep(backoff_s[min(attempt, len(backoff_s) - 1)])
	raise last  # type: ignore[misc]
