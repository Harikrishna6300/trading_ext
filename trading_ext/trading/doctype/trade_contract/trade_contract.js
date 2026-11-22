frappe.listview_settings["Trade Contract"] = {
    add_fields: ["status", "workflow_state"],
    has_indicator_for_draft: true,
    get_indicator(doc) {
        const colors = {
            "Open": "blue",
            "Partially Shipped": "orange",
            "Fully Shipped": "green",
            "Closed": "gray",
        };
        if (doc.docstatus === 0) return [__(doc.workflow_state || "Draft"), "red", "docstatus,=,0"];
        return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
    },
};  
    