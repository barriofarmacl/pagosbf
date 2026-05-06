# E2E manual: POS Invoice, DTE Boleta 39 y SII

Objetivo: validar el camino **POS Invoice** con **boleta afecta (Tipo DTE 39)** antes del set formal de certificacion (100 casos): venta en POS con IVA, emision a SII, y revision de `DTE Boleta` + respuestas SII.

En `pagosbf`, el Tipo DTE se deriva del documento: **IVA cobrado > 0** implica **39**; sin IVA implica **41**. Este manual centra el flujo en **39**.

## 1. Prerrequisitos en el sitio

- **SII Configuration** completo: RUT emisor, razon, resolucion, **Certificado Digital** (PFX) valido, URLs maullin si certificas en ese ambiente.
- **CAF no agotado para 39** (obligatorio para esta prueba). Conviene tener tambien 41 si probareis exentos en otro momento.
- **ERPNext (Chile)**:
  - **Company** con impuestos Chile y plantillas de IVA coherentes (articulos que gravan IVA en POS).
  - **Item** de prueba con **impuesto / plantilla de impuestos** que en POS genere **IVA > 0** en la factura (no usar solo articulos exentos si el objetivo es 39).
  - **POS Profile** operativo (almacen, lista de precios, metodo de pago, cuenta efectivo/banco segun vuestro perfil).
  - **Customer** (o flujo POS que cree consumidor) segun useis caja registradora o factura nominativa.
- **Usuario** con permisos para **POS Invoice** (crear, enviar), lectura de **DTE Boleta** y uso de `emitir` si no sois Administrator.

Comprobar con:

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.run
```

En la salida JSON, `caf_39` debe ser **true** para esta E2E. Resolver todo lo que marque en `errores` antes de continuar.

## 2. Ruta minima: POS Invoice que dispara DTE 39

1. Abrir **POS** (o **POS Invoice** desde cuentas) con un perfil que permita facturar con IVA.
2. Agregar lineas con articulos **gravados** (que en el documento resulten en `Total Taxes and Charges` > 0). Verificar en el formulario antes de enviar:
   - **Net Total** > 0
   - **Total Taxes and Charges** > 0 (condicion necesaria para **39**)
   - **Grand Total** = neto + impuestos (coherente con lineas)
3. **Guardar** y **Enviar** (docstatus = 1). Anotar el `name` (p. ej. `ACC-PSINV-2026-00001`).

Comprobacion rapida (opcional). **`bench execute` no admite bloques Python con `import`**; usar ruta de funcion y `--args`:

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.check_pos_invoice_dte39_ready \
  --args '["ACC-PSINV-XXXXX"]'
```

(Sustituir el name; en JSON, `ok` debe ser true.) Para codigo libre, usar `bench --site <sitio> console`.

Si `total_taxes_and_charges` es 0, el sistema calculara **41**; ajustar articulos / plantilla de impuestos del Item o del perfil POS, no el codigo de `pagosbf`.

### Hook al enviar (opcional)

Si en **SII Configuration** esta activo **Encolar emision en submit** y hay certificado, al enviar la POS Invoice puede encolarse sola la emision. Para la primera prueba suele ser mas claro usar **emision sincrona** con `emitir` (siguiente seccion).

### Sales Invoice y consolidadas

- **Sales Invoice** no consolidada sigue pudiendo usarse con `emitir(sales_invoice=...)` como origen alternativo.
- **Sales Invoice consolidada** (`is_consolidated`): el hook de SI **no** encola emision para evitar doble timbre cuando la boleta ya salio por POS.

## 3. Emision: sincrona o en cola

### A) Sincrona (recomendado la primera vez, para ver error en el acto)

`bench --site` ya carga el sitio. Los helpers E2E ejecutan como **Administrator** (aptos para `bench execute` sin sesion web).

**POS Invoice hacia DTE 39:**

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_emitir_pos_invoice \
  --kwargs "{'pos_invoice': 'ACC-PSINV-XXXXX', 'en_background': 0}"
```

Si el CAF correcto no se resuelve solo, pasar el name del CAF 39 (mismo helper):

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_emitir_pos_invoice \
  --kwargs "{'pos_invoice': 'ACC-PSINV-XXXXX', 'caf': 'CAF-39-1-10', 'en_background': 0}"
```

**Sales Invoice (opcional):**

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_emitir_sales_invoice \
  --kwargs "{'sales_invoice': 'SINV-XXXXX', 'en_background': 0}"
```

**API** (sesion/cookie o token): `POST /api/method/pagosbf.pagosbf.api.boleta.emitir` con exactamente uno de `sales_invoice` o `pos_invoice`, mas `en_background`, opcional `caf`.

### B) En cola (`en_background=1`)

Misma llamada con `en_background=1`. Debe haber **worker** RQ en cola `default`. Respuesta tipica POS:

```text
{ "enqueued": true, "job": "...", "pos_invoice": "ACC-PSINV-..." }
```

## 4. Comprobaciones

| Que mirar | Criterio esperado (si SII acepta) |
|-----------|-----------------------------------|
| `DTE Boleta` | `tipo_dte` = **39**; enlace **POS Invoice** en `pos_invoice`; `sales_invoice` vacio |
| `estado_envio` | `ENVIADO` (o `RECHAZADO_LOCAL` con `error_log` legible) |
| `track_id` | Relleno tras envio exitoso |
| `DTE Respuesta SII` | Filas semilla, token, envio |
| XML | `xml_sobre_firmado` y DTE firmado si el envio completo fue exitoso |

Si `tipo_dte` sale **41**, revisar la POS Invoice origen: casi siempre falta IVA en el documento (`total_taxes_and_charges`).

### Consulta de estado SII (opcional, despues de TrackId)

```bash
bench --site <sitio> execute pagosbf.tests.certification.e2e_preflight.e2e_consultar_estado_dte \
  --args '["BOL-39-00001"]'
```

(Sustituir por el `name` real de `DTE Boleta`.)

## 5. Fallos habituales

- **CAF / Tipo DTE**: mensaje de conflicto entre CAF y TipoDTE 39; cargar o seleccionar CAF **39** y folios disponibles.
- **Rechazado local / XSD / TED**: `error_log` en `DTE Boleta`; revisar totales vs lineas, folio y CAF.
- **POS sin IVA**: documento valido para negocio pero mapea a **41**; corregir impuestos en Item / POS Profile / plantilla.
- **503 o timeout SII**: reintentar; revisar `DTE Respuesta SII` y conectividad al ambiente SII.
- **`getToken: ESTADO='10' GLOSA='Error Interno'`** (sin token): el SII rechazo la peticion de token tras **getSeed** OK. Revisar en orden: **certificado digital** (PFX vigente, password correcta en `Certificado Digital`), **RUT del firmante** alineado al certificado y al contribuyente en **SII Configuration** / portal SII (certificacion), que el certificado este **autorizado** para el ambiente **maullin** si corresponde, hora del servidor (skew), y reintentar (a veces fallo transitorio del servicio). No confundir con error de XSD del DTE (eso ya paso si llegaste a `get_semilla_y_token`).
- **`bench execute` + `NameError: name 'pagosbf' is not defined`**: aparece **después** de otra excepcion; es un efecto secundario del fallback de Frappe al evaluar el comando. El error real es la **primera** traza (`SIIClientError`, etc.).
- **Sin worker**: con `en_background=1`, el job no corre sin `bench worker` (o equivalente).
- **Permisos `emitir`**: lectura sobre la **POS Invoice** enviada y permisos sobre **DTE Boleta** segun usuario.

## 6. Cierre hacia set de 100 casos

Registrar en `verify-report.md` (fase 8): sitio, fecha, `ACC-PSINV-...`, `BOL-...` con **tipo_dte 39**, TrackId (o motivo de fallo), sync vs cola.

## 8. Nivel B: comprobante impreso (timbre / ticket / issue #53)

Objetivo: tras emision exitosa y criterio de estado acordado con el SII (p. ej. consulta **EPR** o regla de certificacion vigente), dejar **evidencia** de impresion en el issue whiteboard **#53** (PDF exportado o fotografia legible del ticket).

### Pasos

1. Completar secciones 1–4 de este manual para una **POS Invoice** con **DTE 39** y `DTE Boleta` en estado coherente con el criterio de aceptacion del equipo.
2. Opcional: verificar payload de impresion por API (sesion autenticada):

   `POST /api/method/pagosbf.pagosbf.api.boleta.datos_impresion_boleta_pos` con `pos_invoice=<name>`.

   Debe responder `ok: true`, `folio`, `track_id`, `ted_compact`, `ted_pdf417_payload` cuando existe DTE vinculado.
3. En Desk: abrir la **POS Invoice** y usar **Print** con el formato **POS Invoice Boleta SII** (app `barriofarma_app`). Confirmar que el PDF/preview muestra tipo DTE, folio, track, estado, bloque TED (resumen) y payload PDF417 (C14N).
4. Si la emision fue **asincrona** (`en_background` o cola en submit), el primer print puede mostrar mensaje de pendiente; ejecutar **consultar estado** cuando corresponda y **reimprimir**.
5. Adjuntar al issue #53: archivo de impresion o captura con datos del timbre visibles; referenciar `name` de POS Invoice y de `DTE Boleta`.

### Nota tecnica

Los campos Long Text `xml_dte`, `xml_dte_firmado`, `xml_sobre_firmado` en `DTE Boleta` llevan **`ignore_xss_filter`** para que Frappe no aplique `sanitize_html` al XML. Tras desplegar el cambio, ejecutar `bench migrate`. Filas antiguas con XML escapado siguen siendo legibles gracias al des-escape defensivo en `print_context`.

El Print Format usa la funcion Jinja global **`pos_invoice_sii_print_block(doc)`** (hook `jinja` en `barriofarma_app`), no `frappe.get_attr` dentro del HTML (el sandbox de impresion no lo expone). Tras cambiar `hooks.py` o el modulo de metodos, ejecutar **`bench --site <sitio> clear-cache`** y reiniciar procesos si hace falta. Si el formato se guardo antes en Desk con HTML antiguo, revisar que la plantilla contenga `pos_invoice_sii_print_block(doc)`.

## 7. RCOF (Consumo de Folios) despues del envio de boletas

El SII exige un **Resumen de Consumo de Folios** (`ConsumoFolios` / `DocumentoConsumoFolios`) por periodo, firmado con el certificado del representante (mismo criterio que el sobre **EnvioBOLETA**). En `pagosbf` esta el builder y la firma XMLDSig RSA-SHA1 (`sign_consumo_folios`); el XSD oficial esta en `pagosbf/public/xsd/consumo_folio/ConsumoFolio_v10.xsd`.

### Generacion offline (workspace `development/sii`)

Tras tener un **`envio_firmado.xml`** (sobre con las boletas ya timbradas), generar **`rcof_firmado.xml`**:

Desde el directorio `development/` del workspace. Con **pyenv**, `python3` puede ser el mismo
binario que el venv pero sin `sys.prefix` del bench (faltan `lxml`/`signxml`): el script se
re-lanza solo con `frappe-bench/env/bin/python`. Si aun asi falla, instalar deps en el venv
(`pip install -e apps/pagosbf` desde `frappe-bench`).

```bash
export PYTHONPATH=/ruta/frappe-bench/apps/pagosbf
../frappe-bench/env/bin/python sii/build_rcof_certificacion.py \
  --envio-xml development/sii/out_be_certificacion/envio_firmado.xml \
  --out development/sii/out_be_certificacion/rcof_firmado.xml \
  --rut-emisor 76957985-0 \
  --rut-envia 15437220-2 \
  --fch-resol 2026-04-30 \
  --nro-resol 0 \
  --fch-inicio 2026-05-03 \
  --fch-final 2026-05-03 \
  --sec-envio 1 \
  --pfx /ruta/al/certificado.pfx \
  --pfx-password "$CERT_PFX_PASSWORD"
```

- **`--fch-inicio` / `--fch-final`**: dia (o rango) del consumo que declara el resumen; deben ser coherentes con las **FchEmis** de las boletas agregadas desde el envio.
- **`--sec-envio`**: correlativo de envio del resumen (1 la primera vez; incrementar si el SII exige reenvio correccion).
- **`--tmst-firma-env`**: opcional; por defecto usa hora actual America/Santiago.

El script **agrega** montos y rangos de folio por **Tipo DTE** desde los `<DTE>` del envio (Totales dentro de **Encabezado**). Valida el XML firmado contra el XSD salvo `--skip-xsd`.

### Subida al SII

El envio automatico desde la app usa hoy **`DTEUpload`** para sobres de boleta; el **Consumo de Folios** en certificacion suele cargarse por **portal** (menu Consumo de folios / ambiente de certificacion) o por un endpoint distinto segun el manual tecnico vigente. Confirmar en la documentacion del postulante el CGI/SOAP correcto antes de automatizar.
