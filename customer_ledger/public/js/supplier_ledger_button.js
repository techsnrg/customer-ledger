frappe.ui.form.on("Supplier", {
	refresh: function (frm) {
		var today  = frappe.datetime.get_today();

		frm.add_custom_button(__("Supplier Ledger"), function () {
			frappe.set_route("query-report", "Supplier Ledger Report", {
				supplier:  frm.doc.name,
				company:   frappe.defaults.get_default("company"),
				from_date: "2025-04-01",
				to_date:   today,
			});
		});

		frm.add_custom_button(__("Supplier AP"), function () {
			frappe.set_route("query-report", "Supplier AP Report", {
				supplier: frm.doc.name,
				company:  frappe.defaults.get_default("company"),
				to_date:  today,
			});
		});
	},
});
