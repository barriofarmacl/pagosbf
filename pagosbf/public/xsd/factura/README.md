# XSD oficiales SII — Documentos tributarios genericos (factura, NC, ND, etc.)

Paquete **`schema_dte.zip`** del SII (mismo conjunto que describe el portal para DTE
**33, 34, 46, 52, 56, 61**, etc.). **No** es el paquete de **boleta** (`EnvioBOLETA`).

## Origen

| Campo | Valor |
|-------|--------|
| URL | https://www.sii.cl/factura_electronica/factura_mercado/schema_dte.zip |
| Descarga (spike) | 2026-05-06; respuesta HTTP `Last-Modified: Fri, 20 Feb 2026 13:53:27 GMT` |

## Archivos en este directorio

| Archivo | Rol |
|---------|-----|
| `EnvioDTE_v10.xsd` | Raiz **`EnvioDTE`** > `SetDTE` > `Caratula` + `DTE` para **envio multipart** estandar (`DTEUpload`). |
| `DTE_v10.xsd` | Definicion de **`DTE` / `Documento`** para tipos de DTE incluidos en formato electronico (incluye **33**). |
| `SiiTypes_v10.xsd` | Tipos compartidos. |
| `xmldsignature_v10.xsd` | XMLDSig (perfil alineado a `xmldsignature_v10` en boleta). |

## Conclusion spike (ADR-F3)

- El **sobre** para factura electronica y derivados **NO** es `EnvioBOLETA_v11.xsd`: es **`EnvioDTE`** segun `EnvioDTE_v10.xsd`.
- El mismo endpoint **`DTEUpload`** (maullin/palena) recibe el multipart con este XML firmado como sobre (comportamiento estandar integracion SII).
- **`DTE_v10.xsd` en `boleta/` puede diferir** del de este zip (versiones distintas); para validar o construir **33/61/56** MUST usarse el set bajo **`factura/`** para evitar drift.

## Mantenimiento

Ante cambios del SII: volver a descargar `schema_dte.zip`, reemplazar los cuatro archivos y ejecutar tests XSD afectados.

## Referencias

- Tecnicas SII: https://www.sii.cl/factura_electronica/tecnica.htm
- README boleta (solo 39/41): `../boleta/README.md`
