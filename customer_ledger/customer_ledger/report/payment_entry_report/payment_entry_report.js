// Payment Entry Report - Client-side filter configuration

frappe.query_reports["Payment Entry Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: "2025-04-01",
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Month (overrides dates)"),
			fieldtype: "Select",
			options: [
				"",
				"January", "February", "March", "April",
				"May", "June", "July", "August",
				"September", "October", "November", "December",
			].join("\n"),
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: parseInt(frappe.datetime.get_today().split("-")[0]),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			get_query: function () {
				return { filters: { disabled: 0 } };
			},
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory",
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group",
		},
		{
			fieldname: "mode_of_payment",
			label: __("Mode of Payment"),
			fieldtype: "Link",
			options: "Mode of Payment",
		},
		{
			fieldname: "payment_type",
			label: __("Payment Type"),
			fieldtype: "Select",
			options: "\nReceive\nPay\nInternal Transfer",
		},
	],

	onload: function (report) {
		report.page.add_inner_button(__("Export Excel"), function () {
			frappe.query_report.export_report();
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_total) {
			value = "<strong>" + value + "</strong>";
		}

		if (column.fieldname === "unallocated_amount" && data && !data.is_total) {
			var raw = data.unallocated_amount;
			if (raw && raw > 0) {
				value = '<span style="color:#e67e22;">' + value + "</span>";
			}
		}

		return value;
	},
};
