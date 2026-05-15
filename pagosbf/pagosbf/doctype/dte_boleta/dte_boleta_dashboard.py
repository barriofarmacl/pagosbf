# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Dashboard: origen de la boleta es un Link en este documento, no en SI/PI."""

from frappe import _


def get_data():
	return {
		"internal_links": {
			"Sales Invoice": "sales_invoice",
			"POS Invoice": "pos_invoice",
		},
		"transactions": [
			{"label": _("Origen"), "items": ["Sales Invoice", "POS Invoice"]},
		],
	}
