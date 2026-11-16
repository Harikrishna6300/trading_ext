import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = filters or {}
    data = get_data(filters)
    return get_columns(), data, None, get_chart(data)


def get_columns():
    return [
        {"label": _("Shipment"), "fieldname": "name", "fieldtype": "Link", "options": "Trade Shipment", "width": 140},
        {"label": _("Sales Contract"), "fieldname": "sales_contract", "fieldtype": "Link", "options": "Trade Contract", "width": 130},
        {"label": _("Customer"), "fieldname": "customer", "fieldtype": "Data", "width": 160},
        {"label": _("Loading Type"), "fieldname": "loading_type", "fieldtype": "Data", "width": 100},
        {"label": _("Qty (MT)"), "fieldname": "shipped_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
        {"label": _("Product Cost"), "fieldname": "product_cost", "fieldtype": "Currency", "width": 130},
        {"label": _("Other Costs"), "fieldname": "other_costs", "fieldtype": "Currency", "width": 120},
        {"label": _("Margin"), "fieldname": "margin", "fieldtype": "Currency", "width": 130},
        {"label": _("Margin / MT"), "fieldname": "margin_per_mt", "fieldtype": "Currency", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
    ]


def get_data(filters):
    conditions = {"docstatus": 1}
    for key in ("loading_type", "sales_contract", "region", "country", "trader"):
        if filters.get(key):
            conditions[key] = filters[key]
    if filters.get("from_date") and filters.get("to_date"):
        conditions["creation"] = ["between", [filters["from_date"], filters["to_date"] + " 23:59:59"]]

    rows = frappe.get_all(
        "Trade Shipment",
        filters=conditions,
        fields=[
            "name", "sales_contract", "customer", "loading_type", "shipped_qty",
            "revenue", "product_cost", "other_costs", "margin", "status",
        ],
        order_by="creation desc",
    )
    for r in rows:
        r.margin_per_mt = flt(r.margin) / flt(r.shipped_qty) if flt(r.shipped_qty) else 0
    return rows


def get_chart(data):
    if not data:
        return None
    return {
        "data": {
            "labels": [d.name for d in data],
            "datasets": [{"name": _("Margin"), "values": [flt(d.margin) for d in data]}],
        },
        "type": "bar",
    }