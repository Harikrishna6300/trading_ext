frappe.query_reports["Contract Balance"] = {
    filters: [
        { fieldname: "contract_type", label: __("Contract Type"), fieldtype: "Select", options: "\nSales\nPurchase" },
        { fieldname: "commodity", label: __("Commodity"), fieldtype: "Link", options: "Item" },
        { fieldname: "trader", label: __("Trader"), fieldtype: "Link", options: "Sales Person" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nPartially Shipped\nFully Shipped\nClosed" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
    ],
};