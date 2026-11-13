// Copyright (c) 2026, hari and contributors
// For license information, please see license.txt

frappe.ui.form.on("Contract Allocation", {
    setup(frm) {
        frm.set_query("sales_contract", () => ({
            filters: { contract_type: "Sales", docstatus: 1 },
        }));
        frm.set_query("purchase_contract", () => ({
            filters: { contract_type: "Purchase", docstatus: 1 },
        }));
    },
});