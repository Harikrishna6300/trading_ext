import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

STATUS_ORDER = ["Planned", "Loading", "Sailed", "Delivered", "Settled"]


class TradeShipment(Document):
    # ---------- validation ----------
    def validate(self):
        self.validate_status_flow()
        self.set_from_allocation()
        self.validate_qty()
        self.calculate_costs()
        self.calculate_profit()

    # ---------- status control ----------
    def validate_status_flow(self):
        """Voyage status moves forward one step at a time."""
        if self.is_new():
            self.status = "Planned"
            return

        old = self.get_doc_before_save()
        if not old or old.status == self.status:
            return

        old_i = STATUS_ORDER.index(old.status or "Planned")
        new_i = STATUS_ORDER.index(self.status)

        if new_i != old_i + 1:
            frappe.throw(
                _("Status can only move forward one step: from {0} to {1}").format(
                    old.status, STATUS_ORDER[min(old_i + 1, len(STATUS_ORDER) - 1)]
                )
            )

        if self.docstatus == 0 and new_i > 0:
            frappe.throw(_("Submit the shipment before changing its status"))

        if self.status == "Sailed" and not (self.bl_no and self.bl_date):
            frappe.throw(_("Enter BL No and BL Date before marking the shipment as Sailed"))

        if self.status == "Settled":
            if "Finance Manager" not in frappe.get_roles():
                frappe.throw(_("Only a Finance Manager can mark a shipment as Settled"))

    @frappe.whitelist()
    def update_status(self, new_status):
        """Called by the form buttons. Runs the same checks as a normal save."""
        if new_status not in STATUS_ORDER:
            frappe.throw(_("Invalid status {0}").format(new_status))
        if self.docstatus != 1:
            frappe.throw(_("Submit the shipment before changing its status"))
        self.check_permission("write")
        self.status = new_status
        self.save()
        return self.status

    # ---------- quantity checks ----------
    def set_from_allocation(self):
        alloc = frappe.get_doc("Contract Allocation", self.contract_allocation)
        if alloc.docstatus != 1:
            frappe.throw(_("Contract Allocation must be submitted"))
        self.sales_contract = alloc.sales_contract
        self.purchase_contract = alloc.purchase_contract
        self.company = frappe.db.get_value("Trade Contract", alloc.sales_contract, "company")

    def validate_qty(self):
        qty = flt(self.shipped_qty, 3)
        if qty <= 0:
            frappe.throw(_("Shipped Qty must be greater than zero"))

        # 1) allocation balance
        allocated = flt(
            frappe.db.get_value("Contract Allocation", self.contract_allocation, "allocated_qty"), 3
        )
        already_alloc = self.get_shipped(self.contract_allocation, "contract_allocation")
        if qty > flt(allocated - already_alloc, 3):
            frappe.throw(
                _("Only {0} MT remains on allocation {1}, you entered {2} MT").format(
                    flt(allocated - already_alloc, 3), self.contract_allocation, qty
                )
            )

        # 2) contract quantity including tolerance (sales and purchase)
        has_tol = frappe.get_meta("Trade Contract").has_field("tolerance_pct")
        for contract, field in (
            (self.sales_contract, "sales_contract"),
            (self.purchase_contract, "purchase_contract"),
        ):
            contract_qty = flt(frappe.db.get_value("Trade Contract", contract, "contract_qty"), 3)
            tol = flt(frappe.db.get_value("Trade Contract", contract, "tolerance_pct")) if has_tol else 0
            tolerance = max(tol, 0)
            limit = flt(contract_qty * (1 + tolerance / 100), 3)
            already = self.get_shipped(contract, field)

            if flt(already + qty, 3) > limit:
                frappe.throw(
                    _(
                        "Shipment exceeds contract {0}: contract qty {1} MT with tolerance "
                        "{2}% gives a limit of {3} MT. Already shipped {4} MT, this shipment "
                        "{5} MT."
                    ).format(contract, contract_qty, tolerance, limit, already, qty)
                )

    def get_shipped(self, value, field):
        """Submitted shipped qty for a contract or allocation, excluding this document."""
        return flt(
            frappe.db.sql(
                f"""select coalesce(sum(shipped_qty), 0) from `tabTrade Shipment`
                where docstatus = 1 and {field} = %s and name != %s""",
                (value, self.name or ""),
            )[0][0],
            3,
        )

    # ---------- costs and profit (all USD) ----------
    def calculate_costs(self):
        total = 0
        for row in self.costs:
            row.currency = row.currency or "USD"
            row.exchange_rate = flt(row.exchange_rate) or 1

            if self.docstatus == 0:
                row.accrued_amount = row.estimated_amount

            amount = flt(row.actual_amount) or flt(row.accrued_amount) or flt(row.estimated_amount)
            row.amount_usd = amount * row.exchange_rate
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

    # ---------- submit / cancel ----------
    def on_submit(self):
        self.update_contracts()
        self.create_sales_invoice()
        self.create_accrual_entry()

    def on_cancel(self):
        self.ignore_linked_doctypes = ("Journal Entry", "Sales Invoice")
        self.cancel_accrual_entry()
        self.remove_sales_invoice()
        self.update_contracts()

    def update_contracts(self):
        for contract, field in (
            (self.sales_contract, "sales_contract"),
            (self.purchase_contract, "purchase_contract"),
        ):
            shipped = flt(
                frappe.db.sql(
                    f"""select coalesce(sum(shipped_qty), 0) from `tabTrade Shipment`
                    where docstatus = 1 and {field} = %s""",
                    (contract,),
                )[0][0],
                3,
            )
            qty = flt(frappe.db.get_value("Trade Contract", contract, "contract_qty"), 3)
            if shipped <= 0:
                status = "Open"
            elif shipped < qty:
                status = "Partially Shipped"
            else:
                status = "Fully Shipped"
            frappe.db.set_value(
                "Trade Contract",
                contract,
                {"shipped_qty": shipped, "balance_qty": flt(qty - shipped, 3), "status": status},
            )

    # ---------- accounting ----------
    def set_dimensions(self, row):
        """Fill accounting dimension fields if they exist on the target row."""
        meta = frappe.get_meta(row.doctype)
        values = {
            "trade_shipment": self.name,
            "trade_contract": self.sales_contract,
            "region": self.region,
        }
        for fieldname, value in values.items():
            if value and meta.has_field(fieldname):
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
            amount = flt(c.accrued_amount) * flt(c.exchange_rate or 1)
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

        row = je.append("accounts", {"account": liability, "credit_in_account_currency": total})
        self.set_dimensions(row)
        je.insert(ignore_permissions=True)
        je.submit()
        self.db_set("accrual_journal_entry", je.name)

    def cancel_accrual_entry(self):
        if self.accrual_journal_entry:
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