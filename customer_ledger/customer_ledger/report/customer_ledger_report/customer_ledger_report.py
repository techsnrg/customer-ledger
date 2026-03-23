"""
Customer Ledger Report
Generates a formatted ledger for a specific customer between two dates,
including company header, customer details, opening balance, transactions,
and closing balance.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate


# ---------------------------------------------------------------------------
# Filters definition (rendered in the Report Builder UI)
# ---------------------------------------------------------------------------

def get_filters():
    return [
        {
            "fieldname": "company",
            "label": _("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1,
        },
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "reqd": 1,
        },
        {
            "fieldname": "from_date",
            "label": _("From Date"),
            "fieldtype": "Date",
            "default": frappe.utils.get_first_day(nowdate()),
            "reqd": 1,
        },
        {
            "fieldname": "to_date",
            "label": _("To Date"),
            "fieldtype": "Date",
            "default": nowdate(),
            "reqd": 1,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Link",
            "options": "Currency",
        },
        {
            "fieldname": "show_cancelled",
            "label": _("Include Cancelled Entries"),
            "fieldtype": "Check",
            "default": 0,
        },
    ]


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

def get_columns(filters):
    currency = _get_currency(filters)
    return [
        {
            "fieldname": "posting_date",
            "label": _("Date"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "voucher_type",
            "label": _("Type"),
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "voucher_no",
            "label": _("Voucher No"),
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 160,
        },
        {
            "fieldname": "remarks",
            "label": _("Remarks"),
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "fieldname": "debit",
            "label": _("Debit ({0})".format(currency)),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "credit",
            "label": _("Credit ({0})".format(currency)),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "fieldname": "balance",
            "label": _("Balance ({0})".format(currency)),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "fieldname": "currency",
            "label": _("Currency"),
            "fieldtype": "Currency",
            "hidden": 1,
        },
    ]


# ---------------------------------------------------------------------------
# Main execute function called by ERPNext
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    columns = get_columns(filters)
    data = _get_data(filters)

    # Build the custom HTML header (shown when printing / PDF)
    report_summary = _get_report_summary(filters, data)

    return columns, data, None, None, report_summary


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_filters(filters):
    if filters.from_date and filters.to_date:
        if getdate(filters.from_date) > getdate(filters.to_date):
            frappe.throw(_("From Date cannot be greater than To Date"))


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _get_data(filters):
    currency = _get_currency(filters)

    # 1. Fetch the receivable account(s) linked to the customer's party
    party_account = _get_party_account(filters)
    if not party_account:
        frappe.msgprint(_("No receivable account found for this customer."))
        return []

    # 2. Opening balance (all entries BEFORE from_date)
    opening_balance = _get_opening_balance(filters, party_account)

    # 3. Transactions within the date range
    gl_entries = _get_gl_entries(filters, party_account)

    # 4. Build result rows
    data = []

    # Opening balance row
    data.append(
        _make_opening_row(opening_balance, currency, filters.from_date)
    )

    running_balance = opening_balance
    for entry in gl_entries:
        running_balance += flt(entry.debit) - flt(entry.credit)
        data.append(
            {
                "posting_date": entry.posting_date,
                "voucher_type": entry.voucher_type,
                "voucher_no": entry.voucher_no,
                "remarks": entry.remarks or "",
                "debit": flt(entry.debit),
                "credit": flt(entry.credit),
                "balance": running_balance,
                "currency": currency,
                "indent": 0,
            }
        )

    # Closing / total row
    total_debit = sum(flt(r.get("debit", 0)) for r in data[1:])
    total_credit = sum(flt(r.get("credit", 0)) for r in data[1:])
    data.append(
        {
            "posting_date": None,
            "voucher_type": "",
            "voucher_no": "",
            "remarks": _("Closing Balance"),
            "debit": total_debit,
            "credit": total_credit,
            "balance": running_balance,
            "currency": currency,
            "bold": 1,
        }
    )

    return data


def _get_party_account(filters):
    """Return the default receivable account for the customer's company."""
    account = frappe.db.get_value(
        "Party Account",
        {"parenttype": "Customer", "parent": filters.customer, "company": filters.company},
        "account",
    )
    if not account:
        # Fall back to the company's default receivable account
        account = frappe.db.get_value(
            "Company", filters.company, "default_receivable_account"
        )
    return account


def _get_opening_balance(filters, party_account):
    """Sum of (debit - credit) for all GL entries before from_date."""
    result = frappe.db.sql(
        """
        SELECT
            SUM(debit_in_account_currency) - SUM(credit_in_account_currency) AS balance
        FROM `tabGL Entry`
        WHERE
            company = %(company)s
            AND account = %(account)s
            AND party_type = 'Customer'
            AND party = %(customer)s
            AND posting_date < %(from_date)s
            AND is_cancelled = 0
        """,
        {
            "company": filters.company,
            "account": party_account,
            "customer": filters.customer,
            "from_date": filters.from_date,
        },
        as_dict=True,
    )
    return flt(result[0].balance) if result else 0.0


def _get_gl_entries(filters, party_account):
    """GL entries within the selected date range."""
    cancelled_condition = "" if filters.get("show_cancelled") else "AND gle.is_cancelled = 0"

    return frappe.db.sql(
        """
        SELECT
            gle.posting_date,
            gle.voucher_type,
            gle.voucher_no,
            gle.remarks,
            gle.debit_in_account_currency  AS debit,
            gle.credit_in_account_currency AS credit
        FROM `tabGL Entry` gle
        WHERE
            gle.company = %(company)s
            AND gle.account = %(account)s
            AND gle.party_type = 'Customer'
            AND gle.party = %(customer)s
            AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
            {cancelled_condition}
        ORDER BY gle.posting_date ASC, gle.creation ASC
        """.format(cancelled_condition=cancelled_condition),
        {
            "company": filters.company,
            "account": party_account,
            "customer": filters.customer,
            "from_date": filters.from_date,
            "to_date": filters.to_date,
        },
        as_dict=True,
    )


def _make_opening_row(opening_balance, currency, from_date):
    return {
        "posting_date": from_date,
        "voucher_type": "",
        "voucher_no": "",
        "remarks": _("Opening Balance"),
        "debit": opening_balance if opening_balance > 0 else 0.0,
        "credit": abs(opening_balance) if opening_balance < 0 else 0.0,
        "balance": opening_balance,
        "currency": currency,
        "bold": 1,
    }


# ---------------------------------------------------------------------------
# Report summary (used by ERPNext's print/PDF template)
# ---------------------------------------------------------------------------

def _get_report_summary(filters, data):
    """
    Returns a dict with extra context used by the Jinja print template.
    Also builds the HTML header block for the report.
    """
    company_doc = frappe.get_doc("Company", filters.company)
    customer_doc = frappe.get_doc("Customer", filters.customer)

    # Try to get customer's primary address
    customer_address = _get_customer_address(filters.customer)

    closing_balance = flt(data[-1].get("balance", 0)) if data else 0.0
    currency = _get_currency(filters)

    return {
        "company_name": company_doc.company_name,
        "company_address": _get_company_address(filters.company),
        "company_phone": company_doc.get("phone_no") or "",
        "company_email": company_doc.get("email") or "",
        "company_tax_id": company_doc.get("tax_id") or "",
        "company_logo": company_doc.get("company_logo") or "",
        "customer_name": customer_doc.customer_name,
        "customer_code": customer_doc.name,
        "customer_address": customer_address,
        "customer_tax_id": customer_doc.get("tax_id") or "",
        "from_date": formatdate(filters.from_date),
        "to_date": formatdate(filters.to_date),
        "currency": currency,
        "closing_balance": closing_balance,
        "report_html_header": _build_html_header(
            company_doc, customer_doc, customer_address, filters, closing_balance, currency
        ),
    }


def _get_company_address(company):
    address = frappe.db.sql(
        """
        SELECT
            CONCAT_WS(', ',
                NULLIF(a.address_line1, ''),
                NULLIF(a.address_line2, ''),
                NULLIF(a.city, ''),
                NULLIF(a.state, ''),
                NULLIF(a.pincode, ''),
                NULLIF(a.country, '')
            ) AS full_address
        FROM `tabAddress` a
        INNER JOIN `tabDynamic Link` dl
            ON dl.parent = a.name
            AND dl.link_doctype = 'Company'
            AND dl.link_name = %(company)s
        WHERE a.is_primary_address = 1
        LIMIT 1
        """,
        {"company": company},
        as_dict=True,
    )
    return address[0].full_address if address else ""


def _get_customer_address(customer):
    address = frappe.db.sql(
        """
        SELECT
            CONCAT_WS(', ',
                NULLIF(a.address_line1, ''),
                NULLIF(a.address_line2, ''),
                NULLIF(a.city, ''),
                NULLIF(a.state, ''),
                NULLIF(a.pincode, ''),
                NULLIF(a.country, '')
            ) AS full_address
        FROM `tabAddress` a
        INNER JOIN `tabDynamic Link` dl
            ON dl.parent = a.name
            AND dl.link_doctype = 'Customer'
            AND dl.link_name = %(customer)s
        WHERE a.is_primary_address = 1
        LIMIT 1
        """,
        {"customer": customer},
        as_dict=True,
    )
    return address[0].full_address if address else ""


def _get_currency(filters):
    if filters.get("currency"):
        return filters.currency
    return frappe.db.get_value("Company", filters.get("company"), "default_currency") or "USD"


# ---------------------------------------------------------------------------
# HTML header builder
# ---------------------------------------------------------------------------

def _build_html_header(company_doc, customer_doc, customer_address, filters, closing_balance, currency):
    """
    Returns an HTML string rendered at the top of the printed/PDF report.
    The inline CSS ensures it looks clean without any external stylesheet.
    """
    logo_html = ""
    if company_doc.get("company_logo"):
        logo_html = '<img src="{src}" style="max-height:70px; max-width:200px;" alt="logo">'.format(
            src=company_doc.company_logo
        )

    balance_label = _("Balance Due") if closing_balance >= 0 else _("Credit Balance")
    balance_color = "#c0392b" if closing_balance >= 0 else "#27ae60"
    balance_display = frappe.utils.fmt_money(abs(closing_balance), currency=currency)

    phone_row = (
        '<tr><td style="color:#666;padding:1px 0;">{label}:</td>'
        '<td style="padding:1px 0 1px 8px;">{val}</td></tr>'.format(
            label=_("Phone"), val=company_doc.get("phone_no", "")
        )
        if company_doc.get("phone_no")
        else ""
    )
    email_row = (
        '<tr><td style="color:#666;padding:1px 0;">{label}:</td>'
        '<td style="padding:1px 0 1px 8px;">{val}</td></tr>'.format(
            label=_("Email"), val=company_doc.get("email", "")
        )
        if company_doc.get("email")
        else ""
    )
    tax_id_row = (
        '<tr><td style="color:#666;padding:1px 0;">{label}:</td>'
        '<td style="padding:1px 0 1px 8px;">{val}</td></tr>'.format(
            label=_("Tax ID"), val=company_doc.get("tax_id", "")
        )
        if company_doc.get("tax_id")
        else ""
    )

    customer_tax_row = (
        '<tr><td style="color:#555;width:110px;padding:2px 0;">{label}:</td>'
        '<td style="padding:2px 0 2px 8px;">{val}</td></tr>'.format(
            label=_("Tax ID"), val=customer_doc.get("tax_id", "")
        )
        if customer_doc.get("tax_id")
        else ""
    )

    html = """
<div style="
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: #2c3e50;
    margin-bottom: 18px;
    border-bottom: 3px solid #2c3e50;
    padding-bottom: 14px;
">
    <!-- Top bar: logo + company info on left, report title on right -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
        <tr>
            <!-- Left: Logo + Company Details -->
            <td style="vertical-align:top; width:55%;">
                <div style="margin-bottom:6px;">{logo_html}</div>
                <div style="font-size:17px; font-weight:700; letter-spacing:0.3px;">
                    {company_name}
                </div>
                <div style="font-size:11px; color:#555; margin-top:4px; line-height:1.5;">
                    {company_address}
                </div>
                <table style="font-size:11px; margin-top:4px; color:#333;" cellpadding="0" cellspacing="0">
                    {phone_row}
                    {email_row}
                    {tax_id_row}
                </table>
            </td>

            <!-- Right: Report Title + Date Range -->
            <td style="vertical-align:top; text-align:right; width:45%;">
                <div style="
                    font-size:20px;
                    font-weight:700;
                    color:#2c3e50;
                    letter-spacing:0.5px;
                    margin-bottom:6px;
                ">
                    {report_title}
                </div>
                <div style="font-size:12px; color:#555; line-height:1.8;">
                    <span style="font-weight:600;">{period_label}:</span>
                    {from_date} &mdash; {to_date}
                </div>
                <div style="
                    margin-top:10px;
                    display:inline-block;
                    background:{balance_color};
                    color:#fff;
                    padding:6px 16px;
                    border-radius:4px;
                    font-size:13px;
                    font-weight:700;
                    letter-spacing:0.3px;
                ">
                    {balance_label}: {currency} {balance_display}
                </div>
            </td>
        </tr>
    </table>

    <!-- Divider -->
    <div style="border-top:1px solid #dce1e7; margin: 10px 0;"></div>

    <!-- Customer detail block -->
    <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
            <td style="vertical-align:top; width:50%;">
                <div style="
                    background:#f4f6f8;
                    border-left:4px solid #2c3e50;
                    padding:10px 14px;
                    border-radius:0 4px 4px 0;
                ">
                    <div style="font-size:11px; font-weight:700; color:#888;
                                text-transform:uppercase; letter-spacing:0.8px;
                                margin-bottom:6px;">
                        {bill_to_label}
                    </div>
                    <div style="font-size:14px; font-weight:700; color:#2c3e50;
                                margin-bottom:3px;">
                        {customer_name}
                    </div>
                    <div style="font-size:11px; color:#666; margin-bottom:3px;">
                        <span style="color:#888;">{customer_code_label}:</span>
                        {customer_code}
                    </div>
                    <div style="font-size:11px; color:#555; line-height:1.5;">
                        {customer_address}
                    </div>
                    <table style="font-size:11px; margin-top:4px; color:#333;"
                           cellpadding="0" cellspacing="0">
                        {customer_tax_row}
                    </table>
                </div>
            </td>
        </tr>
    </table>
</div>
""".format(
        logo_html=logo_html,
        company_name=company_doc.company_name,
        company_address=company_doc.get("company_address", "") or "",
        phone_row=phone_row,
        email_row=email_row,
        tax_id_row=tax_id_row,
        report_title=_("Customer Ledger Statement"),
        period_label=_("Period"),
        from_date=formatdate(filters.from_date),
        to_date=formatdate(filters.to_date),
        balance_color=balance_color,
        balance_label=balance_label,
        currency=currency,
        balance_display=balance_display,
        bill_to_label=_("Bill To"),
        customer_name=customer_doc.customer_name,
        customer_code_label=_("Customer Code"),
        customer_code=customer_doc.name,
        customer_address=customer_address or "&mdash;",
        customer_tax_row=customer_tax_row,
    )

    return html
