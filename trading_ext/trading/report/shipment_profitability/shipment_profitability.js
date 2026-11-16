frappe.query_reports["Shipment Profitability"] = {
    filters: [
        { fieldname: "loading_type", label: __("Loading Type"), fieldtype: "Select", options: "\nBulk\nContainer" },
        { fieldname: "sales_contract", label: __("Sales Contract"), fieldtype: "Link", options: "Trade Contract" },
        { fieldname: "region", label: __("Region"), fieldtype: "Link", options: "Territory" },
        { fieldname: "country", label: __("Country"), fieldtype: "Link", options: "Country" },
        { fieldname: "trader", label: __("Trader"), fieldtype: "Link", options: "Sales Person" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
    ],
};