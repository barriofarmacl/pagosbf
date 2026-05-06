# Certificacion SII Boleta (pagosbf)

Este directorio agrupa el **set de certificacion**: datos declarativos (`fixtures/manifest.json`), carga (`fixtures/load_cases.py`) y runner offline (`run_all.py`).

## Alcance del runner offline

`run_all.run` valida por cada fila del manifiesto:

1. `xml_builder.build_dte`
2. `ted_generator.build_signed_ted` con CAF sintetico (`dte_fixtures.synthetic_caf`)
3. `xml_builder.insert_ted` + `validate_dte_xml` (XSD composite boleta)

No llama al **SII** (no maullin, no EPR). Eso corresponde a **Verify / E2E manual** y queda documentado en `verify-report.md`.

## Ejecucion

Desde el bench (mismo patron que otros `execute`):

```bash
bench --site <sitio> execute pagosbf.tests.certification.run_all.run
```

Sin necesidad de emitir documentos reales; no consume folios.

## Preflight antes de pruebas contra SII

Antes de un E2E contra maullin o de cerrar el lote amplio de casos normativos:

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.run
```

Pasos humanos de una Sales Invoice + `emitir`: ver `E2E_MANUAL.md` en este mismo directorio.

## Manifiesto (`fixtures/manifest.json`)

- **`version`**: debe ser `1` para el cargador actual.
- **`cases`**: cada elemento define `id`, `tipo_dte` (39 o 41), `folio`, `ind_servicio`, `detalles`, `totales`.
- Cantidades y montos en detalle son **strings** compatibles con `Decimal`.

Para acercarse al **set oficial de ~100 escenarios** del SII: ir anadiendo filas al manifiesto (o partiendo matrices oficiales de certificacion) y volver a ejecutar el runner offline; conviene trazar en hoja de calculo el `id` con el codigo de escenario SII cuando lo tengais asignado.

## Pruebas automaticas

El test `tests/test_certification_offline.py` falla si alguna fila del manifiesto deja de pasar XSD.

```bash
bench --site <sitio> run-tests --app pagosbf --module pagosbf.tests.test_certification_offline
```
