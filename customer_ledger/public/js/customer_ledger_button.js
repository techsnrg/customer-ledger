frappe.ui.form.on("Customer", {
	refresh: function (frm) {
		// Indian FY start: 1 Apr of current or previous year
		var today  = frappe.datetime.get_today();
		var parts  = today.split("-");
		var y      = parseInt(parts[0]);
		var m      = parseInt(parts[1]);
		var fy_start = (m <= 3 ? y - 1 : y) + "-04-01";

		frm.add_custom_button(__("Customer Ledger"), function () {
			frappe.set_route("query-report", "Customer Ledger Report", {
				customer:   frm.doc.name,
				company:    frappe.defaults.get_default("company"),
				from_date:  fy_start,
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
