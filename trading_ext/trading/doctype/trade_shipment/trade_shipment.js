// Copyright (c) 2026, hari and contributors
// For license information, please see license.txt

frappe.ui.form.on("Trade Shipment", {
    setup(frm) {
        frm.set_query("contract_allocation", () => ({ filters: { docstatus: 1 } }));
    },
});