// Customer Ledger Report - Client-side filter configuration

frappe.query_reports["Customer Ledger Report"] = {
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			reqd: 1,
			get_query: function () {
				return { filters: { disabled: 0 } };
			},
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
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
			fieldname: "currency",
			label: __("Currency"),
			fieldtype: "Link",
			options: "Currency",
		},
		{
			fieldname: "show_cancelled",
			label: __("Include Cancelled Entries"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "group_by_account",
			label: __("Group by Account"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_journal_entries",
			label: __("Include Journal Entries"),
			fieldtype: "Check",
			default: 1,
		},
	],

	onload: function (report) {
		// Frappe's query-report does not auto-refresh when a Check filter is
		// toggled.  Wire up jQuery change handlers directly on the checkbox
		// inputs so every toggle immediately re-runs the report.
		// A short delay is needed because the filter DOM is built after onload.
		setTimeout(function () {
			["show_cancelled", "group_by_account", "include_journal_entries"].forEach(function (fn) {
				var f = report.get_filter(fn);
				if (f && f.$input) {
					f.$input.off("change.cl_report").on("change.cl_report", function () {
						report.refresh();
					});
				}
			});
		}, 500);

		report.page.add_inner_button(__("Print Ledger"), function () {
			var filters = report.get_values();
			if (!filters) return;

			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Print Format",
					filters: { doc_type: "Report", name: "Customer Ledger Statement" },
					fields: ["name"],
					limit: 1,
				},
				callback: function () {
					// Open print dialog using the built-in report print
					var url = frappe.urllib.get_full_url(
						"/api/method/frappe.utils.print_format.download_pdf?" +
							$.param({
								doctype: "Report",
								name: "Customer Ledger Report",
								format: "Standard",
								no_letterhead: 0,
								filters: JSON.stringify(filters),
							})
					);
					window.open(url);
				},
			});
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Account group header rows — bold, no colour formatting
		if (data && data.is_group) {
			return `<strong>${value}</strong>`;
		}

		// Highlight Opening / Closing balance rows
		if (
			data &&
			(data.remarks === __("Opening Balance") || data.remarks === __("Closing Balance"))
		) {
			value = `<strong>${value}</strong>`;
		}

		// Color debit red, credit green in their respective columns
		if (column.fieldname === "debit" && data && data.debit > 0) {
			value = `<span style="color:#c0392b;">${value}</span>`;
		}
		if (column.fieldname === "credit" && data && data.credit > 0) {
			value = `<span style="color:#27ae60;">${value}</span>`;
		}

		// Color balance: positive = red (owes us), negative = green (credit balance)
		if (column.fieldname === "balance" && data && data.balance !== null) {
			const color = data.balance >= 0 ? "#c0392b" : "#27ae60";
			value = `<span style="color:${color}; font-weight:600;">${value}</span>`;
		}

		return value;
	},
};
