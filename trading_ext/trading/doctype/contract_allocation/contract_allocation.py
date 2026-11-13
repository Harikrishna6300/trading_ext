# Copyright (c) 2026, hari and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ContractAllocation(Document):
    def validate(self):
        self.validate_contracts()
        self.validate_qty()
        self.margin_per_mt = (self.sell_price or 0) - (self.buy_price or 0)
        self.expected_margin = self.margin_per_mt * (self.allocated_qty or 0)

    def validate_contracts(self):
        sc = frappe.get_doc("Trade Contract", self.sales_contract)
        pc = frappe.get_doc("Trade Contract", self.purchase_contract)

        if sc.contract_type != "Sales":
            frappe.throw(_("{0} is not a Sales contract").format(sc.name))
        if pc.contract_type != "Purchase":
            frappe.throw(_("{0} is not a Purchase contract").format(pc.name))
        if sc.docstatus != 1 or pc.docstatus != 1:
            frappe.throw(_("Both contracts must be submitted before allocation"))
        if sc.commodity != pc.commodity:
            frappe.throw(_("Commodity differs between the two contracts"))

    def validate_qty(self):
        if (self.allocated_qty or 0) <= 0:
            frappe.throw(_("Allocated Qty must be greater than zero"))

        for name in (self.sales_contract, self.purchase_contract):
            contract_qty = frappe.db.get_value("Trade Contract", name, "contract_qty")
            already = self.get_allocated(name, exclude=self.name)
            free = contract_qty - already
            if self.allocated_qty > free:
                frappe.throw(
                    _("{0}: only {1} MT is unallocated, you entered {2} MT").format(
                        name, free, self.allocated_qty
                    )
                )

    @staticmethod
    def get_allocated(contract, exclude=None):
        return frappe.db.sql(
            """select coalesce(sum(allocated_qty), 0)
            from `tabContract Allocation`
            where docstatus = 1 and name != %s
            and (sales_contract = %s or purchase_contract = %s)""",
            (exclude or "", contract, contract),
        )[0][0]

    def on_submit(self):
        self.update_contracts()

    def on_cancel(self):
        self.update_contracts()

    def update_contracts(self):
        for name in (self.sales_contract, self.purchase_contract):
            frappe.db.set_value(
                "Trade Contract", name, "allocated_qty", self.get_allocated(name)
            )