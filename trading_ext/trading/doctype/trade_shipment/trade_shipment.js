const STATUS_ORDER = ["Planned", "Loading", "Sailed", "Delivered", "Settled"];

frappe.ui.form.on("Trade Shipment", {
    setup(frm) {
        frm.set_query("contract_allocation", () => ({ filters: { docstatus: 1 } }));
    },

    refresh(frm) {
        if (frm.doc.docstatus !== 1) return;

        // Manual status change is for Finance Manager only
        if (!frappe.user.has_role("Finance Manager")) return;

        const i = STATUS_ORDER.indexOf(frm.doc.status || "Planned");
        if (i < 0 || i >= STATUS_ORDER.length - 1) return;
        const next = STATUS_ORDER[i + 1];

        frm.add_custom_button(
            __("Mark as {0}", [next]),
            () => {
                frappe.confirm(__("Change status from {0} to {1}?", [frm.doc.status, next]), () => {
                    frm.call({
                        doc: frm.doc,
                        method: "update_status",
                        args: { new_status: next },
                        freeze: true,
                    }).then(() => frm.reload_doc());
                });
            },
            __("Status")
        );
    },
});