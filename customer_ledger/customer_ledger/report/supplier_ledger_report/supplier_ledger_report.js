// Supplier Ledger Report - Client-side filter configuration

frappe.query_reports["Supplier Ledger Report"] = {
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
		setTimeout(function () {
			["show_cancelled", "group_by_account", "include_journal_entries"].forEach(function (fn) {
				var f = report.get_filter(fn);
				if (f && f.$input) {
					f.$input.off("change.sl_report").on("change.sl_report", function () {
						report.refresh();
					});
				}
			});
		}, 500);

		function _getFilters(action) {
			var filters = report.get_filter_values();
			if (!filters || !filters.supplier) {
				frappe.msgprint(__("Please select a Supplier before " + action + "."));
				return null;
			}
			return filters;
		}

		function _exportPdf(include_ap) {
			var filters = _getFilters("exporting");
			if (!filters) return;
			var url = frappe.urllib.get_full_url(
				"/api/method/customer_ledger.customer_ledger.report" +
				".supplier_ledger_report.supplier_ledger_report.download_supplier_ledger_pdf?" +
				$.param({ filters: JSON.stringify(filters), include_ap: include_ap })
			);
			window.open(url);
		}

		function _emailLedger(include_ap) {
			var filters = _getFilters("emailing");
			if (!filters) return;
			var msg = include_ap
				? __("Send Ledger + AP statement to the supplier's email address?")
				: __("Send Ledger statement to the supplier's email address?");
			frappe.confirm(msg, function () {
				frappe.call({
					method: "customer_ledger.customer_ledger.report" +
						".supplier_ledger_report.supplier_ledger_report.email_supplier_ledger",
					args: { filters: JSON.stringify(filters), include_ap: include_ap },
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

		// ── Export Ledger dropdown ──────────────────────────────────────────
		report.page.add_inner_button(__("Export Ledger"),       function () { _exportPdf(0); }, __("Export Ledger"));
		report.page.add_inner_button(__("Export Ledger + AP"),  function () { _exportPdf(1); }, __("Export Ledger"));

		// ── Email Ledger dropdown ───────────────────────────────────────────
		report.page.add_inner_button(__("Email Ledger"),        function () { _emailLedger(0); }, __("Email Ledger"));
		report.page.add_inner_button(__("Email Ledger + AP"),   function () { _emailLedger(1); }, __("Email Ledger"));
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (data && data.is_group) {
			return `<strong>${value}</strong>`;
		}

		if (
			data &&
			(data.remarks === __("Opening Balance") || data.remarks === __("Closing Balance"))
		) {
			value = `<strong>${value}</strong>`;
		}

		// For supplier: debit = payments made (green), credit = bills (red)
		if (column.fieldname === "debit" && data && data.debit > 0) {
			value = `<span style="color:#27ae60;">${value}</span>`;
		}
		if (column.fieldname === "credit" && data && data.credit > 0) {
			value = `<span style="color:#c0392b;">${value}</span>`;
		}

		// Balance: positive = we owe supplier (red), negative = advance (green)
		if (column.fieldname === "balance" && data && data.balance !== null) {
			const color = data.balance >= 0 ? "#c0392b" : "#27ae60";
			value = `<span style="color:${color}; font-weight:600;">${value}</span>`;
		}

		return value;
	},
};
