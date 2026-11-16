import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Contract"), "fieldname": "name", "fieldtype": "Link", "options": "Trade Contract", "width": 140},
        {"label": _("Type"), "fieldname": "contract_type", "fieldtype": "Data", "width": 80},
        {"label": _("Party"), "fieldname": "party_name", "fieldtype": "Data", "width": 160},
        {"label": _("Commodity"), "fieldname": "commodity", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Contract Qty"), "fieldname": "contract_qty", "fieldtype": "Float", "width": 110},
        {"label": _("Shipped"), "fieldname": "shipped_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Balance"), "fieldname": "balance_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Invoiced"), "fieldname": "invoiced_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Un-invoiced"), "fieldname": "uninvoiced_qty", "fieldtype": "Float", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
    ]


def get_data(filters):
    conditions = {"docstatus": 1}
    for key in ("contract_type", "commodity", "trader", "status"):
        if filters.get(key):
            conditions[key] = filters[key]
    if filters.get("from_date") and filters.get("to_date"):
        conditions["contract_date"] = ["between", [filters["from_date"], filters["to_date"]]]

    contracts = frappe.get_all(
        "Trade Contract",
        filters=conditions,
        fields=["name", "contract_type", "party_name", "commodity", "contract_qty", "status"],
        order_by="contract_date desc, name desc",
    )

    shipments = frappe.db.sql(
        """
        select ts.sales_contract, ts.purchase_contract, ts.shipped_qty,
               si.docstatus as inv_status
        from `tabTrade Shipment` ts
        left join `tabSales Invoice` si on si.name = ts.sales_invoice
        where ts.docstatus = 1
        """,
        as_dict=True,
    )

    shipped, invoiced = {}, {}
    for s in shipments:
        for key in (s.sales_contract, s.purchase_contract):
            shipped[key] = shipped.get(key, 0) + flt(s.shipped_qty)
        if s.inv_status == 1:
            invoiced[s.sales_contract] = invoiced.get(s.sales_contract, 0) + flt(s.shipped_qty)

    for c in contracts:
        c.shipped_qty = shipped.get(c.name, 0)
        c.balance_qty = flt(c.contract_qty) - c.shipped_qty
        is_sales = c.contract_type == "Sales"
        c.invoiced_qty = invoiced.get(c.name, 0) if is_sales else 0
        c.uninvoiced_qty = (c.shipped_qty - c.invoiced_qty) if is_sales else 0
    return contracts