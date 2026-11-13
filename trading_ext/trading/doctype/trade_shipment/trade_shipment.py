# Copyright (c) 2026, hari and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TradeShipment(Document):
    def validate(self):
        self.set_from_allocation()
        self.validate_qty()
        self.calculate_costs()

    def set_from_allocation(self):
        alloc = frappe.get_doc("Contract Allocation", self.contract_allocation)
        if alloc.docstatus != 1:
            frappe.throw(_("Contract Allocation must be submitted"))
        self.sales_contract = alloc.sales_contract
        self.purchase_contract = alloc.purchase_contract
        self.company = frappe.db.get_value("Trade Contract", alloc.sales_contract, "company")

    def validate_qty(self):
        if (self.shipped_qty or 0) <= 0:
            frappe.throw(_("Shipped Qty must be greater than zero"))

        allocated = frappe.db.get_value("Contract Allocation", self.contract_allocation, "allocated_qty")
        already = frappe.db.sql(
            """select coalesce(sum(shipped_qty), 0) from `tabTrade Shipment`
            where docstatus = 1 and contract_allocation = %s and name != %s""",
            (self.contract_allocation, self.name or ""),
        )[0][0]
        if self.shipped_qty > allocated - already:
            frappe.throw(
                _("Only {0} MT remains on this allocation, you entered {1} MT").format(
                    allocated - already, self.shipped_qty
                )
            )

        sc = frappe.db.get_value(
            "Trade Contract", self.sales_contract, ["contract_qty", "tolerance_pct"], as_dict=True
        )
        shipped = get_shipped_qty(self.sales_contract, "sales_contract", exclude=self.name)
        limit = sc.contract_qty * (1 + (sc.tolerance_pct or 0) / 100)
        if shipped + self.shipped_qty > limit:
            frappe.throw(_("Shipment exceeds the sales contract quantity (including tolerance)"))

    def calculate_costs(self):
        total = 0
        for row in self.costs:
            amount = row.actual_amount or row.accrued_amount or row.estimated_amount or 0
            row.amount_usd = amount * (row.exchange_rate or 1)
            total += row.amount_usd
        self.total_cost_usd = total

    def on_submit(self):
        self.update_contracts()

    def on_cancel(self):
        self.update_contracts()

    def update_contracts(self):
        for contract, field in ((self.sales_contract, "sales_contract"),
                                (self.purchase_contract, "purchase_contract")):
            shipped = get_shipped_qty(contract, field)
            qty = frappe.db.get_value("Trade Contract", contract, "contract_qty")
            if shipped <= 0:
                status = "Open"
            elif shipped < qty:
                status = "Partially Shipped"
            else:
                status = "Fully Shipped"
            frappe.db.set_value("Trade Contract", contract, {
                "shipped_qty": shipped,
                "balance_qty": qty - shipped,
                "status": status,
            })


def get_shipped_qty(contract, field, exclude=None):
    return frappe.db.sql(
        f"""select coalesce(sum(shipped_qty), 0) from `tabTrade Shipment`
        where docstatus = 1 and {field} = %s and name != %s""",
        (contract, exclude or ""),
    )[0][0]
