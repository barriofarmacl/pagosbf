# PagosBF

Capa de pagos Chile para el ecosistema Barriofarma. App Frappe independiente; **no** modifica `erpnext` ni `barriofarma_app`. Integracion cruzada solo via hooks o APIs (`@frappe.whitelist()`), sin imports Python directos desde `barriofarma_app`.

**Trazabilidad:** [whiteboard #51](https://github.com/barriofarmacl/whiteboard/issues/51)  
**SDD:** change `pagosbf-bootstrap` en el repo de metodologia / workspace Barriofarma.

## Alcance actual (bootstrap)

- Estructura Frappe minima y `required_apps = ["frappe", "erpnext"]`.
- Sin emision/recepcion SII, sin CAF, sin DocTypes DTE en esta iteracion.

**Siguiente change:** `pagosbf-sii-boleta-certificacion` (boleta electronica 39/41, ambiente certificacion).

## Instalacion

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/barriofarmacl/pagosbf.git --branch develop
bench --site YOUR_SITE install-app pagosbf
```

Desarrollo local con el repo ya clonado en `apps/pagosbf`:

```bash
bench --site YOUR_SITE install-app pagosbf
```

## Desarrollo

Pre-commit (ruff, eslint, etc.):

```bash
cd apps/pagosbf
pre-commit install
```

Chequeo de aislamiento (R2): el script `scripts/check_no_barriofarma_imports.sh` falla si aparecen imports directos a `barriofarma_app` bajo `pagosbf/**/*.py`.

## Licencia

MIT (ver `LICENSE` y `license.txt`).
