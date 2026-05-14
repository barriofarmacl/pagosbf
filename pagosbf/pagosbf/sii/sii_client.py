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


def _trunc_xml(s: str, max_len: int = 3600) -> str:
	t = (s or "").replace("\n", " ").strip()
	if len(t) > max_len:
		return f"{t[:max_len]}...(truncated {len(t) - max_len} chars)"
	return t


class SIIClientError(Exception):
	"""Error de negocio o protocolo (ESTADO SII != 00)."""

	def __init__(
		self,
		message: str,
		*,
		phase: str,
		raw_xml: str | None = None,
		raw_previous: str | None = None,
		endpoint: str | None = None,
		sii_estado: str | None = None,
		sii_glosa: str | None = None,
		semilla_obtenida: str | None = None,
	) -> None:
		super().__init__(message)
		self.phase = phase
		self.raw_xml = raw_xml
		self.raw_previous = raw_previous
		self.endpoint = endpoint
		self.sii_estado = sii_estado
		self.sii_glosa = sii_glosa
		self.semilla_obtenida = semilla_obtenida

	def __str__(self) -> str:
		parts: list[str] = [super().__str__()]
		if self.endpoint:
			parts.append(f"endpoint={self.endpoint!r}")
		if self.semilla_obtenida:
			parts.append(f"semilla_obtenida={self.semilla_obtenida!r}")
		if self.raw_xml:
			parts.append(f"raw_xml={_trunc_xml(self.raw_xml)!r}")
		return " | ".join(parts)


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
		raw = self.get_raw_seed()
		p = parse_respuesta_sii(raw)
		if p.estado != "00" or not p.semilla:
			raise SIIClientError(
				f"getSeed: ESTADO={p.estado!r} GLOSA={p.glosa!r} (sin semilla)",
				phase="getSeed",
				raw_xml=raw,
				endpoint=self._cfg.url_semilla,
				sii_estado=p.estado,
				sii_glosa=p.glosa,
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
				f"getToken: ESTADO={p.estado!r} GLOSA={p.glosa!r} (sin token)",
				phase="getToken",
				raw_xml=raw,
				endpoint=self._cfg.url_token,
				sii_estado=p.estado,
				sii_glosa=p.glosa,
				semilla_obtenida=semilla,
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
				f"getSeed: ESTADO={p0.estado!r} GLOSA={p0.glosa!r} (sin semilla)",
				phase="getSeed",
				raw_xml=raw0,
				endpoint=self._cfg.url_semilla,
				sii_estado=p0.estado,
				sii_glosa=p0.glosa,
			)
		sem = p0.semilla
		psz = sign_sii_get_token_envelope(sem, material)

		def _call() -> str:
			return str(self._c_tok().service.getToken(pszXml=psz))

		raw1 = str(call_with_retry(_call, max_attempts=self._cfg.retries))
		p1 = parse_respuesta_sii(raw1)
		if p1.estado != "00" or not p1.token:
			raise SIIClientError(
				f"getToken: ESTADO={p1.estado!r} GLOSA={p1.glosa!r} (sin token)",
				phase="getToken",
				raw_xml=raw1,
				raw_previous=raw0,
				endpoint=self._cfg.url_token,
				sii_estado=p1.estado,
				sii_glosa=p1.glosa,
				semilla_obtenida=sem,
			)
		return sem, p1.token, raw0, raw1

	def enviar_sobre(
		self,
		envio_bytes: bytes,
		token: str,
		rut_emisor: str,
		*,
		rut_digitador: str | None = None,
	) -> DteUploadResult:
		"""POST multipart a `url_envio`."""
		return upload_envio_dte(
			self._cfg.url_envio,
			envio_bytes,
			rut_emisor=rut_emisor,
			token=token,
			rut_digitador=rut_digitador,
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
