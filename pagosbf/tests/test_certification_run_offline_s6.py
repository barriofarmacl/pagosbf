# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Spec S6: runner offline certificacion sin fallos (manifest obligatorio)."""

from __future__ import annotations

import unittest

from pagosbf.tests.certification.fixtures.load_cases import iter_cases
from pagosbf.tests.certification.run_all import run_offline_suite

from .dte_fixtures import FIXED_DATE, FIXED_TS, emisor, receptor


class TestCertificationOfflineS6(unittest.TestCase):
	def test_run_offline_suite_zero_failures(self) -> None:
		out = run_offline_suite()
		self.assertEqual(out["fail_count"], 0, out.get("errors"))
		cases = list(
			iter_cases(emisor, receptor, FIXED_DATE, FIXED_TS),
		)
		self.assertEqual(out["ok_count"], len(cases))
		self.assertEqual(out["total"], len(cases))
		for c in cases:
			self.assertIn(c.case_id, out["ok"])


if __name__ == "__main__":
	unittest.main()
