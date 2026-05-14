# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""RUT digitador desde subject X.509 (sin depender de rut_firmante en DocType)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from pagosbf.pagosbf.boleta.cert_utils import rut_from_certificate_subject


def _self_signed_cert(*attrs: tuple[x509.ObjectIdentifier, str]) -> x509.Certificate:
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	subject = issuer = x509.Name([x509.NameAttribute(oid, val) for oid, val in attrs])
	now = datetime.now(timezone.utc)
	return (
		x509.CertificateBuilder()
		.subject_name(subject)
		.issuer_name(issuer)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(now)
		.not_valid_after(now + timedelta(days=1))
		.sign(key, hashes.SHA256())
	)


class TestRutFromCertificateSubject(unittest.TestCase):
	def test_serial_number_plain(self) -> None:
		c = _self_signed_cert((NameOID.SERIAL_NUMBER, "15437220-2"))
		self.assertEqual(rut_from_certificate_subject(c), "15437220-2")

	def test_serial_number_run_prefix(self) -> None:
		c = _self_signed_cert((NameOID.SERIAL_NUMBER, "RUN 15437220-2"))
		self.assertEqual(rut_from_certificate_subject(c), "15437220-2")

	def test_common_name_embedded(self) -> None:
		c = _self_signed_cert(
			(NameOID.COUNTRY_NAME, "CL"),
			(NameOID.COMMON_NAME, "REPRESENTANTE LEGAL 76000000-0"),
		)
		self.assertEqual(rut_from_certificate_subject(c), "76000000-0")

	def test_no_rut_returns_none(self) -> None:
		c = _self_signed_cert((NameOID.COMMON_NAME, "SIN RUT AQUI"))
		self.assertIsNone(rut_from_certificate_subject(c))
