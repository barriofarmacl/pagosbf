"""Modulos puros de construccion y firma de DTE Boleta (SII Chile).

Spec pagosbf-sii-boleta:
- `xml_builder` R4: construye XML de DTE 39/41 y valida contra XSD.
- `ted_generator` R6: arma el Timbre Electronico firmado con la clave del CAF.
- `xml_signer` R5: firma XMLDSig enveloped del DTE y del sobre con el PFX.

Ninguno de estos modulos depende de Frappe (ORM/DocType); reciben dataclasses
o dicts y retornan bytes/str. Esto permite tests unitarios deterministas sin
bench.

- `caf_parser` (fase 3): lee el XML de autorizacion SII (CAF + `RSASK`) a `CAFData`.
- `folio_policy` / `folio_allocator` (fase 3): reglas de cupo y asignacion
  atomica con `get_doc(..., for_update=True)`.
"""
