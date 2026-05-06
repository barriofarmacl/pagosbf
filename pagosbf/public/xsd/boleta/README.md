# XSD oficiales SII para Boleta Electronica

Archivos copiados desde los paquetes oficiales publicados en
https://www.sii.cl/factura_electronica/formato_boleta_elec.htm

| Archivo | Origen |
| --- | --- |
| `EnvioBOLETA_v11.xsd` | `schema_envio_bol.zip` / `schema_envio_bol_sii.zip` |
| `DTE_v10.xsd` | `schema_dte.zip` (sin uso directo para boletas, ver abajo) |
| `SiiTypes_v10.xsd` | `schema_dte.zip` |
| `xmldsignature_v10.xsd` | `schema_dte.zip` |

## Validacion local: composite en memoria

`pagosbf.dte.xml_builder._build_boleta_schema_tree()` arma un XSD composite
en memoria a partir de los anteriores para validar `<DTE>` boleta
(tipos 39 y 41) **sin escribir nada al disco**. El composite:

1. Parsea `EnvioBOLETA_v11.xsd` (que define `BOLETADefType`).
2. Mergea las definiciones de `SiiTypes_v10.xsd` que falten, preservando
   las locales de `EnvioBOLETA` cuando hay colision (por ejemplo `DTEType`).
3. Declara `<xs:element name="DTE" type="SiiDte:BOLETADefType"/>` como root
   para poder validar un DTE standalone (no envuelto en `<EnvioBOLETA>`).
4. Marca `ds:Signature` como `minOccurs=0`, habilitando validacion
   pre-firma (ver "Validacion pre vs post firma" abajo).

## Quirks conocidos que patcheamos

### 1. `DescuentoPct` con `minInclusive=0.00`

`EnvioBOLETA_v11.xsd` lineas 678 y 700 restringen `SiiDte:PctType`
(cuya base tiene `minInclusive=0.01`) con `minInclusive=0.00`. Esto es
invalido por XSD y `lxml.etree.XMLSchema` rechaza la compilacion con
`XMLSchemaParseError`. Es un defecto documentado en la comunidad Chile DTE
(OpenKM, facturacionelectronica.cl).

Mitigacion: el loader en memoria reescribe ambos facets a `0.01`. Efecto
operativo: si se necesita emitir un descuento porcentual, el valor minimo
local es `0.01%` (despreciable).

### 2. `DTE_v10.xsd` NO define boletas

`DTE_v10.xsd` enumera tipos 33/34/46/52/56/61 (factura y notas). **No sirve
para validar boletas 39/41**. La definicion `BOLETADefType` vive dentro de
`EnvioBOLETA_v11.xsd`; por eso el composite parte de alli, no de
`DTE_v10.xsd`. El archivo queda en el repo como referencia.

### 3. Firma XMLDSig (`xmldsignature_v10.xsd`)

El XSD del manual fija para cada ``Signature`` (incluida la del ``Documento`` del
DTE y la del sobre): ``CanonicalizationMethod`` =
``http://www.w3.org/TR/2001/REC-xml-c14n-20010315``, una sola ``Transform``
``enveloped-signature`` en ``Reference``, y ``KeyInfo`` con ``KeyValue`` antes de
``X509Data``. Usar ``xml-exc-c14n`` en ``SignedInfo`` o una segunda ``Transform``
provoca errores **cvc-complex-type** en la validacion XSD del portal de carga.

``pagosbf.dte.xml_signer`` aplica **el mismo perfil** en ``sign_dte``,
``sign_envio_boleta`` y ``sign_sii_get_token_envelope``.

## Validacion pre vs post firma

`pagosbf.dte.xml_builder.validate_dte_xml()`:
- Debe llamarse **antes** de firmar el documento (para detectar bugs de construccion).
- Correrlo **despues** de firmar puede rechazar por restricciones del composite XSD
  sobre `Signature`; no usar como gate automatico sobre XML ya firmado para envio.

## No hay validacion local del sobre `<EnvioBOLETA>`

Por los mismos quirks, la validacion del sobre se delega al SII. Al cliente
`pagosbf.dte.sii_client` (fase 4) le corresponde capturar `EstadoEnvio` y
`EstadoDTE` en el DocType `DTE Respuesta SII` para auditoria.
