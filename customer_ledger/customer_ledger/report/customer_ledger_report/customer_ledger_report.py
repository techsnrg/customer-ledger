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
            "remarks":         "" if (entry.remarks or "").strip().lower() in ("no remarks", "") else entry.remarks,
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
def download_customer_ledger_pdf(filters, include_ar=0, include_ledger=1):
    from frappe.utils.pdf import get_pdf

    if isinstance(filters, str):
        filters = frappe._dict(json.loads(filters))
    else:
        filters = frappe._dict(filters or {})
    include_ar      = cint(include_ar)
    include_ledger  = cint(include_ledger)

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

    def _fdate(d):
        """Format date as '04 Sep 2025' — never wraps in the narrow Date column."""
        return formatdate(d, "dd MMM yyyy") if d else ""

    rows_html += _pdf_row(
        _fdate(filters.from_date), "Opening Balance", "",
        _fmt(opening_balance, currency) if opening_balance > 0 else "",
        _fmt(abs(opening_balance), currency) if opening_balance < 0 else "",
        _fmt(opening_balance, currency), bold=True,
    )

    for e in gl_entries:
        debit  = flt(e.debit)
        credit = flt(e.credit)
        running   += debit - credit
        total_inv += debit
        total_rec += credit
        rows_html += _pdf_row(
            _fdate(e.posting_date),
            e.voucher_type,
            "{}{}<br><small style='color:#666'>{}</small>".format(
                e.voucher_no,
                " <em>({})</em>".format(e.voucher_subtype) if e.voucher_subtype else "",
                "" if (e.remarks or "").strip().lower() in ("no remarks", "") else (e.remarks or ""),
            ),
            _fmt(debit,  currency) if debit  else "",
            _fmt(credit, currency) if credit else "",
            _fmt(running, currency),
        )

    rows_html += _pdf_row("", "<strong>Closing Balance</strong>", "",
                          _fmt(total_inv, currency) if total_inv else "",
                          _fmt(total_rec, currency) if total_rec else "",
                          _fmt(running, currency), bold=True)

    closing     = running
    bal_label   = _("Balance Due") if closing >= 0 else _("Credit Balance")
    bal_color   = "#c0392b" if closing >= 0 else "#27ae60"

    # ── Logo (embedded as base64 so wkhtmltopdf / weasyprint can render it)
    logo_src = _get_logo_base64(
        company_doc.get("company_logo") or "/files/WhatsApp Image 2025-11-27 at 16.04.30.jpeg"
    )
    logo_html = (
        '<img src="{src}" style="max-height:72px;max-width:220px;'
        'display:block;margin-bottom:8px;">'.format(src=logo_src)
        if logo_src else ""
    )

    def _meta_line(val):
        """Return a <div> line or empty string."""
        return "<div>{}</div>".format(val) if val else ""

    # ── Customer GSTIN (tax_id first; then India Compliance GSTIN doctype)
    cust_gstin = customer_doc.get("tax_id") or ""
    if not cust_gstin:
        try:
            cust_gstin = frappe.db.get_value(
                "GSTIN",
                {"linked_to": "Customer", "linked_name": filters.customer},
                "name",
            ) or ""
        except Exception:
            cust_gstin = ""

    # ── Company GSTIN
    co_gstin = company_doc.get("tax_id") or ""

    # ── Build ledger page (page 1) — skip when AR-only export ──────────
    html = "" if not include_ledger else """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #222; }}
  .page {{ padding: 14px 18px; }}
  /* ── Accent bar ── */
  .accent-bar {{ height: 5px; background: #1d3969; margin: -14px -18px 0; }}
  /* ── Header area ── */
  .hdr-area {{ background: #eef1f8; margin: 0 -18px; padding: 11px 18px 10px; }}
  .co-name {{ font-size: 14px; font-weight: bold; color: #1d3969; margin-bottom: 3px; }}
  .co-meta {{ font-size: 10px; color: #555; line-height: 1.7; }}
  .stmt-title {{ font-size: 17px; font-weight: bold; text-align: right; color: #1d3969; }}
  .stmt-period {{ font-size: 10px; color: #666; text-align: right; margin-top: 3px; }}
  /* ── Divider ── */
  .divider {{ border-top: 2px solid #1d3969; margin: 10px 0; }}
  /* ── Summary cards ── */
  .cards-tbl {{ width: 100%; border-collapse: separate; border-spacing: 5px 0; }}
  .card {{ padding: 7px 8px; border: 1px solid #dde3ee; border-radius: 3px;
           text-align: center; vertical-align: top; white-space: nowrap; }}
  .card-lbl {{ font-size: 8.5px; color: #777; text-transform: uppercase;
               letter-spacing: 0.4px; display: block; margin-bottom: 4px; }}
  .card-val {{ font-size: 12px; font-weight: bold; display: block; }}
  /* ── Customer block ── */
  .to-block {{ border-left: 3px solid #1d3969; padding-left: 10px; }}
  .to-label {{ font-size: 8.5px; font-weight: bold; color: #1d3969;
               text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 3px; }}
  .party-name {{ font-size: 16px; line-height: 1.15; font-weight: 700;
                 color: #22384f; margin-bottom: 4px; }}
  .cust-meta {{ font-size: 10px; color: #555; line-height: 1.7; margin-top: 2px; }}
  /* ── Balance banner ── */
  .bal-banner {{ background: #f8f9fc; border-left: 4px solid {bal_color};
                 padding: 7px 14px; margin: 10px 0; }}
  .bal-banner td {{ vertical-align: middle; }}
  .bal-banner .bb-lbl {{ font-size: 11px; color: #555; }}
  .bal-banner .bb-amt {{ font-size: 15px; font-weight: bold;
                         text-align: right; color: {bal_color}; }}
  /* ── Ledger table ── */
  table.ledger {{ width: 100%; border-collapse: collapse; font-size: 10.5px; table-layout: fixed; }}
  table.ledger thead tr {{ background: #1d3969; color: #fff; }}
  table.ledger thead th {{ padding: 6px 7px; text-align: left; font-weight: 600; overflow: hidden; }}
  table.ledger thead th.r {{ text-align: right; }}
  table.ledger tbody tr:nth-child(even) {{ background: #f4f6fb; }}
  table.ledger tbody td {{ padding: 5px 7px; border-bottom: 1px solid #e5eaf3;
                           vertical-align: top; overflow: hidden; word-wrap: break-word; }}
  table.ledger tbody td.r {{ text-align: right; white-space: nowrap; }}
  .bold-row td {{ font-weight: bold; background: #e3e8f3 !important;
                  border-top: 1px solid #b8c4dc; }}
</style>
</head>
<body>
<div class="page">

  <!-- ① Accent stripe -->
  <div class="accent-bar"></div>

  <!-- ② Header area with tinted background -->
  <div class="hdr-area">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="55%" style="vertical-align:top;">
          {logo}
          <div class="co-name">{company_name}</div>
          <div class="co-meta">
            {co_addr}{co_phone}{co_email}
          </div>
        </td>
        <td width="45%" style="vertical-align:top;">
          <div class="stmt-title">Statement of Accounts</div>
          <div class="stmt-period">{from_date} To {to_date}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="divider"></div>

  <!-- ③ Summary cards (left) + ⑤ Customer left-border block (right) -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:10px;">
    <tr>
      <td width="58%" style="vertical-align:top; padding-right:14px;">
        <table class="cards-tbl" cellpadding="0" cellspacing="0">
          <tr>
            <td class="card" style="border-top:3px solid #607d8b;">
              <span class="card-lbl">Opening Balance</span>
              <span class="card-val" style="color:#455a64;">{open_bal}</span>
            </td>
            <td class="card" style="border-top:3px solid #1a56db;">
              <span class="card-lbl">Invoiced Amount</span>
              <span class="card-val" style="color:#1a56db;">{inv_amt}</span>
            </td>
            <td class="card" style="border-top:3px solid #27ae60;">
              <span class="card-lbl">Amount Received</span>
              <span class="card-val" style="color:#27ae60;">{rec_amt}</span>
            </td>
            <td class="card" style="border-top:3px solid {bal_color};">
              <span class="card-lbl">{bal_label}</span>
              <span class="card-val" style="color:{bal_color};">{bal_amt}</span>
            </td>
          </tr>
        </table>
      </td>
      <td width="42%" style="vertical-align:top;">
        <div class="to-block">
          <div class="to-label">To</div>
          <div class="party-name">{cust_code_head}</div>
          <div class="party-name">{cust_name}</div>
          <div class="cust-meta">{cust_mobile}{cust_addr}{cust_gstin_line}</div>
        </div>
      </td>
    </tr>
  </table>

  <!-- Transaction Table -->
  <table class="ledger">
    <colgroup>
      <col style="width:78px;">
      <col style="width:108px;">
      <col>
      <col style="width:88px;">
      <col style="width:88px;">
      <col style="width:88px;">
    </colgroup>
    <thead>
      <tr>
        <th>Date</th>
        <th>Transactions</th>
        <th>Details</th>
        <th class="r">Amount</th>
        <th class="r">Payments</th>
        <th class="r">Balance</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <!-- Balance Due summary banner (bottom) -->
  <table class="bal-banner" width="100%" cellpadding="0" cellspacing="0"
         style="margin-top:14px;">
    <tr>
      <td class="bb-lbl">{bal_label}</td>
      <td class="bb-amt">{bal_amt}</td>
    </tr>
  </table>

  {tnc}

</div>
</body>
</html>""".format(
        bal_color=bal_color,
        logo=logo_html,
        company_name=company_doc.company_name,
        co_addr=_meta_line(company_addr),
        co_phone=_meta_line(company_doc.get("phone_no", "")),
        co_email=_meta_line(company_doc.get("email", "")),
        from_date=formatdate(filters.from_date),
        to_date=formatdate(filters.to_date),
        cust_name=customer_doc.customer_name,
        cust_code_head=(customer_doc.name
                        if customer_doc.name != customer_doc.customer_name
                        else customer_doc.customer_name),
        cust_mobile=_meta_line(customer_doc.get("custom_mobile_number") or ""),
        cust_addr=_meta_line(customer_addr),
        cust_gstin_line=_meta_line("GSTIN: {}".format(cust_gstin) if cust_gstin else ""),
        open_bal=_fmt(opening_balance, currency),
        inv_amt=_fmt(total_inv, currency),
        rec_amt=_fmt(total_rec, currency),
        bal_label=bal_label,
        bal_amt=_fmt(abs(closing), currency),
        rows=rows_html,
        tnc=_build_tnc_html(),
    )

    # ── Page 2: Accounts Receivable (only when requested) ──────────
    if include_ar:
        ar_entries = _get_ar_entries(filters)
        aging      = _build_ar_aging(ar_entries)
        ar_page    = _build_ar_page(
            ar_entries, aging, filters, currency,
            logo_html, company_doc, customer_doc,
            company_addr, customer_addr,
            _meta_line,
        )
        if include_ledger:
            html = html.replace("</div>\n</body>", "</div>\n" + ar_page + "\n</body>")
        else:
            html = ar_page

    import datetime
    generated_on = datetime.datetime.now().strftime("%-d %b %Y, %-I:%M %p")
    pdf = get_pdf(html, {
        "page-size": "A4",
        "orientation": "Portrait",
        "margin-top": "8mm",
        "margin-bottom": "14mm",
        "margin-left": "8mm",
        "margin-right": "8mm",
        "footer-left": "Generated on {}".format(generated_on),
        "footer-right": "Page [page] of [topage]",
        "footer-font-size": "8",
        "footer-font-name": "Arial",
        "footer-spacing": "3",
    })

    prefix = "Statement" if (include_ar and include_ledger) else ("AR" if include_ar else "Ledger")
    fname = "{}_{}_{}_to_{}.pdf".format(
        prefix,
        customer_doc.customer_name.replace(" ", "_"),
        filters.from_date, filters.to_date,
    )
    frappe.local.response.filename    = fname
    frappe.local.response.filecontent = pdf
    frappe.local.response.type        = "pdf"


# ---------------------------------------------------------------------------
# Email statement  (called from "Email to Customer" button)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def email_customer_ledger(filters, include_ar=0, include_ledger=1):
    """Build the same PDF as download_customer_ledger_pdf and send it to the
    customer's primary email address."""
    from frappe.utils.pdf import get_pdf

    if isinstance(filters, str):
        import json
        filters = frappe._dict(json.loads(filters))
    else:
        filters = frappe._dict(filters)

    include_ar     = int(include_ar)
    include_ledger = int(include_ledger)

    # Resolve customer email
    customer_doc = frappe.get_doc("Customer", filters.customer)
    to_email = (
        customer_doc.get("email_id")
        or frappe.db.get_value(
            "Contact Email",
            {
                "parent": frappe.db.get_value(
                    "Dynamic Link",
                    {"link_doctype": "Customer", "link_name": filters.customer,
                     "parenttype": "Contact"},
                    "parent",
                )
            },
            "email_id",
        )
    )

    if not to_email:
        frappe.throw(
            "No email address found for customer <b>{}</b>. "
            "Please add an email on the Customer or linked Contact.".format(filters.customer)
        )

    # Re-use the same HTML/PDF logic by calling the internal builder
    # (we duplicate the minimal wiring rather than calling the download endpoint)
    # Easiest: call download_customer_ledger_pdf with side-effect suppressed,
    # then grab the pdf bytes before the response is set.
    from frappe.utils.pdf import get_pdf as _get_pdf

    # Build pdf via shared helper — invoke same logic but capture bytes
    # We piggy-back on frappe.local.response being set then read it back.
    download_customer_ledger_pdf(filters, include_ar=include_ar, include_ledger=include_ledger)
    pdf_bytes = frappe.local.response.filecontent
    fname     = frappe.local.response.filename

    # Reset response type so the browser doesn't receive a PDF download
    frappe.local.response.type        = "json"
    frappe.local.response.filecontent = None
    frappe.local.response.filename    = None

    company_name = frappe.db.get_value("Company", filters.company, "company_name") or filters.company
    subject = "{} — Account Statement ({} to {})".format(
        company_name, filters.from_date, filters.to_date
    )
    body = (
        "Dear {},<br><br>"
        "Please find attached your account statement for the period "
        "<b>{}</b> to <b>{}</b>.<br><br>"
        "For any discrepancies, please inform us within 7 days of receiving this mail.<br><br>"
        "Regards,<br>{}"
    ).format(
        customer_doc.customer_name,
        filters.from_date, filters.to_date,
        company_name,
    )

    frappe.sendmail(
        recipients=[to_email],
        subject=subject,
        message=body,
        attachments=[{"fname": fname, "fcontent": pdf_bytes}],
        now=True,
    )

    return {"message": "Statement emailed to {}".format(to_email)}


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


# ---------------------------------------------------------------------------
# Shared T&C block
# ---------------------------------------------------------------------------

def _build_tnc_html():
    """Return the Terms & Conditions HTML block — used on both PDF pages."""
    return """
    <div style="margin-top:24px;border-top:1px solid #ccc;padding-top:12px;">
      <div style="font-size:11px;font-weight:bold;text-transform:uppercase;
                  letter-spacing:.6px;margin-bottom:8px;color:#1a1a1a;">Terms &amp; Conditions</div>
      <ol style="font-size:9.5px;color:#333;line-height:1.8;padding-left:18px;margin:0 0 10px;">
        <li>All payments shall be cleared within <strong>60 days</strong> of invoicing
            (70 days in case of IGST billing).</li>
        <li>Accounts overdue above <strong>75 days</strong> shall be frozen for billing
            without prior written approval.</li>
        <li>Interest <strong>@18% p.a.</strong> shall be charged on amounts overdue beyond
            <strong>75 days</strong>.</li>
        <li>Any discrepancies must be notified in <strong>writing within 7 days</strong>
            of receipt; failing which, the statement shall be deemed accepted.</li>
        <li>Payments by A/c payee Cheque / DD / NEFT / RTGS only. All payments to be made
            in <strong>"SNRG Electricals India Pvt Ltd"</strong> bank accounts only.</li>
        <li>All disputes subject to <strong>Delhi</strong> jurisdiction.</li>
      </ol>
      <div style="background:#fff3cd;border:1px solid #ffc107;border-left:4px solid #e67e22;
                  border-radius:3px;padding:8px 12px;font-size:9.5px;color:#7d4e00;line-height:1.6;">
        <strong>&#9888;&nbsp;IMPORTANT:</strong>&nbsp;Do <strong>NOT</strong> hand over cash
        to anyone, including but not limited to employees of SNRG Group of Companies.
        <strong>No cash receipts are valid under any circumstance.</strong>
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Accounts Receivable helpers
# ---------------------------------------------------------------------------

def _get_ar_entries(filters):
    """Return outstanding Sales Invoices & Credit Notes for this customer."""
    return frappe.db.sql(
        """
        SELECT
            si.posting_date,
            si.name                                                      AS voucher_no,
            'Sales Invoice'                                              AS voucher_type,
            CASE WHEN si.is_return = 1 THEN 'Credit Note' ELSE '' END   AS voucher_subtype,
            si.outstanding_amount,
            DATEDIFF(%(to_date)s, si.posting_date)                       AS ageing_days
        FROM `tabSales Invoice` si
        WHERE si.company   = %(company)s
          AND si.customer  = %(customer)s
          AND si.docstatus = 1
          AND si.outstanding_amount != 0
          AND si.posting_date <= %(to_date)s
        ORDER BY si.posting_date ASC, si.name ASC
        """,
        {"company": filters.company, "customer": filters.customer, "to_date": filters.to_date},
        as_dict=True,
    )


def _build_ar_aging(ar_entries):
    """Bucket outstanding amounts into 0-30 / 31-60 / 61-75 / 76-90 / 90+ days."""
    buckets = {"b0": 0.0, "b31": 0.0, "b61": 0.0, "b76": 0.0, "b90": 0.0}
    for e in ar_entries:
        amt  = flt(e.outstanding_amount)
        days = int(e.ageing_days or 0)
        if days <= 30:
            buckets["b0"]  += amt
        elif days <= 60:
            buckets["b31"] += amt
        elif days <= 75:
            buckets["b61"] += amt
        elif days <= 90:
            buckets["b76"] += amt
        else:
            buckets["b90"] += amt
    return buckets


def _build_ar_page(ar_entries, aging, filters, currency,
                   logo_html, company_doc, customer_doc,
                   company_addr, customer_addr,
                   meta_line_fn):
    """Return the full HTML string for the AR page (page 2 of the PDF)."""

    # ── AR table rows ──────────────────────────────────────────────────────
    ar_rows_html = ""
    total_outstanding = 0.0

    if ar_entries:
        for e in ar_entries:
            amt  = flt(e.outstanding_amount)
            days = int(e.ageing_days or 0)
            total_outstanding += amt

            subtype_str = e.voucher_subtype or ""
            if days <= 0:
                days_label = "<span style='color:#27ae60;'>Not due</span>"
            elif days <= 30:
                days_label = "<span style='color:#27ae60;font-weight:600;'>{} days</span>".format(days)
            elif days <= 60:
                days_label = "<span style='color:#f39c12;font-weight:600;'>{} days</span>".format(days)
            elif days <= 75:
                days_label = "<span style='color:#e67e22;font-weight:600;'>{} days</span>".format(days)
            elif days <= 90:
                days_label = "<span style='color:#e74c3c;font-weight:600;'>{} days</span>".format(days)
            else:
                days_label = "<span style='color:#8e1a1a;font-weight:600;'>{} days</span>".format(days)

            ar_rows_html += (
                "<tr>"
                "<td>{date}</td>"
                "<td>{vtype}</td>"
                "<td>{sub}</td>"
                "<td>{vno}</td>"
                "<td class='r'>{amt}</td>"
                "<td class='r'>{days}</td>"
                "</tr>"
            ).format(
                date=formatdate(e.posting_date, "dd MMM yyyy"),
                vtype=e.voucher_type,
                sub=subtype_str,
                vno=e.voucher_no,
                amt=_fmt(amt, currency),
                days=days_label,
            )

        # Totals row
        ar_rows_html += (
            "<tr class='bold-row'>"
            "<td colspan='4'><strong>Total Outstanding</strong></td>"
            "<td class='r'><strong>{}</strong></td>"
            "<td></td>"
            "</tr>"
        ).format(_fmt(total_outstanding, currency))
    else:
        ar_rows_html = (
            "<tr><td colspan='6' style='text-align:center;color:#888;"
            "padding:16px;'>No outstanding transactions</td></tr>"
        )

    # ── Aging summary ──────────────────────────────────────────────────────
    aging_html = """
    <div style="margin-top:20px;">
      <div style="font-size:12px;font-weight:bold;text-transform:uppercase;
                  letter-spacing:.6px;margin-bottom:6px;color:#1d3969;">Ageing Summary</div>
      <div style="border-top:2px solid #1d3969;margin-bottom:8px;"></div>
      <table class="ledger" style="font-size:10.5px;">
        <colgroup>
          <col style="width:28%;">
          <col style="width:14.4%;">
          <col style="width:14.4%;">
          <col style="width:14.4%;">
          <col style="width:14.4%;">
          <col style="width:14.4%;">
        </colgroup>
        <thead>
          <tr>
            <th style="background:#1d3969;">AGEING</th>
            <th class="r" style="background:#27ae60;">0 - 30</th>
            <th class="r" style="background:#f39c12;">31 - 60</th>
            <th class="r" style="background:#e67e22;">61 - 75</th>
            <th class="r" style="background:#e74c3c;">76 - 90</th>
            <th class="r" style="background:#8e1a1a;">90+</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Based on Posting Date<br>up to {as_of}</td>
            <td class="r">{b0}</td>
            <td class="r">{b31}</td>
            <td class="r">{b61}</td>
            <td class="r">{b76}</td>
            <td class="r">{b90}</td>
          </tr>
        </tbody>
      </table>
    </div>""".format(
        as_of=formatdate(filters.to_date),
        b0=_fmt(aging["b0"],  currency),
        b31=_fmt(aging["b31"], currency),
        b61=_fmt(aging["b61"], currency),
        b76=_fmt(aging["b76"], currency),
        b90=_fmt(aging["b90"], currency),
    )

    # ── Terms & Conditions ─────────────────────────────────────────────────
    tnc_html = _build_tnc_html()

    # ── Assemble the full AR page ──────────────────────────────────────────
    return """
<div class="page" style="page-break-before:always;">

  <!-- ① Accent stripe -->
  <div class="accent-bar"></div>

  <!-- ② Header area with tinted background -->
  <div class="hdr-area">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="55%" style="vertical-align:top;">
          {logo}
          <div class="co-name">{company_name}</div>
          <div class="co-meta">
            {co_addr}{co_phone}{co_email}
          </div>
        </td>
        <td width="45%" style="vertical-align:top;">
          <div class="stmt-title">Accounts Receivable</div>
          <div class="stmt-period">As of {to_date}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="divider"></div>

  <!-- ⑤ Customer left-border block -->
  <div style="margin-bottom:12px;">
    <div class="to-block">
      <div class="to-label">To</div>
      <div class="party-name">{cust_code_head}</div>
      <div class="party-name">{cust_name}</div>
      <div class="cust-meta">{cust_mobile}{cust_addr}{cust_gstin_line}</div>
    </div>
  </div>

  <!-- AR Transactions Table -->
  <table class="ledger">
    <colgroup>
      <col style="width:72px;">
      <col style="width:110px;">
      <col style="width:80px;">
      <col style="width:130px;">
      <col style="width:90px;">
      <col style="width:72px;">
    </colgroup>
    <thead>
      <tr>
        <th>Date</th>
        <th>Voucher Type</th>
        <th>Subtype</th>
        <th>Voucher No</th>
        <th class="r">Outstanding</th>
        <th class="r">Ageing Days</th>
      </tr>
    </thead>
    <tbody>{ar_rows}</tbody>
  </table>

  {aging_section}
  {tnc_section}

</div>""".format(
        logo=logo_html,
        company_name=company_doc.company_name,
        co_addr=meta_line_fn(company_addr),
        co_phone=meta_line_fn(company_doc.get("phone_no", "")),
        co_email=meta_line_fn(company_doc.get("email", "")),
        to_date=formatdate(filters.to_date),
        cust_name=customer_doc.customer_name,
        cust_code_head=(customer_doc.name
                        if customer_doc.name != customer_doc.customer_name
                        else customer_doc.customer_name),
        cust_mobile=meta_line_fn(customer_doc.get("custom_mobile_number") or ""),
        cust_addr=meta_line_fn(customer_addr),
        cust_gstin_line=meta_line_fn("GSTIN: {}".format(customer_doc.get("tax_id")) if customer_doc.get("tax_id") else ""),
        ar_rows=ar_rows_html,
        aging_section=aging_html,
        tnc_section=tnc_html,
    )


# ---------------------------------------------------------------------------
# Logo helper — resolves /files/... → filesystem path → base64 data URI
# ---------------------------------------------------------------------------

def _get_logo_base64(logo_url):
    """
    Given a Frappe file URL like '/files/logo.png', resolve it to the
    site's filesystem path, read the bytes and return a data-URI string
    suitable for embedding in HTML (so wkhtmltopdf/weasyprint can render it
    without needing HTTP access).

    Returns an empty string if the file cannot be found or read.
    """
    import base64
    import mimetypes
    import os

    if not logo_url:
        return ""

    # Strip query-string / fragment if any
    clean_url = logo_url.split("?")[0].split("#")[0]

    # Build absolute filesystem path inside the Frappe site
    site_path = frappe.get_site_path()
    # Frappe stores /files/... under <site>/public/files/
    if clean_url.startswith("/files/"):
        file_path = os.path.join(site_path, "public", clean_url.lstrip("/"))
    elif clean_url.startswith("/private/files/"):
        file_path = os.path.join(site_path, clean_url.lstrip("/"))
    else:
        return ""

    if not os.path.isfile(file_path):
        return ""

    try:
        with open(file_path, "rb") as fh:
            raw = fh.read()
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "image/jpeg"
        b64 = base64.b64encode(raw).decode("ascii")
        return "data:{};base64,{}".format(mime, b64)
    except Exception:
        return ""
