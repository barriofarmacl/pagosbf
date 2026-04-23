# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

import unittest

import pagosbf


class TestBootstrapSmoke(unittest.TestCase):
	def test_package_import_and_version(self):
		self.assertTrue(hasattr(pagosbf, "__version__"))
		self.assertIsInstance(pagosbf.__version__, str)
