"""
Customer Ledger Report
Script Report for ERPNext — shows a formatted ledger for one customer
between two dates with opening balance, transactions and closing balance.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, nowdate


# ---------------------------------------------------------------------------
# Column definitions  (filters are defined in customer_ledger_report.js)
# ---------------------------------------------------------------------------

def get_columns(filters):
    currency = _get_currency(filters)
    return [
        {"fieldname": "posting_date", "label": _("Date"),        "fieldtype": "Date",         "width": 100},
        {"fieldname": "voucher_type",    "label": _("Type"),           "fieldtype": "Data",         "width": 130},
        {"fieldname": "voucher_subtype", "label": _("Subtype"),        "fieldtype": "Data",         "width": 110},
        {"fieldname": "voucher_no",      "label": _("Voucher No"),     "fieldtype": "Dynamic Link",
         "options": "voucher_type",                                                                  "width": 160},
        {"fieldname": "remarks",      "label": _("Remarks"),     "fieldtype": "Data",         "width": 220},
        {"fieldname": "debit",        "label": _("Amount ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                       "width": 130},
        {"fieldname": "credit",       "label": _("Payments ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                       "width": 130},
        {"fieldname": "balance",      "label": _("Balance ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                       "width": 140},
        {"fieldname": "currency",     "label": _("Currency"),   "fieldtype": "Currency",     "hidden": 1},
    ]


# ---------------------------------------------------------------------------
# Main execute — called by the Frappe report engine
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _validate_filters(filters)

    columns      = get_columns(filters)
    data         = _get_data(filters)
    html_header  = _build_screen_header(filters, data)
    summary      = _build_summary_cards(filters, data)

    return columns, data, html_header, None, summary


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
    currency         = _get_currency(filters)
    opening_balance  = _get_opening_balance(filters)
    gl_entries       = _get_gl_entries(filters)
    group_by_account = cint(filters.get("group_by_account", 0))

    data             = [_make_opening_row(opening_balance, currency, filters.from_date)]
    running_balance  = opening_balance
    current_account  = None

    for entry in gl_entries:
        if group_by_account and entry.account != current_account:
            current_account = entry.account
            data.append({
                "posting_date": None, "voucher_type": "", "voucher_no": "",
                "remarks": current_account, "debit": None, "credit": None,
                "balance": None, "currency": currency, "bold": 1, "is_group": 1,
            })

        running_balance += flt(entry.debit) - flt(entry.credit)
        data.append({
            "posting_date":    entry.posting_date,
            "voucher_type":    entry.voucher_type,
            "voucher_subtype": entry.voucher_subtype or "",
            "voucher_no":      entry.voucher_no,
            "remarks":         entry.remarks or "",
            "debit":           flt(entry.debit),
            "credit":          flt(entry.credit),
            "balance":         running_balance,
            "currency":        currency,
            "indent":          1 if group_by_account else 0,
        })

    total_debit  = sum(flt(r.get("debit",  0)) for r in data[1:])
    total_credit = sum(flt(r.get("credit", 0)) for r in data[1:])
    data.append({
        "posting_date": None, "voucher_type": "", "voucher_no": "",
        "remarks": _("Closing Balance"),
        "debit":   total_debit,  "credit": total_credit,
        "balance": running_balance, "currency": currency, "bold": 1,
    })
    return data


def _get_opening_balance(filters):
    result = frappe.db.sql(
        """
        SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency) AS balance
        FROM `tabGL Entry`
        WHERE company    = %(company)s
          AND party_type = 'Customer'
          AND party      = %(customer)s
          AND posting_date < %(from_date)s
          AND is_cancelled = 0
        """,
        {"company": filters.company, "customer": filters.customer, "from_date": filters.from_date},
        as_dict=True,
    )
    return flt(result[0].balance) if result else 0.0


def _get_gl_entries(filters):
    show_cancelled   = cint(filters.get("show_cancelled",         0))
    include_je       = cint(filters.get("include_journal_entries", 0))
    group_by_account = cint(filters.get("group_by_account",        0))

    cancelled_cond = "" if show_cancelled else "AND gle.is_cancelled = 0"
    je_cond        = "" if include_je     else "AND gle.voucher_type != 'Journal Entry'"
    order_by       = (
        "gle.account ASC, gle.posting_date ASC, gle.voucher_no ASC"
        if group_by_account else
        "gle.posting_date ASC, gle.voucher_no ASC"
    )

    return frappe.db.sql(
        """
        SELECT
            gle.posting_date, gle.account, gle.voucher_type,
            MAX(gle.voucher_subtype)           AS voucher_subtype,
            gle.voucher_no,
            MAX(gle.remarks)                   AS remarks,
            SUM(gle.debit_in_account_currency) AS debit,
            SUM(gle.credit_in_account_currency)AS credit
        FROM `tabGL Entry` gle
        WHERE gle.company    = %(company)s
          AND gle.party_type = 'Customer'
          AND gle.party      = %(customer)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {cancelled_cond}
          {je_cond}
        GROUP BY gle.posting_date, gle.account, gle.voucher_type, gle.voucher_no
        ORDER BY {order_by}
        """.format(cancelled_cond=cancelled_cond, je_cond=je_cond, order_by=order_by),
        {"company": filters.company, "customer": filters.customer,
         "from_date": filters.from_date, "to_date": filters.to_date},
        as_dict=True,
    )


def _make_opening_row(opening_balance, currency, from_date):
    return {
        "posting_date": from_date,
        "voucher_type": "", "voucher_no": "",
        "remarks": _("Opening Balance"),
        "debit":   opening_balance if opening_balance > 0 else 0.0,
        "credit":  abs(opening_balance) if opening_balance < 0 else 0.0,
        "balance": opening_balance,
        "currency": currency, "bold": 1,
    }


# ---------------------------------------------------------------------------
# Screen header (3rd execute() return — rendered as HTML above the table)
# ---------------------------------------------------------------------------

def _build_screen_header(filters, data):
    company_doc      = frappe.get_doc("Company", filters.company)
    customer_doc     = frappe.get_doc("Customer", filters.customer)
    customer_address = _get_customer_address(filters.customer)
    closing_balance  = flt(data[-1].get("balance", 0)) if data else 0.0
    currency         = _get_currency(filters)

    logo_html = (
        '<img src="{}" style="max-height:70px;max-width:200px;" alt="logo">'.format(company_doc.company_logo)
        if company_doc.get("company_logo") else ""
    )
    balance_label = _("Balance Due") if closing_balance >= 0 else _("Credit Balance")
    balance_color = "#c0392b" if closing_balance >= 0 else "#27ae60"

    def _row(label, val):
        return ('<tr><td style="color:#666;padding:1px 0;">{l}:</td>'
                '<td style="padding:1px 0 1px 8px;">{v}</td></tr>').format(l=label, v=val) if val else ""

    return """
<div style="font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:13px;
            color:#2c3e50;margin-bottom:18px;border-bottom:3px solid #2c3e50;padding-bottom:14px;">
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
    <tr>
      <td style="vertical-align:top;width:55%;">
        <div style="margin-bottom:6px;">{logo}</div>
        <div style="font-size:17px;font-weight:700;">{company}</div>
        <div style="font-size:11px;color:#555;margin-top:4px;line-height:1.5;">{company_addr}</div>
        <table style="font-size:11px;margin-top:4px;color:#333;" cellpadding="0" cellspacing="0">
          {phone}{email}{tax}
        </table>
      </td>
      <td style="vertical-align:top;text-align:right;width:45%;">
        <div style="font-size:20px;font-weight:700;letter-spacing:.5px;margin-bottom:6px;">
          {title}</div>
        <div style="font-size:12px;color:#555;line-height:1.8;">
          <span style="font-weight:600;">{period_lbl}:</span> {from_d} &mdash; {to_d}</div>
        <div style="margin-top:10px;display:inline-block;background:{bal_color};color:#fff;
                    padding:6px 16px;border-radius:4px;font-size:13px;font-weight:700;">
          {bal_label}: {currency} {bal_amt}</div>
      </td>
    </tr>
  </table>
  <div style="border-top:1px solid #dce1e7;margin:10px 0;"></div>
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td style="vertical-align:top;width:50%;">
        <div style="background:#f4f6f8;border-left:4px solid #2c3e50;
                    padding:10px 14px;border-radius:0 4px 4px 0;">
          <div style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;
                      letter-spacing:.8px;margin-bottom:6px;">{bill_to}</div>
          <div style="font-size:14px;font-weight:700;color:#2c3e50;margin-bottom:3px;">
            {cust_name}</div>
          <div style="font-size:11px;color:#666;margin-bottom:3px;">
            <span style="color:#888;">{code_lbl}:</span> {cust_code}</div>
          <div style="font-size:11px;color:#555;line-height:1.5;">{cust_addr}</div>
          {cust_tax}
        </div>
      </td>
    </tr>
  </table>
</div>""".format(
        logo=logo_html,
        company=company_doc.company_name,
        company_addr=company_doc.get("company_address", "") or "",
        phone=_row(_("Phone"), company_doc.get("phone_no")),
        email=_row(_("Email"), company_doc.get("email")),
        tax=_row(_("Tax ID"), company_doc.get("tax_id")),
        title=_("Customer Ledger Statement"),
        period_lbl=_("Period"),
        from_d=formatdate(filters.from_date),
        to_d=formatdate(filters.to_date),
        bal_color=balance_color,
        bal_label=balance_label,
        currency=currency,
        bal_amt=fmt_money(abs(closing_balance), currency=currency),
        bill_to=_("Bill To"),
        cust_name=customer_doc.customer_name,
        code_lbl=_("Customer Code"),
        cust_code=customer_doc.name,
        cust_addr=customer_address or "&mdash;",
        cust_tax=_row(_("Tax ID"), customer_doc.get("tax_id")),
    )


# ---------------------------------------------------------------------------
# Summary cards (5th execute() return)
# ---------------------------------------------------------------------------

def _build_summary_cards(filters, data):
    currency     = _get_currency(filters)
    closing      = flt(data[-1].get("balance", 0)) if data else 0.0
    total_debit  = sum(flt(r.get("debit",  0)) for r in data[1:-1])
    total_credit = sum(flt(r.get("credit", 0)) for r in data[1:-1])
    return [
        {"value": total_debit,  "label": _("Total Invoiced"), "datatype": "Currency", "currency": currency},
        {"value": total_credit, "label": _("Total Received"), "datatype": "Currency", "currency": currency},
        {
            "value": abs(closing),
            "label": _("Balance Due") if closing >= 0 else _("Credit Balance"),
            "datatype": "Currency", "currency": currency,
            "indicator": "Red" if closing > 0 else "Green",
        },
    ]


# ---------------------------------------------------------------------------
# PDF export  (called from the "Export Ledger" button via whitelisted API)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_customer_ledger_pdf(filters):
    from frappe.utils.pdf import get_pdf

    if isinstance(filters, str):
        filters = frappe._dict(json.loads(filters))
    else:
        filters = frappe._dict(filters or {})

    _validate_filters(filters)

    currency        = _get_currency(filters)
    company_doc     = frappe.get_doc("Company", filters.company)
    customer_doc    = frappe.get_doc("Customer", filters.customer)
    company_addr    = _get_company_address(filters.company)
    customer_addr   = _get_customer_address(filters.customer)
    opening_balance = _get_opening_balance(filters)
    gl_entries      = _get_gl_entries(filters)

    # Build transaction rows + running totals
    running   = opening_balance
    total_inv = 0.0
    total_rec = 0.0
    rows_html = ""

    rows_html += _pdf_row(
        formatdate(filters.from_date), "Opening Balance", "",
        _fmt(opening_balance if opening_balance > 0 else 0, currency),
        _fmt(abs(opening_balance) if opening_balance < 0 else 0, currency),
        _fmt(opening_balance, currency), bold=True,
    )

    for e in gl_entries:
        debit  = flt(e.debit)
        credit = flt(e.credit)
        running   += debit - credit
        total_inv += debit
        total_rec += credit
        rows_html += _pdf_row(
            formatdate(e.posting_date),
            e.voucher_type,
            "{}{}<br><small style='color:#666'>{}</small>".format(
                e.voucher_no,
                " <em>({})</em>".format(e.voucher_subtype) if e.voucher_subtype else "",
                e.remarks or "",
            ),
            _fmt(debit,  currency) if debit  else "",
            _fmt(credit, currency) if credit else "",
            _fmt(running, currency),
        )

    rows_html += _pdf_row("", "<strong>Closing Balance</strong>", "",
                          _fmt(total_inv, currency), _fmt(total_rec, currency),
                          _fmt(running, currency), bold=True)

    closing     = running
    bal_label   = _("Balance Due") if closing >= 0 else _("Credit Balance")
    bal_color   = "#c0392b" if closing >= 0 else "#27ae60"

    def _info(label, val):
        return "<tr><td>{l}</td><td style='text-align:right'><strong>{v}</strong></td></tr>".format(
            l=label, v=val) if val else ""

    logo_html = (
        '<img src="{}" style="max-height:60px;max-width:180px;display:block;margin-bottom:6px;">'.format(
            company_doc.company_logo)
        if company_doc.get("company_logo") else ""
    )

    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #222; padding: 0; }}
  .page {{ padding: 18px 22px; }}
  .hdr td {{ vertical-align: top; padding-bottom: 4px; }}
  .co-name {{ font-size: 13px; font-weight: bold; }}
  .co-meta {{ font-size: 10px; color: #444; line-height: 1.6; margin-top: 3px; }}
  .stmt-title {{ font-size: 15px; font-weight: bold; text-align: right; }}
  .stmt-period {{ font-size: 10px; color: #555; text-align: right; margin-top: 3px; }}
  .to-label {{ font-size: 10px; font-weight: bold; color: #888;
               text-transform: uppercase; letter-spacing: 0.6px; }}
  .cust-name {{ font-size: 12px; font-weight: bold; margin-top: 2px; }}
  .cust-meta {{ font-size: 10px; color: #444; line-height: 1.6; margin-top: 2px; }}
  .divider {{ border-top: 2px solid #2c3e50; margin: 10px 0; }}
  .summary {{ display: inline-block; border: 1px solid #ccc;
              background: #f7f8f9; padding: 8px 14px;
              border-radius: 4px; margin-bottom: 12px; }}
  .summary table {{ border-collapse: collapse; font-size: 11px; }}
  .summary td {{ padding: 2px 10px 2px 0; }}
  .summary td:last-child {{ text-align: right; min-width: 90px; }}
  .summary .total-row td {{ border-top: 1px solid #aaa; font-weight: bold;
                             padding-top: 4px; margin-top: 2px; }}
  table.ledger {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  table.ledger thead tr {{ background: #2c3e50; color: #fff; }}
  table.ledger thead th {{ padding: 6px 8px; text-align: left; font-weight: 600; }}
  table.ledger thead th.r {{ text-align: right; }}
  table.ledger tbody tr:nth-child(even) {{ background: #f9f9f9; }}
  table.ledger tbody td {{ padding: 5px 8px; border-bottom: 1px solid #eee;
                           vertical-align: top; }}
  table.ledger tbody td.r {{ text-align: right; white-space: nowrap; }}
  .bold-row td {{ font-weight: bold; background: #eef0f2 !important; }}
  .footer-bal {{ text-align: right; margin-top: 12px; font-size: 12px; font-weight: bold;
                 color: {bal_color}; }}
</style>
</head>
<body>
<div class="page">

  <!-- ── Header ─────────────────────────────────────────────────── -->
  <table class="hdr" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td width="50%">
        {logo}
        <div class="co-name">{company_name}</div>
        <div class="co-meta">
          {company_addr_html}
          {gstin_html}
          {phone_html}
          {email_html}
        </div>
      </td>
      <td width="50%" style="text-align:right; vertical-align:top;">
        <div class="stmt-title">Statement of Accounts</div>
        <div class="stmt-period">{from_date} To {to_date}</div>
        <div style="margin-top:12px;">
          <div class="to-label">To</div>
          <div class="cust-name">{cust_name}</div>
          <div class="cust-meta">
            {cust_addr_html}
            {cust_gstin_html}
          </div>
        </div>
      </td>
    </tr>
  </table>

  <div class="divider"></div>

  <!-- ── Account Summary ────────────────────────────────────────── -->
  <div class="summary">
    <table>
      <tr><td>Opening Balance</td>
          <td>{open_bal}</td></tr>
      <tr><td>Invoiced Amount</td>
          <td>{inv_amt}</td></tr>
      <tr><td>Amount Received</td>
          <td>{rec_amt}</td></tr>
      <tr class="total-row">
          <td>{bal_label}</td>
          <td style="color:{bal_color}">{bal_amt}</td></tr>
    </table>
  </div>

  <!-- ── Transaction Table ──────────────────────────────────────── -->
  <table class="ledger">
    <thead>
      <tr>
        <th style="width:70px;">Date</th>
        <th style="width:110px;">Transactions</th>
        <th>Details</th>
        <th class="r" style="width:90px;">Amount</th>
        <th class="r" style="width:90px;">Payments</th>
        <th class="r" style="width:90px;">Balance</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <!-- ── Balance Due footer ─────────────────────────────────────── -->
  <div class="footer-bal">{bal_label}: {bal_amt}</div>

</div>
</body>
</html>""".format(
        bal_color=bal_color,
        logo=logo_html,
        company_name=company_doc.company_name,
        company_addr_html=company_addr or "",
        gstin_html="GSTIN: {}".format(company_doc.get("tax_id")) if company_doc.get("tax_id") else "",
        phone_html=company_doc.get("phone_no", ""),
        email_html=company_doc.get("email", ""),
        from_date=formatdate(filters.from_date),
        to_date=formatdate(filters.to_date),
        cust_name=customer_doc.customer_name,
        cust_addr_html=customer_addr or "",
        cust_gstin_html="GSTIN: {}".format(customer_doc.get("tax_id")) if customer_doc.get("tax_id") else "",
        open_bal=_fmt(opening_balance, currency),
        inv_amt=_fmt(total_inv, currency),
        rec_amt=_fmt(total_rec, currency),
        bal_label=bal_label,
        bal_amt=_fmt(abs(closing), currency),
        rows=rows_html,
    )

    pdf = get_pdf(html, {"page-size": "A4", "orientation": "Portrait",
                         "margin-top": "10mm", "margin-bottom": "10mm",
                         "margin-left": "12mm", "margin-right": "12mm"})

    fname = "Ledger_{}_{}_to_{}.pdf".format(
        customer_doc.customer_name.replace(" ", "_"),
        filters.from_date, filters.to_date,
    )
    frappe.local.response.filename    = fname
    frappe.local.response.filecontent = pdf
    frappe.local.response.type        = "pdf"


# ---------------------------------------------------------------------------
# HTML helpers for PDF rows
# ---------------------------------------------------------------------------

def _pdf_row(date, txn_type, details, amount, payments, balance, bold=False):
    cls = ' class="bold-row"' if bold else ""
    return (
        "<tr{cls}>"
        "<td>{date}</td>"
        "<td>{txn}</td>"
        "<td>{det}</td>"
        "<td class='r'>{amt}</td>"
        "<td class='r'>{pay}</td>"
        "<td class='r'>{bal}</td>"
        "</tr>"
    ).format(cls=cls, date=date, txn=txn_type, det=details,
             amt=amount, pay=payments, bal=balance)


def _fmt(amount, currency):
    return fmt_money(flt(amount), currency=currency)


# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------

def _get_company_address(company):
    row = frappe.db.sql(
        """
        SELECT CONCAT_WS(', ',
            NULLIF(a.address_line1,''), NULLIF(a.address_line2,''),
            NULLIF(a.city,''), NULLIF(a.state,''),
            NULLIF(a.pincode,''), NULLIF(a.country,'')) AS addr
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent=a.name
          AND dl.link_doctype='Company' AND dl.link_name=%(co)s
        WHERE a.is_primary_address=1 LIMIT 1
        """,
        {"co": company}, as_dict=True,
    )
    return row[0].addr if row else ""


def _get_customer_address(customer):
    row = frappe.db.sql(
        """
        SELECT CONCAT_WS(', ',
            NULLIF(a.address_line1,''), NULLIF(a.address_line2,''),
            NULLIF(a.city,''), NULLIF(a.state,''),
            NULLIF(a.pincode,''), NULLIF(a.country,'')) AS addr
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent=a.name
          AND dl.link_doctype='Customer' AND dl.link_name=%(c)s
        WHERE a.is_primary_address=1 LIMIT 1
        """,
        {"c": customer}, as_dict=True,
    )
    return row[0].addr if row else ""


def _get_currency(filters):
    if filters.get("currency"):
        return filters.currency
    return frappe.db.get_value("Company", filters.get("company"), "default_currency") or "INR"
