frappe.listview_settings["Trade Contract"] = {
    add_fields: ["status"],
    get_indicator(doc) {
        const colors = {
            "Draft": "gray",
            "Open": "green",
            "Partially Shipped": "orange",
            "Fully Shipped": "blue",
            "Closed": "red",
        };
        return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
    },
};