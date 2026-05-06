"""Cliente SII: semilla, token, envio DTE, consulta estado (SOAP + HTTP)."""

from __future__ import annotations

from dataclasses import dataclass

from zeep import Client
from zeep.transports import Transport

from pagosbf.pagosbf.dte.xml_signer import SigningMaterial, sign_sii_get_token_envelope

from .dte_upload import DteUploadResult, SIIUploadError, upload_envio_dte
from .retry import call_with_retry
from .rut import split_rut
from .sii_response_xml import SiiRespuesta, parse_respuesta_sii


class SIIClientError(Exception):
	"""Error de negocio o protocolo (ESTADO SII != 00)."""


@dataclass(frozen=True, slots=True)
class SIIClientConfig:
	url_semilla: str = "https://maullin.sii.cl/DTEWS/CrSeed.jws"
	url_token: str = "https://maullin.sii.cl/DTEWS/GetTokenFromSeed.jws"
	url_envio: str = "https://maullin.sii.cl/cgi_dte/UPL/DTEUpload"
	url_consulta: str = "https://maullin.sii.cl/DTEWS/QueryEstUp.jws"
	timeout_s: float = 30.0
	retries: int = 3


class SIIClient:
	"""Fachada de alto nivel (sin Frappe). Instanciable en tests o jobs."""

	def __init__(self, config: SIIClientConfig | None = None) -> None:
		self._cfg = config or SIIClientConfig()
		self._t = Transport(
			operation_timeout=self._cfg.timeout_s, timeout=self._cfg.timeout_s
		)
		self._cr_seed: Client | None = None
		self._get_token: Client | None = None
		self._q_est: Client | None = None

	def _c_seed(self) -> Client:
		if self._cr_seed is None:
			self._cr_seed = Client(
				f"{self._cfg.url_semilla}?WSDL", transport=self._t
			)
		return self._cr_seed

	def _c_tok(self) -> Client:
		if self._get_token is None:
			self._get_token = Client(
				f"{self._cfg.url_token}?WSDL", transport=self._t
			)
		return self._get_token

	def _c_est(self) -> Client:
		if self._q_est is None:
			self._q_est = Client(
				f"{self._cfg.url_consulta}?WSDL", transport=self._t
			)
		return self._q_est

	def get_raw_seed(self) -> str:
		"""SOAP `getSeed`, retorno crudo (XML)."""

		def _call() -> str:
			return str(self._c_seed().service.getSeed())

		return str(call_with_retry(_call, max_attempts=self._cfg.retries))

	def get_seed_respuesta(self) -> SiiRespuesta:
		"""Obtiene semilla; `ESTADO` ``00`` y `semilla` no vacia para continuar."""
		raw = self.get_raw_seed()
		return parse_respuesta_sii(raw)

	def require_semilla(self) -> str:
		"""Obtiene la semilla o levanta `SIIClientError` si SII responde error."""
		p = self.get_seed_respuesta()
		if p.estado != "00" or not p.semilla:
			raise SIIClientError(
				f"getSeed: ESTADO={p.estado!r} GLOSA={p.glosa!r} (sin semilla)"
			)
		return p.semilla

	def get_token_with_certificate(self, semilla: str, material: SigningMaterial) -> str:
		"""Firma `semilla` con PFX, llama `getToken` y retorna el token (string SII)."""
		psz = sign_sii_get_token_envelope(semilla, material)

		def _call() -> str:
			return str(self._c_tok().service.getToken(pszXml=psz))

		raw = str(call_with_retry(_call, max_attempts=self._cfg.retries))
		p = parse_respuesta_sii(raw)
		if p.estado != "00" or not p.token:
			raise SIIClientError(
				f"getToken: ESTADO={p.estado!r} GLOSA={p.glosa!r} (sin token)"
			)
		return p.token

	def get_semilla_y_token(
		self, material: SigningMaterial
	) -> tuple[str, str, str, str]:
		"""(semilla, token, raw_seed, raw_token) para registro/auditoria."""
		raw0 = self.get_raw_seed()
		p0 = parse_respuesta_sii(raw0)
		if p0.estado != "00" or not p0.semilla:
			raise SIIClientError(
				f"getSeed: ESTADO={p0.estado!r} GLOSA={p0.glosa!r} (sin semilla)"
			)
		sem = p0.semilla
		psz = sign_sii_get_token_envelope(sem, material)

		def _call() -> str:
			return str(self._c_tok().service.getToken(pszXml=psz))

		raw1 = str(call_with_retry(_call, max_attempts=self._cfg.retries))
		p1 = parse_respuesta_sii(raw1)
		if p1.estado != "00" or not p1.token:
			raise SIIClientError(
				f"getToken: ESTADO={p1.estado!r} GLOSA={p1.glosa!r} (sin token)"
			)
		return sem, p1.token, raw0, raw1

	def enviar_sobre(
		self,
		envio_bytes: bytes,
		token: str,
		rut_emisor: str,
	) -> DteUploadResult:
		"""POST multipart a `url_envio`."""
		return upload_envio_dte(
			self._cfg.url_envio,
			envio_bytes,
			rut_emisor=rut_emisor,
			token=token,
			timeout=self._cfg.timeout_s,
		)

	def consultar_estado(self, track_id: str, token: str, rut_emisor: str) -> str:
		"""SOAP `getEstUp`; retorno XML (string) tal cual SII."""
		rut, dv = split_rut(rut_emisor)
		# RUT 8 cifras en SOAP (SII acepta cuerpo sin padding en algunas rutas;
		# QueryEstUp manual: RUT contribuyente)
		rut8 = rut.zfill(8)

		def _call() -> str:
			return str(
				self._c_est().service.getEstUp(
					RutCompania=rut8, DvCompania=dv, TrackId=str(track_id), Token=token
				)
			)

		return str(call_with_retry(_call, max_attempts=self._cfg.retries))

	def consultar_estado_parseado(
		self, track_id: str, token: str, rut_emisor: str
	) -> SiiRespuesta:
		raw = self.consultar_estado(track_id, token, rut_emisor)
		return parse_respuesta_sii(raw)


__all__ = [
	"DteUploadResult",
	"SIIClient",
	"SIIClientConfig",
	"SIIClientError",
	"SIIUploadError",
]
