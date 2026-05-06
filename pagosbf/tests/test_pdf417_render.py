# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Tests unitarios del render PDF417 (TED payload)."""

from __future__ import annotations

import unittest

from pagosbf.pagosbf.boleta.pdf417_render import ted_payload_to_png_bytes


class TestPdf417Render(unittest.TestCase):
	def test_png_no_vacio_payload_mediano(self) -> None:
		payload = "<TED version=\"1.0\"><DD><RE>76000000-0</RE></DD></TED>" + ("X" * 200)
		out = ted_payload_to_png_bytes(payload)
		self.assertGreater(len(out), 200)
		self.assertTrue(out.startswith(b"\x89PNG"))

	def test_payload_vacio_falla(self) -> None:
		with self.assertRaises(ValueError):
			ted_payload_to_png_bytes("")


if __name__ == "__main__":
	unittest.main()
