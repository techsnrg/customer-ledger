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
		var DEFAULT_LEDGER_FROM_DATE = "2025-04-01";

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

		function _getFilters(action) {
			var filters = report.get_filter_values();
			if (!filters || !filters.customer) {
				frappe.msgprint(__("Please select a Customer before " + action + "."));
				return null;
			}
			return filters;
		}

		function _withLedgerDefaults(filters, include_ledger) {
			var payload = Object.assign({}, filters);
			if (!payload.to_date) payload.to_date = frappe.datetime.get_today();
			if (include_ledger && !payload.from_date) {
				payload.from_date = DEFAULT_LEDGER_FROM_DATE;
			}
			return payload;
		}

		function _exportPdf(include_ledger) {
			var filters = _getFilters("exporting");
			if (!filters) return;
			filters = _withLedgerDefaults(filters, include_ledger);
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
			filters = _withLedgerDefaults(filters, include_ledger);
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
						{ group: __("Send WhatsApp AR"), include_ar: 1, include_ledger: 0 },
						{ group: __("Send WhatsApp Ledger + AR"), include_ar: 1, include_ledger: 1 },
					].forEach(function (option) {
						recipients.forEach(function (recipient) {
							var label = recipient.button_label || recipient.label || recipient.mobile;
							report.page.add_inner_button(label, function () {
								var payloadFilters = _withLedgerDefaults(filters, option.include_ledger);
								if (!recipient.mobile) {
									frappe.msgprint(__("No mobile number available. Please update the contact."));
									return;
								}

								frappe.call({
									method: "snrg_whatsapp.api.send_customer_report_whatsapp",
									args: {
										report_name: "Customer AR Report",
										recipient_mobile: recipient.mobile,
										recipient_label: label,
										filters: JSON.stringify(payloadFilters),
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

		// ── Export AR dropdown ──────────────────────────────────────────────
		report.page.add_inner_button(__("Export AR"),           function () { _exportPdf(0); }, __("Export AR"));
		report.page.add_inner_button(__("Export Ledger + AR"),  function () { _exportPdf(1); }, __("Export AR"));

		// ── Email AR dropdown ───────────────────────────────────────────────
		report.page.add_inner_button(__("Email AR"),            function () { _emailAr(0); }, __("Email AR"));
		report.page.add_inner_button(__("Email Ledger + AR"),   function () { _emailAr(1); }, __("Email AR"));

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

		if (!data) return value;

		// Total row — bold
		if (data.is_total) {
			value = "<strong>" + value + "</strong>";
		}

		// Ageing days — colour by severity
		if (column.fieldname === "ageing_days" && data.ageing_days != null && !data.is_total) {
			var days = data.ageing_days;
			var color = days <= 30  ? "#27ae60"
					  : days <= 60  ? "#f39c12"
					  : days <= 75  ? "#e67e22"
					  : days <= 90  ? "#e74c3c"
					  : "#8e1a1a";
			value = "<span style='color:" + color + ";font-weight:600;'>" + days + " days</span>";
		}

		// Bucket columns — colour header matches ageing severity, skip total row styling
		var bucketColors = { b0: "#27ae60", b31: "#f39c12", b61: "#e67e22", b76: "#e74c3c", b90: "#8e1a1a" };
		if (bucketColors[column.fieldname] && !data.is_total && value && value !== "0.00" && value !== "₹ 0.00") {
			value = "<span style='color:" + bucketColors[column.fieldname] + ";font-weight:600;'>" + value + "</span>";
		}

		return value;
	},
};
