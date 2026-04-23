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
			// Ledger statements should always start from the fixed cutoff date.
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
			label: __("Include Adjustment Entries"),
			fieldtype: "Check",
			default: 1,
		},
	],

	onload: function (report) {
		function _clearWhatsAppButtons() {
			(report.__wa_button_entries || []).forEach(function (entry) {
				report.page.remove_inner_button(entry.label, entry.group);
			});
			report.__wa_button_entries = [];
		}

		function _rememberWhatsAppButton(label, group) {
			report.__wa_button_entries = report.__wa_button_entries || [];
			report.__wa_button_entries.push({ label: label, group: group });
		}

		// Wire Check filters to trigger a report re-run on toggle.
		// Frappe's query-report does NOT auto-refresh for Check fields, and
		// get_filter_values() drops falsy (0) values so Python must default
		// to 0 — the JS default:1 ensures the first run always sends 1.
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

		function _getFilters(action) {
			var filters = report.get_filter_values();
			if (!filters || !filters.customer) {
				frappe.msgprint(__("Please select a Customer before " + action + "."));
				return null;
			}
			return filters;
		}

		function _exportPdf(include_ar) {
			var filters = _getFilters("exporting");
			if (!filters) return;
			var url = frappe.urllib.get_full_url(
				"/api/method/customer_ledger.customer_ledger.report" +
				".customer_ledger_report.customer_ledger_report.download_customer_ledger_pdf?" +
				$.param({ filters: JSON.stringify(filters), include_ar: include_ar })
			);
			window.open(url);
		}

		function _emailLedger(include_ar) {
			var filters = _getFilters("emailing");
			if (!filters) return;
			var msg = include_ar
				? __("Send Ledger + AR statement to the customer's email address?")
				: __("Send Ledger statement to the customer's email address?");
			frappe.confirm(msg, function () {
				frappe.call({
					method: "customer_ledger.customer_ledger.report" +
						".customer_ledger_report.customer_ledger_report.email_customer_ledger",
					args: { filters: JSON.stringify(filters), include_ar: include_ar },
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

		function _loadWhatsAppButtons() {
			var filters = _getFilters("sending WhatsApp");
			_clearWhatsAppButtons();
			if (!filters) return;

			frappe.call({
				method: "snrg_whatsapp.api.get_manual_whatsapp_recipients",
				args: { customer: filters.customer },
				callback: function (r) {
					var recipients = (r.message && r.message.recipients) || [];
					if (!recipients.length) return;

					[
						{ group: __("Send WhatsApp Ledger"), include_ar: 0, include_ledger: 1 },
						{ group: __("Send WhatsApp Ledger + AR"), include_ar: 1, include_ledger: 1 },
					].forEach(function (option) {
						recipients.forEach(function (recipient) {
							var label = recipient.button_label || recipient.label || recipient.mobile;
							report.page.add_inner_button(label, function () {
								if (!recipient.mobile) {
									frappe.msgprint(__("No mobile number available. Please update the contact."));
									return;
								}

								frappe.call({
									method: "snrg_whatsapp.api.send_customer_report_whatsapp",
									args: {
										report_name: "Customer Ledger Report",
										recipient_mobile: recipient.mobile,
										recipient_label: label,
										filters: JSON.stringify(filters),
										include_ar: option.include_ar,
										include_ledger: option.include_ledger,
									},
									freeze: true,
									freeze_message: __("Sending WhatsApp…"),
									callback: function (send_r) {
										if (send_r.message) {
											frappe.show_alert({
												message: __(send_r.message.message),
												indicator: "green",
											});
										}
									},
								});
							}, option.group);
							_rememberWhatsAppButton(label, option.group);
						});
					});
				},
			});
		}

		// ── Export Ledger dropdown ──────────────────────────────────────────
		report.page.add_inner_button(__("Export Ledger"),       function () { _exportPdf(0); }, __("Export Ledger"));
		report.page.add_inner_button(__("Export Ledger + AR"),  function () { _exportPdf(1); }, __("Export Ledger"));

		// ── Email Ledger dropdown ───────────────────────────────────────────
		report.page.add_inner_button(__("Email Ledger"),        function () { _emailLedger(0); }, __("Email Ledger"));
		report.page.add_inner_button(__("Email Ledger + AR"),   function () { _emailLedger(1); }, __("Email Ledger"));

		setTimeout(() => {
			const df = report.get_filter("customer");
			if (df && df.$input) {
				df.$input.on("change", () => setTimeout(_loadWhatsAppButtons, 300));
			}
			_loadWhatsAppButtons();
		}, 500);
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
