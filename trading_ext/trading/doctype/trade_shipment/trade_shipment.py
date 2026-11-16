# Copyright (c) 2026, hari and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class TradeShipment(Document):

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self):
        self.set_from_allocation()
        self.validate_qty()
        self.calculate_costs()
        self.calculate_profit()

    def set_from_allocation(self):
        if not self.contract_allocation:
            frappe.throw(_("Please select a Contract Allocation"))

        alloc = frappe.get_doc("Contract Allocation", self.contract_allocation)

        if alloc.docstatus != 1:
            frappe.throw(_("Contract Allocation must be submitted"))

        if not alloc.sales_contract:
            frappe.throw(_("Sales Contract is missing in Contract Allocation"))

        self.sales_contract = alloc.sales_contract
        self.purchase_contract = alloc.purchase_contract
        self.customer = alloc.customer
        self.supplier = alloc.supplier
        self.commodity = alloc.commodity

        sc = frappe.db.get_value(
            "Trade Contract",
            alloc.sales_contract,
            ["company", "trader", "region", "country"],
            as_dict=True,
        )
        if not sc:
            frappe.throw(_("Sales Contract not found"))

        self.company = sc.company
        self.trader = sc.trader
        self.region = sc.region
        self.country = sc.country

    def validate_qty(self):
        qty = flt(self.shipped_qty)
        if qty <= 0:
            frappe.throw(_("Shipped Qty must be greater than zero"))

        # 1. Allocation balance
        allocated = flt(
            frappe.db.get_value("Contract Allocation", self.contract_allocation, "allocated_qty")
        )
        already = flt(
            get_shipped_qty(self.contract_allocation, "contract_allocation", exclude=self.name)
        )
        remaining = allocated - already

        if qty > remaining + 0.0001:
            frappe.throw(
                _("Only {0} MT remains on this allocation, you entered {1} MT").format(
                    remaining, qty
                )
            )

        # 2. Sales contract quantity (including tolerance)
        tol_field = get_tolerance_field()
        fields = ["contract_qty"] + ([tol_field] if tol_field else [])
        sc = frappe.db.get_value("Trade Contract", self.sales_contract, fields, as_dict=True)
        if not sc:
            frappe.throw(_("Sales Contract not found"))

        shipped = flt(get_shipped_qty(self.sales_contract, "sales_contract", exclude=self.name))
        tolerance = flt(sc.get(tol_field)) if tol_field else 0
        limit = flt(sc.contract_qty) * (1 + tolerance / 100)

        if shipped + qty > limit + 0.0001:
            frappe.throw(
                _("Shipment exceeds the sales contract quantity (including tolerance)")
            )

    def calculate_costs(self):
        total = 0

        for row in self.costs:
            if flt(row.estimated_amount) < 0 or flt(row.actual_amount) < 0:
                frappe.throw(_("Cost amounts cannot be negative (row {0})").format(row.idx))

            # Before submit, the accrual follows the estimate
            if self.docstatus == 0:
                row.accrued_amount = row.estimated_amount

            amount = (
                flt(row.actual_amount)
                or flt(row.accrued_amount)
                or flt(row.estimated_amount)
            )
            row.amount_usd = amount * (flt(row.exchange_rate) or 1)
            total += row.amount_usd

        self.total_cost_usd = total

    def calculate_profit(self):
        sell = flt(frappe.db.get_value("Trade Contract", self.sales_contract, "price_per_mt"))
        buy = flt(frappe.db.get_value("Trade Contract", self.purchase_contract, "price_per_mt"))
        qty = flt(self.shipped_qty)

        self.revenue = qty * sell
        self.product_cost = qty * buy
        self.other_costs = flt(self.total_cost_usd)
        self.margin = self.revenue - self.product_cost - self.other_costs
        self.margin_per_mt = self.margin / qty if qty else 0

    # ------------------------------------------------------------------
    # Submit / Cancel
    # ------------------------------------------------------------------
    def on_submit(self):
        self.update_contracts()
        self.create_sales_invoice()
        self.create_accrual_entry()

    def on_cancel(self):
        self.ignore_linked_doctypes = (
            "Journal Entry",
            "Sales Invoice",
            "GL Entry",
            "Payment Ledger Entry",
        )
        self.cancel_accrual_entry()
        self.remove_sales_invoice()
        self.update_contracts()

    def update_contracts(self):
        contracts = [
            (self.sales_contract, "sales_contract"),
            (self.purchase_contract, "purchase_contract"),
        ]

        for contract, field in contracts:
            if not contract:
                continue

            # Do not touch a contract that was cancelled / closed
            if frappe.db.get_value("Trade Contract", contract, "docstatus") != 1:
                continue

            shipped = flt(get_shipped_qty(contract, field))
            qty = flt(frappe.db.get_value("Trade Contract", contract, "contract_qty"))

            if shipped <= 0:
                status = "Open"
            elif shipped < qty:
                status = "Partially Shipped"
            else:
                status = "Fully Shipped"

            frappe.db.set_value(
                "Trade Contract",
                contract,
                {
                    "shipped_qty": shipped,
                    "balance_qty": qty - shipped,
                    "status": status,
                },
            )

    # ------------------------------------------------------------------
    # Accounting
    # ------------------------------------------------------------------
    def set_dimensions(self, row):
        """Fill accounting dimension fields if they exist on the target row."""
        values = {
            "trade_shipment": self.name,
            "trade_contract": self.sales_contract,
            "region": self.region,
        }
        for fieldname, value in values.items():
            if value and row.meta.has_field(fieldname):
                row.set(fieldname, value)

    def create_sales_invoice(self):
        sc = frappe.get_doc("Trade Contract", self.sales_contract)

        si = frappe.new_doc("Sales Invoice")
        si.company = self.company
        si.customer = sc.party
        si.currency = sc.currency
        si.posting_date = today()
        si.due_date = today()

        row = si.append(
            "items",
            {
                "item_code": self.commodity or sc.commodity,
                "qty": self.shipped_qty,
                "uom": "MT",
                "rate": sc.price_per_mt,
            },
        )
        self.set_dimensions(row)

        si.insert(ignore_permissions=True)
        self.db_set("sales_invoice", si.name)

    def create_accrual_entry(self):
        cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
        liability = frappe.db.get_value(
            "Account", {"account_name": "Accrued Shipment Costs", "company": self.company}
        )
        if not liability:
            frappe.throw(
                _("Account 'Accrued Shipment Costs' not found for {0}").format(self.company)
            )

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = self.company
        je.posting_date = today()
        je.user_remark = f"Cost accrual for {self.name}"

        total = 0
        for c in self.costs:
            amount = flt(c.accrued_amount) * (flt(c.exchange_rate) or 1)
            if amount <= 0:
                continue

            account = frappe.db.get_value("Shipment Cost Type", c.cost_type, "expense_account")
            if not account:
                frappe.throw(_("No expense account set for cost type {0}").format(c.cost_type))

            row = je.append(
                "accounts",
                {
                    "account": account,
                    "cost_center": cost_center,
                    "debit_in_account_currency": amount,
                },
            )
            self.set_dimensions(row)
            total += amount

        if not total:
            return

        row = je.append(
            "accounts",
            {
                "account": liability,
                "cost_center": cost_center,
                "credit_in_account_currency": total,
            },
        )
        self.set_dimensions(row)

        je.insert(ignore_permissions=True)
        je.submit()
        self.db_set("accrual_journal_entry", je.name)

    def cancel_accrual_entry(self):
        if not self.accrual_journal_entry:
            return
        je = frappe.get_doc("Journal Entry", self.accrual_journal_entry)
        if je.docstatus == 1:
            je.cancel()

    def remove_sales_invoice(self):
        if not self.sales_invoice:
            return

        status = frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus")
        if status == 0:
            invoice = self.sales_invoice
            self.db_set("sales_invoice", None)
            frappe.delete_doc("Sales Invoice", invoice, ignore_permissions=True)
        elif status == 1:
            frappe.throw(_("Cancel Sales Invoice {0} first").format(self.sales_invoice))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def get_tolerance_field():
    """Return the tolerance fieldname used on Trade Contract (or None)."""
    columns = frappe.db.get_table_columns("Trade Contract")
    for name in ("tolerance_pct", "tolerance"):
        if name in columns:
            return name
    return None


def get_shipped_qty(contract, field, exclude=None):
    allowed_fields = (
        "sales_contract",
        "purchase_contract",
        "contract_allocation",
    )
    if field not in allowed_fields:
        frappe.throw(_("Invalid shipment reference field"))

    return (
        frappe.db.sql(
            f"""
            SELECT COALESCE(SUM(shipped_qty), 0)
            FROM `tabTrade Shipment`
            WHERE docstatus = 1
            AND {field} = %s
            AND name != %s
            """,
            (contract, exclude or ""),
        )[0][0]
        or 0
    )