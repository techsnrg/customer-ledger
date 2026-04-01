// Supplier AP Report - Client-side filter configuration

frappe.query_reports["Supplier AP Report"] = {
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
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			reqd: 1,
			get_query: function () {
				return { filters: { disabled: 0 } };
			},
		},
		{
			fieldname: "to_date",
			label: __("As of Date"),
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
	],

	onload: function (report) {
		function _getFilters(action) {
			var filters = report.get_filter_values();
			if (!filters || !filters.supplier) {
				frappe.msgprint(__("Please select a Supplier before " + action + "."));
				return null;
			}
			return filters;
		}

		function _exportPdf(include_ledger) {
			var filters = _getFilters("exporting");
			if (!filters) return;
			var url = frappe.urllib.get_full_url(
				"/api/method/customer_ledger.customer_ledger.report" +
				".supplier_ledger_report.supplier_ledger_report.download_supplier_ledger_pdf?" +
				$.param({
					filters: JSON.stringify(frappe.utils.merge(filters, {
						from_date: filters.from_date || "2025-04-01",
					})),
					include_ap: 1,
					include_ledger: include_ledger,
				})
			);
			window.open(url);
		}

		function _emailLedger(include_ledger) {
			var filters = _getFilters("emailing");
			if (!filters) return;
			var msg = include_ledger
				? __("Send Ledger + AP statement to the supplier's email address?")
				: __("Send AP statement to the supplier's email address?");
			frappe.confirm(msg, function () {
				frappe.call({
					method: "customer_ledger.customer_ledger.report" +
						".supplier_ledger_report.supplier_ledger_report.email_supplier_ledger",
					args: {
						filters: JSON.stringify(frappe.utils.merge(filters, {
							from_date: filters.from_date || "2025-04-01",
						})),
						include_ap: 1,
						include_ledger: include_ledger,
					},
					freeze: true,
					freeze_message: __("Sending email…"),
					callback: function (r) {
						if (r.message) {
							frappe.show_alert({ message: __(r.message.message), indicator: "green" });
						}
					},
				});
			});
		}

		// ── Export AP dropdown ──────────────────────────────────────────────
		report.page.add_inner_button(__("Export AP"),           function () { _exportPdf(0); }, __("Export AP"));
		report.page.add_inner_button(__("Export Ledger + AP"),  function () { _exportPdf(1); }, __("Export AP"));

		// ── Email AP dropdown ───────────────────────────────────────────────
		report.page.add_inner_button(__("Email AP"),            function () { _emailLedger(0); }, __("Email AP"));
		report.page.add_inner_button(__("Email Ledger + AP"),   function () { _emailLedger(1); }, __("Email AP"));
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_total) {
			value = `<strong>${value}</strong>`;
		}

		if (column.fieldname === "ageing_days" && data && data.ageing_days != null) {
			var days = data.ageing_days;
			var color = days <= 30 ? "#27ae60"
				: days <= 60 ? "#f39c12"
				: days <= 75 ? "#e67e22"
				: days <= 90 ? "#e74c3c"
				: "#8e1a1a";
			if (days > 0) {
				value = `<span style="color:${color};font-weight:600;">${days} days</span>`;
			}
		}

		return value;
	},
};
