# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

from pagosbf.tests.certification.run_all import run_offline_suite


class TestCertificationOffline(unittest.TestCase):
	def test_manifest_offline_suite_passes(self):
		out = run_offline_suite()
		self.assertEqual(out["fail_count"], 0, out.get("errors"))
		self.assertGreater(out["total"], 0)


if __name__ == "__main__":
	unittest.main()
