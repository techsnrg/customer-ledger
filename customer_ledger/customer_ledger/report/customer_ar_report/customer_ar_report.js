frappe.query_reports["Customer AR Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("company"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("As of Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "currency",
			label: __("Currency"),
			fieldtype: "Link",
			options: "Currency",
		},
	],

	onload: function (report) {
		function _getFilters(action) {
			var filters = report.get_filter_values();
			if (!filters || !filters.customer) {
				frappe.msgprint(__("Please select a Customer before " + action + "."));
				return null;
			}
			return filters;
		}

		function _exportPdf(include_ledger) {
			var filters = _getFilters("exporting");
			if (!filters) return;
			// Ensure to_date is set; fall back to today
			if (!filters.to_date) filters.to_date = frappe.datetime.get_today();
			// For ledger+AR we need from_date — default to FY start
			if (include_ledger && !filters.from_date) {
				var parts = filters.to_date.split("-");
				var y = parseInt(parts[0]), m = parseInt(parts[1]);
				filters.from_date = (m <= 3 ? y - 1 : y) + "-04-01";
			}
			var url = frappe.urllib.get_full_url(
				"/api/method/customer_ledger.customer_ledger.report" +
				".customer_ledger_report.customer_ledger_report.download_customer_ledger_pdf?" +
				$.param({
					filters: JSON.stringify(filters),
					include_ar: 1,
					include_ledger: include_ledger,
				})
			);
			window.open(url);
		}

		function _emailAr(include_ledger) {
			var filters = _getFilters("emailing");
			if (!filters) return;
			if (!filters.to_date) filters.to_date = frappe.datetime.get_today();
			if (include_ledger && !filters.from_date) {
				var parts = filters.to_date.split("-");
				var y = parseInt(parts[0]), m = parseInt(parts[1]);
				filters.from_date = (m <= 3 ? y - 1 : y) + "-04-01";
			}
			var msg = include_ledger
				? __("Send Ledger + AR statement to the customer's email address?")
				: __("Send AR statement to the customer's email address?");
			frappe.confirm(msg, function () {
				frappe.call({
					method: "customer_ledger.customer_ledger.report" +
						".customer_ledger_report.customer_ledger_report.email_customer_ledger",
					args: {
						filters: JSON.stringify(filters),
						include_ar: 1,
						include_ledger: include_ledger,
					},
					freeze: true,
					freeze_message: __("Sending email…"),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({
								message: __(r.message.message),
								indicator: "green",
							});
						}
					},
				});
			});
		}

		// ── Export AR dropdown ──────────────────────────────────────────────
		report.page.add_inner_button(__("Export AR"),           function () { _exportPdf(0); }, __("Export AR"));
		report.page.add_inner_button(__("Export Ledger + AR"),  function () { _exportPdf(1); }, __("Export AR"));

		// ── Email AR dropdown ───────────────────────────────────────────────
		report.page.add_inner_button(__("Email AR"),            function () { _emailAr(0); }, __("Email AR"));
		report.page.add_inner_button(__("Email Ledger + AR"),   function () { _emailAr(1); }, __("Email AR"));
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Total row — bold
		if (data.is_total) {
			value = "<strong>" + value + "</strong>";
		}

		// Section break / ageing header rows — muted italic
		if (data.is_section_break) {
			value = "<span style='color:#888;font-style:italic;'>" + (value || "") + "</span>";
		}

		// Ageing bucket rows — indent + label styling
		if (data.is_aging_row && column.fieldname === "voucher_no") {
			value = "<span style='color:#555;padding-left:12px;'>" + (value || "") + "</span>";
		}

		// Ageing days — colour by severity (matches bucket thresholds)
		if (column.fieldname === "ageing_days" && data.ageing_days != null) {
			var days = data.ageing_days;
			var color = days <= 30  ? "#27ae60"
					  : days <= 60  ? "#f39c12"
					  : days <= 75  ? "#e67e22"
					  : days <= 90  ? "#e74c3c"
					  : "#8e1a1a";
			value = "<span style='color:" + color + ";font-weight:600;'>" + days + " days</span>";
		}

		return value;
	},
};
