import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

STATUS_ORDER = ["Planned", "Loading", "Sailed", "Delivered", "Settled"]
STATUS_ROLE = "Finance Manager"


class TradeShipment(Document):
    # ---------- validation ----------
    def validate(self):
        self.validate_status_flow()
        self.voyage_status = self.status or "Planned"
        self.set_from_allocation()
        self.validate_currency()
        self.validate_qty()
        self.calculate_costs()
        self.calculate_profit()

    # ---------- status control ----------
    def validate_status_flow(self):
        """Manual status change: Finance Manager only, forward one step at a time."""
        if self.is_new():
            self.status = "Planned"
            return

        old = self.get_doc_before_save()
        if not old or old.status == self.status:
            return

        if STATUS_ROLE not in frappe.get_roles():
            frappe.throw(_("Only a Finance Manager can change the shipment status manually"))

        old_i = STATUS_ORDER.index(old.status or "Planned")
        new_i = STATUS_ORDER.index(self.status)

        if new_i != old_i + 1:
            frappe.throw(
                _("Status can only move forward one step: from {0} to {1}").format(
                    old.status, STATUS_ORDER[min(old_i + 1, len(STATUS_ORDER) - 1)]
                )
            )

        if self.docstatus == 0:
            frappe.throw(_("Submit the shipment before changing its status"))

        if self.status == "Sailed" and not (self.bl_no and self.bl_date):
            frappe.throw(_("Enter BL No and BL Date before marking the shipment as Sailed"))

    @frappe.whitelist()
    def update_status(self, new_status):
        """Called by the form button (Finance Manager only)."""
        if new_status not in STATUS_ORDER:
            frappe.throw(_("Invalid status {0}").format(new_status))
        if self.docstatus != 1:
            frappe.throw(_("Submit the shipment before changing its status"))
        self.check_permission("write")
        self.status = new_status
        self.save()
        return self.status

    def on_update_after_submit(self):
        """Run the automatic rules whenever a submitted shipment is updated."""
        evaluate_status(self)
        self.db_set("voyage_status", self.status)

    def set_status_auto(self, new_status, reason):
        """System-driven change. Bypasses the manual role check."""
        self.db_set({"status": new_status, "voyage_status": new_status})
        self.add_comment(
            "Info", _("Status changed to {0} automatically: {1}").format(new_status, reason)
        )

    # ---------- allocation, currency, quantity ----------
    def set_from_allocation(self):
        alloc = frappe.get_doc("Contract Allocation", self.contract_allocation)
        if alloc.docstatus != 1:
            frappe.throw(_("Contract Allocation must be submitted"))
        self.sales_contract = alloc.sales_contract
        self.purchase_contract = alloc.purchase_contract
        self.company = frappe.db.get_value("Trade Contract", alloc.sales_contract, "company")

    def validate_currency(self):
        base = frappe.get_cached_value("Company", self.company, "default_currency")
        for contract in (self.sales_contract, self.purchase_contract):
            currency = frappe.db.get_value("Trade Contract", contract, "currency")
            if currency != base:
                frappe.throw(
                    _("Contract {0} is in {1}, but company {2} uses {3}. Use the company currency.").format(
                        contract, currency, self.company, base
                    )
                )

    def validate_qty(self):
        qty = flt(self.shipped_qty, 3)
        if qty <= 0:
            frappe.throw(_("Shipped Qty must be greater than zero"))

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
        return flt(
            frappe.db.sql(
                f"""select coalesce(sum(shipped_qty), 0) from `tabTrade Shipment`
                where docstatus = 1 and {field} = %s and name != %s""",
                (value, self.name or ""),
            )[0][0],
            3,
        )

    # ---------- costs and profit (company currency) ----------
    def calculate_costs(self):
        base = frappe.get_cached_value("Company", self.company, "default_currency")
        total = 0
        for row in self.costs:
            row.currency = row.currency or base
            row.exchange_rate = 1 if row.currency == base else (flt(row.exchange_rate) or 1)

            if self.docstatus == 0:
                row.accrued_amount = row.estimated_amount

            amount = flt(row.actual_amount) or flt(row.accrued_amount) or flt(row.estimated_amount)
            row.amount_usd = amount * row.exchange_rate  # holds company currency (INR)
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
                {
                    "shipped_qty": shipped,
                    "balance_qty": flt(qty - shipped, 3),
                    "status": status,
                    "shipping_status": status,
                },
            )

    # ---------- accounting ----------
    def set_dimensions(self, row):
        meta = frappe.get_meta(row.doctype)
        values = {
            "trade_shipment": self.name,
            "trade_contract": self.sales_contract,
            "region": self.region,
        }
        for fieldname, value in values.items():
            if value and meta.has_field(fieldname):
                row.set(fieldname, value)

    def get_expense_account(self, cost_type):
        account = frappe.db.get_value("Shipment Cost Type", cost_type, "expense_account")
        if not account:
            frappe.throw(_("No expense account set for cost type {0}").format(cost_type))

        acc = frappe.db.get_value("Account", account, ["company", "account_name"], as_dict=True)
        if acc and acc.company != self.company:
            mapped = frappe.db.get_value(
                "Account", {"account_name": acc.account_name, "company": self.company}
            )
            if not mapped:
                frappe.throw(
                    _("Account '{0}' does not exist in company {1}. Create it first.").format(
                        acc.account_name, self.company
                    )
                )
            return mapped
        return account

    def get_liability_account(self):
        name = frappe.db.get_value(
            "Account", {"account_name": "Accrued Shipment Costs", "company": self.company}
        )
        if name:
            return name

        parent = frappe.db.get_value(
            "Account",
            {"company": self.company, "account_name": "Current Liabilities", "is_group": 1},
        )
        if not parent:
            frappe.throw(_("'Current Liabilities' account group not found for {0}").format(self.company))

        acc = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "Accrued Shipment Costs",
                "company": self.company,
                "parent_account": parent,
            }
        ).insert(ignore_permissions=True)
        return acc.name

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
        liability = self.get_liability_account()

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
            row = je.append(
                "accounts",
                {
                    "account": self.get_expense_account(c.cost_type),
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
            {"account": liability, "cost_center": cost_center, "credit_in_account_currency": total},
        )
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


# ---------- automatic status rules (module level) ----------
def evaluate_status(doc):
    """Apply all automatic rules to one submitted shipment, in order."""
    if doc.docstatus != 1 or doc.status == "Settled":
        return
    current = getdate(today())

    if doc.status == "Planned" and doc.etd and getdate(doc.etd) <= current:
        doc.set_status_auto("Loading", "ETD reached")

    if doc.status in ("Planned", "Loading") and doc.bl_no and doc.bl_date:
        doc.set_status_auto("Sailed", "BL details entered")

    if doc.status == "Sailed" and (
        doc.delivered_date or (doc.eta and getdate(doc.eta) <= current)
    ):
        reason = "Delivered Date entered" if doc.delivered_date else "ETA reached"
        doc.set_status_auto("Delivered", reason)

    if doc.status in ("Sailed", "Delivered") and doc.sales_invoice:
        inv = frappe.db.get_value(
            "Sales Invoice", doc.sales_invoice, ["docstatus", "outstanding_amount"], as_dict=True
        )
        if inv and inv.docstatus == 1 and flt(inv.outstanding_amount) <= 0:
            doc.set_status_auto("Settled", "Sales Invoice fully paid")


def auto_update_status():
    """Hourly safety-net job."""
    for name in frappe.get_all(
        "Trade Shipment", filters={"docstatus": 1, "status": ["!=", "Settled"]}, pluck="name"
    ):
        evaluate_status(frappe.get_doc("Trade Shipment", name))
    frappe.db.commit()


def refresh_for_invoices(invoices):
    """Re-check shipments linked to these Sales Invoices."""
    for name in frappe.get_all(
        "Trade Shipment",
        filters={"docstatus": 1, "sales_invoice": ["in", invoices], "status": ["!=", "Settled"]},
        pluck="name",
    ):
        evaluate_status(frappe.get_doc("Trade Shipment", name))
    frappe.db.commit()


def on_payment(doc, method=None):
    """Hook for Payment Entry, Journal Entry and Sales Invoice."""
    invoices = set()
    if doc.doctype == "Sales Invoice":
        invoices.add(doc.name)
    elif doc.doctype == "Payment Entry":
        for r in doc.get("references") or []:
            if r.reference_doctype == "Sales Invoice":
                invoices.add(r.reference_name)
    elif doc.doctype == "Journal Entry":
        for r in doc.get("accounts") or []:
            if r.reference_type == "Sales Invoice":
                invoices.add(r.reference_name)

    if invoices:
        frappe.enqueue(
            "trading_ext.trading.doctype.trade_shipment.trade_shipment.refresh_for_invoices",
            invoices=list(invoices),
            enqueue_after_commit=True,
        )