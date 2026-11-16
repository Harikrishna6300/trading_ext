frappe.ui.form.on("Trade Contract", {
    contract_type(frm) {
        frm.set_value("party_type", frm.doc.contract_type === "Purchase" ? "Supplier" : "Customer");
        frm.set_value("party", null);
    },
});