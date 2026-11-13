# Copyright (c) 2026, hari and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TradeContract(Document):
    def validate(self):
        self.set_party_details()
        self.validate_dates()
        self.balance_qty = (self.contract_qty or 0) - (self.shipped_qty or 0)

    def set_party_details(self):
        self.party_type = "Supplier" if self.contract_type == "Purchase" else "Customer"
        name_field = "supplier_name" if self.party_type == "Supplier" else "customer_name"
        self.party_name = frappe.db.get_value(self.party_type, self.party, name_field)

    def validate_dates(self):
        if self.shipment_from and self.shipment_to and self.shipment_to < self.shipment_from:
            frappe.throw(_("Shipment To cannot be before Shipment From"))

    def on_submit(self):
        self.db_set("status", "Open")

    def on_cancel(self):
        self.db_set("status", "Closed")
