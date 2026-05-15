# Copyright (c) 2026, BarrioFarmacl and contributors
# For license information, please see license.txt

"""Dashboard: SI origen enlazado desde este documento (internal_links)."""

from frappe import _


def get_data():
	return {
		"internal_links": {
			"Sales Invoice": "sales_invoice",
		},
		"transactions": [
			{"label": _("Origen"), "items": ["Sales Invoice"]},
		],
	}
