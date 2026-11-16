import json

import frappe

CARDS = [
    # label, doctype, function, field, filters
    ("Open Sales Contracts", "Trade Contract", "Count", None, [
        ["Trade Contract", "contract_type", "=", "Sales"],
        ["Trade Contract", "docstatus", "=", 1],
        ["Trade Contract", "status", "in", ["Open", "Partially Shipped"]],
    ]),
    ("Open Purchase Contracts", "Trade Contract", "Count", None, [
        ["Trade Contract", "contract_type", "=", "Purchase"],
        ["Trade Contract", "docstatus", "=", 1],
        ["Trade Contract", "status", "in", ["Open", "Partially Shipped"]],
    ]),
    ("Total Balance Qty (MT)", "Trade Contract", "Sum", "balance_qty", [
        ["Trade Contract", "contract_type", "=", "Sales"],
        ["Trade Contract", "docstatus", "=", 1],
    ]),
    ("Total Shipped Qty (MT)", "Trade Shipment", "Sum", "shipped_qty", [
        ["Trade Shipment", "docstatus", "=", 1],
    ]),
    ("Total Margin (USD)", "Trade Shipment", "Sum", "margin", [
        ["Trade Shipment", "docstatus", "=", 1],
    ]),
]

CHARTS = [
    # name, doctype, group_by, function, field, type
    ("Contracts by Status", "Trade Contract", "status", "Count", None, "Donut"),
    ("Shipped Qty by Sales Contract", "Trade Shipment", "sales_contract", "Sum", "shipped_qty", "Bar"),
    ("Margin by Loading Type", "Trade Shipment", "loading_type", "Sum", "margin", "Bar"),
]


def run():
    for c in CARDS:
        make_card(*c)
    for c in CHARTS:
        make_chart(*c)
    frappe.db.commit()
    print("Number Cards and Charts ready")
    make_workspace()
    frappe.db.commit()
    print("Workspace ready")


def make_card(label, doctype, function, field, filters):
    old = frappe.db.get_value("Number Card", {"label": label})
    if old:
        frappe.delete_doc("Number Card", old, force=True)
    doc = {
        "doctype": "Number Card",
        "label": label,
        "type": "Document Type",
        "document_type": doctype,
        "function": function,
        "filters_json": json.dumps(filters),
        "is_public": 1,
        "show_percentage_stats": 0,
    }
    if field:
        doc["aggregate_function_based_on"] = field
    frappe.get_doc(doc).insert(ignore_permissions=True)


def make_chart(name, doctype, group_by, function, field, chart_type):
    old = frappe.db.get_value("Dashboard Chart", {"chart_name": name})
    if old:
        frappe.delete_doc("Dashboard Chart", old, force=True)
    doc = {
        "doctype": "Dashboard Chart",
        "chart_name": name,
        "chart_type": "Group By",
        "document_type": doctype,
        "group_by_type": function,
        "group_by_based_on": group_by,
        "filters_json": json.dumps([[doctype, "docstatus", "=", 1]]),
        "type": chart_type,
        "is_public": 1,
        "timeseries": 0,
    }
    if field:
        doc["aggregate_function_based_on"] = field
    frappe.get_doc(doc).insert(ignore_permissions=True)


def make_workspace():
    name = "Commodity Trading"
    if frappe.db.exists("Workspace", name):
        frappe.delete_doc("Workspace", name, force=True)

    blocks = [{"id": "h1", "type": "header",
               "data": {"text": "<span class=\"h4\">Commodity Trading</span>", "col": 12}}]
    for i, c in enumerate(CARDS):
        blocks.append({"id": f"n{i}", "type": "number_card",
                       "data": {"number_card_name": c[0], "col": 4}})
    for i, c in enumerate(CHARTS):
        blocks.append({"id": f"c{i}", "type": "chart",
                       "data": {"chart_name": c[0], "col": 6}})
    shortcuts = [
        ("Trade Contract", "DocType", "Trade Contract"),
        ("Contract Allocation", "DocType", "Contract Allocation"),
        ("Trade Shipment", "DocType", "Trade Shipment"),
        ("Contract Balance", "Report", "Contract Balance"),
        ("Shipment Profitability", "Report", "Shipment Profitability"),
    ]
    for i, s in enumerate(shortcuts):
        blocks.append({"id": f"s{i}", "type": "shortcut",
                       "data": {"shortcut_name": s[0], "col": 3}})

    ws = frappe.new_doc("Workspace")
    ws.name = name
    ws.label = name
    ws.title = name
    ws.module = "Trading"
    ws.public = 1
    ws.is_hidden = 0
    ws.content = json.dumps(blocks)
    for c in CARDS:
        ws.append("number_cards", {"number_card_name": c[0], "label": c[0]})
    for c in CHARTS:
        ws.append("charts", {"chart_name": c[0], "label": c[0]})
    for label, typ, link in shortcuts:
        row = {"label": label, "link_to": link, "type": typ}
        if typ == "Report":
            row["doc_view"] = ""
            row["report_ref_doctype"] = frappe.db.get_value("Report", link, "ref_doctype")
        ws.append("shortcuts", row)
    ws.insert(ignore_permissions=True)