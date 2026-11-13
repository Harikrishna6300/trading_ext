import frappe

COMPANY = "Hari Krishna IT Solutions PVT LTD-US"
ABBR = "HK"


def run():
    make_company()
    make_masters()
    make_accounts()
    make_cost_types()
    make_dimensions()
    frappe.db.commit()
    print("Demo data ready")


def ensure(doctype, name, values, by_field=None):
    """Insert the record only if it doesn't already exist.

    by_field: look up an existing record by this field's value instead of
    the document name (needed when the name is a hash or a series).
    """
    if by_field:
        exists = frappe.db.exists(doctype, {by_field: values[by_field]})
    else:
        exists = frappe.db.exists(doctype, name)
    if not exists:
        frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def leaf(doctype):
    """Return the first non-group record (for example a leaf Customer Group)."""
    return frappe.db.get_value(doctype, {"is_group": 0}, "name")


def make_company():
    if frappe.db.exists("Company", COMPANY):
        return
    frappe.get_doc({
        "doctype": "Company",
        "company_name": COMPANY,
        "abbr": ABBR,
        "default_currency": "USD",
        "country": "United States",
        "chart_of_accounts": "Standard",
    }).insert(ignore_permissions=True)


def make_masters():
    ensure("Item Group", "Fertilizer", {
        "item_group_name": "Fertilizer",
        "parent_item_group": "All Item Groups",
    })

    ensure("UOM", "MT", {"uom_name": "MT"})

    ensure("Item", "Urea Granular", {
        "item_code": "Urea Granular",
        "item_name": "Urea Granular",
        "item_group": "Fertilizer",
        "stock_uom": "MT",
        "is_stock_item": 0,
    }, by_field="item_code")

    ensure("Customer", "Customer A", {
        "customer_name": "Customer A",
        "customer_group": leaf("Customer Group"),
        "territory": leaf("Territory"),
        "default_currency": "USD",
    }, by_field="customer_name")

    ensure("Supplier", "Supplier X", {
        "supplier_name": "Supplier X",
        "supplier_group": leaf("Supplier Group"),
        "default_currency": "USD",
    }, by_field="supplier_name")

    ensure("Vessel", "MV Demo One", {
        "vessel_name": "MV Demo One",
    }, by_field="vessel_name")


def make_accounts():
    expenses = [
        "Freight Expense", "Insurance Expense", "Port Charges",
        "Demurrage Expense", "Survey Charges", "Handling Charges",
        "Bank Charges", "Trade Finance Cost",
    ]
    for name in expenses:
        ensure("Account", f"{name} - {ABBR}", {
            "account_name": name,
            "company": COMPANY,
            "parent_account": f"Indirect Expenses - {ABBR}",
            "account_type": "Expense Account",
        })

    # Plain liability account (no account type, so no Party is forced)
    ensure("Account", f"Accrued Shipment Costs - {ABBR}", {
        "account_name": "Accrued Shipment Costs",
        "company": COMPANY,
        "parent_account": f"Current Liabilities - {ABBR}",
    })


def make_cost_types():
    types = {
        "Freight": "Freight Expense",
        "Insurance": "Insurance Expense",
        "Port Charges": "Port Charges",
        "Demurrage": "Demurrage Expense",
        "Survey": "Survey Charges",
        "Handling": "Handling Charges",
        "Bank Charges": "Bank Charges",
        "Trade Finance Cost": "Trade Finance Cost",
    }
    for cost_type, account in types.items():
        ensure("Shipment Cost Type", cost_type, {
            "cost_type": cost_type,
            "expense_account": f"{account} - {ABBR}",
        }, by_field="cost_type")


def make_dimensions():
    for label, doctype in (
        ("Region", "Territory"),
        ("Trade Contract", "Trade Contract"),
        ("Trade Shipment", "Trade Shipment"),
    ):
        if not frappe.db.exists("Accounting Dimension", {"document_type": doctype}):
            frappe.get_doc({
                "doctype": "Accounting Dimension",
                "label": label,
                "document_type": doctype,
            }).insert(ignore_permissions=True)