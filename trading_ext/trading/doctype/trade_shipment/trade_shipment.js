// Copyright (c) 2026, hari and contributors
// For license information, please see license.txt

frappe.ui.form.on("Trade Shipment", {
    setup(frm) {
        frm.set_query("contract_allocation", () => ({ filters: { docstatus: 1 } }));
    },

    contract_allocation(frm) {
        if (!frm.doc.contract_allocation) {
            frm.set_value({
                sales_contract: null, purchase_contract: null, customer: null,
                supplier: null, commodity: null, company: null,
                trader: null, region: null, country: null,
            });
            return;
        }

        frappe.db
            .get_value("Contract Allocation", frm.doc.contract_allocation,
                ["sales_contract", "purchase_contract", "customer", "supplier", "commodity"])
            .then((r) => {
                const a = r.message;
                frm.set_value({
                    sales_contract: a.sales_contract,
                    purchase_contract: a.purchase_contract,
                    customer: a.customer,
                    supplier: a.supplier,
                    commodity: a.commodity,
                });

                return frappe.db.get_value("Trade Contract", a.sales_contract,
                    ["company", "trader", "region", "country"]);
            })
            .then((r) => {
                const c = r.message;
                frm.set_value({
                    company: c.company,
                    trader: c.trader,
                    region: c.region,
                    country: c.country,
                });
            });
    },
});