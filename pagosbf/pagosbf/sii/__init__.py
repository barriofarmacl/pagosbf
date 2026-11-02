"""Cliente de red para servicios SII.

Boleta electronica produccion: REST api.sii.cl / rahue.sii.cl.
Factura y CGI historico: SOAP DTEWS + cgi_dte (maullin/palena).

No importar modulos con `import frappe` en el nivel de paquete: `sii_client`
puede probarse con mocks; el puente a DocTypes esta en `sii_frappe`
(`sii_client_from_sii_configuration`, `append_dte_respuesta_sii`).
"""
