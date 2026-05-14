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

## Set basico facturacion electronica (DTE 33, spike issue #54)

### Prioridad: aprobar Maullín antes de ERPNext / Sales Invoice

Objetivo: recibir **TrackID** y estado aceptable en **maullin** para el caso **4811534-1** (un DTE 33 en un `EnvioDTE`), y dejar evidencia en [whiteboard #54](https://github.com/barriofarmacl/whiteboard/issues/54). No requiere facturas cargadas en ERPNext.

**Orden sugerido**

1. **AUTORIZACION** SII con **TD=33** (CAF + `RSASK`), folio elegido dentro de `[D, H]`.
2. **PFX** del contribuyente (mismo RUT que usaras como **`RutEnvia`** si firma el emisor, o el RUT real del firmante según tu operacion).
3. Alineación **carátula**: `FchResol` y `NroResol` de la **resolución de facturación electrónica** vigente del emisor (no usar valores de prueba si el SII los rechaza). Pasarlos con `fch_resol` (YYYY-MM-DD) y `nro_resol` en el `execute`.
4. **Smoke sin red** (opcional): generar bytes del sobre y guardar XML para revisión local o portal SII de validación.

```bash
bench --site <sitio> execute \
  pagosbf.tests.certification.factura_set_basico_maullin.build_signed_envio_from_files \
  --kwargs "{'caf_xml_path': '/ruta/AUTORIZACION33.xml', 'pfx_path': '/ruta/cert.pfx', 'pfx_password': '***', 'folio': 1, 'fch_resol': '2026-04-30', 'nro_resol': 0, 'envia_rut_override': '76543210-K'}"
```

(Sustituir rutas, folio, resolución y RUT que firma; `nro_resol`/`fch_resol` deben ser los **reales** del emisor en certificación.)

5. **POST maullin** (requiere salida a Internet y certificado aceptado por el SII de certificación):

```bash
bench --site <sitio> execute \
  pagosbf.tests.certification.factura_set_basico_maullin.emitir_set_basico_a_maullin \
  --kwargs "{'caf_xml_path': '/ruta/AUTORIZACION33.xml', 'pfx_path': '/ruta/cert.pfx', 'pfx_password': '***', 'folio': 1, 'fch_resol': '2026-04-30', 'nro_resol': 0, 'envia_rut_override': '76543210-K'}"
```

6. Copiar en el comentario del issue **#54**: `track_id`, fragmento o XML de **estado** (`estado_xml`), y si hubo error la glosa/código devuelto por el SII.

**Notas**

- El DTE spike usa receptor **77777777-7** y glosa de ítems alineada al PDF del set; si tu instructivo de certificación exige otro RUT/datos de receptor para el número de atención **4811534**, habrá que ajustar el compositor (`SpikeFactura33Params`) en una iteración siguiente.
- Un solo envío con **varios** DTE 33 (casos 1–4) es el siguiente paso de producto; para **aprobar Maullín la primera vez** basta con **un** DTE bien formado y aceptado.

Referencia de código: ``pagosbf.tests.certification.factura_set_basico_maullin``.

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
