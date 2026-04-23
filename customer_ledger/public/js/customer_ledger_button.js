frappe.ui.form.on("Customer", {
	refresh: function (frm) {
		var today = frappe.datetime.get_today();
		var ledgerStartDate = "2025-04-01";

		frm.add_custom_button(__("Customer Ledger"), function () {
			frappe.set_route("query-report", "Customer Ledger Report", {
				customer:   frm.doc.name,
				company:    frappe.defaults.get_default("company"),
				from_date:  ledgerStartDate,
				to_date:    today,
			});
		});

		frm.add_custom_button(__("Customer AR"), function () {
			frappe.set_route("query-report", "Customer AR Report", {
				customer:  frm.doc.name,
				company:   frappe.defaults.get_default("company"),
				to_date:   today,
			});
		});
	},
});
