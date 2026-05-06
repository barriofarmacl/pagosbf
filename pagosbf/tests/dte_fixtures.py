# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Datos sinteticos para tests del paquete `pagosbf.pagosbf.dte` (sin CAF/FE real)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
	BestAvailableEncryption,
	Encoding,
	NoEncryption,
	PrivateFormat,
	pkcs12,
)
from cryptography.x509.oid import NameOID

from pagosbf.pagosbf.dte.types import CAFData, DetalleBoleta, DTEBoletaData, Emisor, Receptor, TotalesBoleta

FIXED_DATE = date(2026, 4, 24)
FIXED_TS = datetime(2026, 4, 24, 12, 0, 0)


def emisor() -> Emisor:
	return Emisor(
		rut="76000000-0",
		razon_social="Barrio Farma SpA",
		giro="Farmacia",
		direccion_origen="Av Siempreviva 742",
		comuna_origen="Santiago",
		resolucion_numero=80,
		resolucion_fecha=date(2020, 1, 1),
	)


def receptor() -> Receptor:
	return Receptor(rut="66666666-6", razon_social="Cliente Anonimo")


def dte_39() -> DTEBoletaData:
	return DTEBoletaData(
		tipo_dte=39,
		folio=1,
		fecha_emision=FIXED_DATE,
		emisor=emisor(),
		receptor=receptor(),
		detalles=(
			DetalleBoleta(
				nro_lin_det=1,
				nombre_item="Paracetamol 500mg",
				cantidad=Decimal("1"),
				precio_item=Decimal("1000"),
				monto_item=Decimal("1000"),
			),
		),
		totales=TotalesBoleta(monto_neto=840, iva=160, monto_exento=0, monto_total=1000),
		ind_servicio=3,
		timestamp_firma=FIXED_TS,
	)


def dte_41() -> DTEBoletaData:
	return DTEBoletaData(
		tipo_dte=41,
		folio=1,
		fecha_emision=FIXED_DATE,
		emisor=emisor(),
		receptor=receptor(),
		detalles=(
			DetalleBoleta(
				nro_lin_det=1,
				nombre_item="Libro exento",
				cantidad=Decimal("1"),
				precio_item=Decimal("5000"),
				monto_item=Decimal("5000"),
			),
		),
		totales=TotalesBoleta(monto_neto=0, iva=0, monto_exento=5000, monto_total=5000),
		ind_servicio=3,
		timestamp_firma=FIXED_TS,
	)


def caf_block_xml(tipo_dte: int) -> str:
	"""Bloque CAF minimo que parsea `lxml` (no valido SII, suficiente para unit tests)."""
	return (
		f'<CAF version="1.0">'
		f'<DA><RE>76000000-0</RE><RS>Barrio Farma</RS>'
		f'<TD>{tipo_dte}</TD><RNG><D>1</D><H>50</H></RNG><FA>2026-01-01</FA>'
		f'<RSAPK><M>AAAA</M><E>AQAB</E></RSAPK><IDK>100</IDK></DA>'
		f'<FRMA algoritmo="SHA1withRSA">ZmFrZQ==</FRMA></CAF>'
	)


def synthetic_caf(tipo_dte: int) -> CAFData:
	key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
	pem = key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
	return CAFData(
		tipo_dte=tipo_dte,
		rango_desde=1,
		rango_hasta=50,
		rut_emisor="76000000-0",
		razon_social_emisor="Barrio Farma",
		fecha_autorizacion=date(2026, 1, 1),
		caf_xml_element_str=caf_block_xml(tipo_dte),
		rsa_private_key_pem=pem,
		rsa_public_key_modulus_b64="AAAA",
		rsa_public_key_exponent_b64="AQAB",
		idk="100",
	)


def pfx_for_tests(password: str = "test1234") -> bytes:
	"""Genera un PKCS#12 con RSA 2048 y certificado self-signed (smoke, no SII)."""
	pfx_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pagosbf-dte-test")])
	cert = (
		x509.CertificateBuilder()
		.subject_name(name)
		.issuer_name(name)
		.public_key(pfx_key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(datetime(2026, 1, 1))
		.not_valid_after(datetime(2030, 1, 1))
		.sign(pfx_key, hashes.SHA256())
	)
	return pkcs12.serialize_key_and_certificates(
		name=b"test",
		key=pfx_key,
		cert=cert,
		cas=None,
		encryption_algorithm=BestAvailableEncryption(password.encode("utf-8")),
	)
