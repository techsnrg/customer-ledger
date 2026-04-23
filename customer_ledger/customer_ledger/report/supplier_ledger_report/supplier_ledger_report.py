"""
Supplier Ledger Report
Script Report for ERPNext — shows a formatted ledger for one supplier
between two dates with opening balance, transactions and closing balance.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, nowdate

DEFAULT_LEDGER_FROM_DATE = "2025-04-01"


# ---------------------------------------------------------------------------
# Column definitions  (filters are defined in supplier_ledger_report.js)
# ---------------------------------------------------------------------------

def get_columns(filters):
    currency = _get_currency(filters)
    return [
        {"fieldname": "posting_date",    "label": _("Date"),           "fieldtype": "Date",         "width": 100},
        {"fieldname": "voucher_type",    "label": _("Type"),           "fieldtype": "Data",         "width": 130},
        {"fieldname": "voucher_subtype", "label": _("Subtype"),        "fieldtype": "Data",         "width": 110},
        {"fieldname": "voucher_no",      "label": _("Voucher No"),     "fieldtype": "Dynamic Link",
         "options": "voucher_type",                                                                  "width": 160},
        {"fieldname": "remarks",         "label": _("Remarks"),        "fieldtype": "Data",         "width": 220},
        {"fieldname": "debit",           "label": _("Payments ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                             "width": 130},
        {"fieldname": "credit",          "label": _("Bills ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                             "width": 130},
        {"fieldname": "balance",         "label": _("Balance ({0})".format(currency)),
         "fieldtype": "Currency", "options": "currency",                                             "width": 140},
        {"fieldname": "currency",        "label": _("Currency"),       "fieldtype": "Currency",     "hidden": 1},
    ]


# ---------------------------------------------------------------------------
# Main execute — called by the Frappe report engine
# ---------------------------------------------------------------------------

def execute(filters=None):
    filters = frappe._dict(filters or {})
    _apply_default_filters(filters)
    _validate_filters(filters)

    columns     = get_columns(filters)
    data        = _get_data(filters)
    html_header = _build_screen_header(filters, data)
    summary     = _build_summary_cards(filters, data)

    return columns, data, html_header, None, summary


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _apply_default_filters(filters, include_ledger=1):
    if not filters.get("company"):
        filters.company = frappe.defaults.get_user_default("company")
    if not filters.get("to_date"):
        filters.to_date = nowdate()
    if cint(include_ledger) and not filters.get("from_date"):
        filters.from_date = DEFAULT_LEDGER_FROM_DATE


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

    data            = [_make_opening_row(opening_balance, currency, filters.from_date)]
    running_balance = opening_balance
    current_account = None

    for entry in gl_entries:
        if group_by_account and entry.account != current_account:
            current_account = entry.account
            data.append({
                "posting_date": None, "voucher_type": "", "voucher_no": "",
                "remarks": current_account, "debit": None, "credit": None,
                "balance": None, "currency": currency, "bold": 1, "is_group": 1,
            })

        # For supplier: credit = bills received (increases balance), debit = payments made (decreases)
        running_balance += flt(entry.credit) - flt(entry.debit)
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
        "debit":   total_debit, "credit": total_credit,
        "balance": running_balance, "currency": currency, "bold": 1,
    })
    return data


def _get_opening_balance(filters):
    result = frappe.db.sql(
        """
        SELECT SUM(credit_in_account_currency) - SUM(debit_in_account_currency) AS balance
        FROM `tabGL Entry`
        WHERE company    = %(company)s
          AND party_type = 'Supplier'
          AND party      = %(supplier)s
          AND posting_date < %(from_date)s
          AND is_cancelled = 0
        """,
        {"company": filters.company, "supplier": filters.supplier, "from_date": filters.from_date},
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
            CASE
                WHEN gle.voucher_type = 'Purchase Invoice' AND MAX(pi.is_return) = 1
                THEN CONCAT('Debit Note', {pi_reason_gl})
                ELSE MAX(gle.voucher_subtype)
            END                                AS voucher_subtype,
            gle.voucher_no,
            MAX(gle.remarks)                   AS remarks,
            SUM(gle.debit_in_account_currency) AS debit,
            SUM(gle.credit_in_account_currency)AS credit
        FROM `tabGL Entry` gle
        LEFT JOIN `tabPurchase Invoice` pi
            ON pi.name = gle.voucher_no AND gle.voucher_type = 'Purchase Invoice'
        WHERE gle.company    = %(company)s
          AND gle.party_type = 'Supplier'
          AND gle.party      = %(supplier)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          {cancelled_cond}
          {je_cond}
        GROUP BY gle.posting_date, gle.account, gle.voucher_type, gle.voucher_no
        ORDER BY {order_by}
        """.format(
            cancelled_cond=cancelled_cond, je_cond=je_cond, order_by=order_by,
            pi_reason_gl=(
                "IF(MAX(IFNULL(pi.custom_reason,'')) != '', CONCAT(' (', MAX(IFNULL(pi.custom_reason,'')), ')'), '')"
                if frappe.db.has_column("Purchase Invoice", "custom_reason") else "''"
            ),
        ),
        {"company": filters.company, "supplier": filters.supplier,
         "from_date": filters.from_date, "to_date": filters.to_date},
        as_dict=True,
    )


def _make_opening_row(opening_balance, currency, from_date):
    return {
        "posting_date": from_date,
        "voucher_type": "", "voucher_no": "",
        "remarks": _("Opening Balance"),
        "debit":   abs(opening_balance) if opening_balance < 0 else 0.0,
        "credit":  opening_balance if opening_balance > 0 else 0.0,
        "balance": opening_balance,
        "currency": currency, "bold": 1,
    }


# ---------------------------------------------------------------------------
# Screen header (3rd execute() return — rendered as HTML above the table)
# ---------------------------------------------------------------------------

def _build_screen_header(filters, data):
    company_doc      = frappe.get_doc("Company", filters.company)
    supplier_doc     = frappe.get_doc("Supplier", filters.supplier)
    supplier_address = _get_supplier_address(filters.supplier)
    closing_balance  = flt(data[-1].get("balance", 0)) if data else 0.0
    currency         = _get_currency(filters)

    logo_html = (
        '<img src="{}" style="max-height:70px;max-width:200px;" alt="logo">'.format(company_doc.company_logo)
        if company_doc.get("company_logo") else ""
    )
    balance_label = _("Amount Payable") if closing_balance >= 0 else _("Advance Balance")
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
                      letter-spacing:.8px;margin-bottom:6px;">{bill_from}</div>
          <div style="font-size:14px;font-weight:700;color:#2c3e50;margin-bottom:3px;">
            {supp_name}</div>
          <div style="font-size:11px;color:#666;margin-bottom:3px;">
            <span style="color:#888;">{code_lbl}:</span> {supp_code}</div>
          <div style="font-size:11px;color:#555;line-height:1.5;">{supp_addr}</div>
          {supp_tax}
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
        title=_("Supplier Ledger Statement"),
        period_lbl=_("Period"),
        from_d=formatdate(filters.from_date),
        to_d=formatdate(filters.to_date),
        bal_color=balance_color,
        bal_label=balance_label,
        currency=currency,
        bal_amt=fmt_money(abs(closing_balance), currency=currency),
        bill_from=_("Supplier"),
        supp_name=supplier_doc.supplier_name,
        code_lbl=_("Supplier Code"),
        supp_code=supplier_doc.name,
        supp_addr=supplier_address or "&mdash;",
        supp_tax=_row(_("Tax ID"), supplier_doc.get("tax_id")),
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
        {"value": total_credit, "label": _("Total Bills"),   "datatype": "Currency", "currency": currency},
        {"value": total_debit,  "label": _("Total Paid"),    "datatype": "Currency", "currency": currency},
        {
            "value": abs(closing),
            "label": _("Amount Payable") if closing >= 0 else _("Advance Balance"),
            "datatype": "Currency", "currency": currency,
            "indicator": "Red" if closing > 0 else "Green",
        },
    ]


# ---------------------------------------------------------------------------
# Shared PDF helpers
# ---------------------------------------------------------------------------

def _get_pdf_css(bal_color):
    return """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #222; }
  .page { padding: 14px 18px; }
  .accent-bar { height: 5px; background: #1d3969; margin: -14px -18px 0; }
  .hdr-area { background: #eef1f8; margin: 0 -18px; padding: 11px 18px 10px; }
  .co-name { font-size: 14px; font-weight: bold; color: #1d3969; margin-bottom: 3px; }
  .co-meta { font-size: 10px; color: #555; line-height: 1.7; }
  .stmt-title { font-size: 17px; font-weight: bold; text-align: right; color: #1d3969; }
  .stmt-period { font-size: 10px; color: #666; text-align: right; margin-top: 3px; }
  .divider { border-top: 2px solid #1d3969; margin: 10px 0; }
  .cards-tbl { width: 100%; border-collapse: separate; border-spacing: 5px 0; }
  .card { padding: 7px 8px; border: 1px solid #dde3ee; border-radius: 3px;
          text-align: center; vertical-align: top; white-space: nowrap; }
  .card-lbl { font-size: 8.5px; color: #777; text-transform: uppercase;
              letter-spacing: 0.4px; display: block; margin-bottom: 4px; }
  .card-val { font-size: 12px; font-weight: bold; display: block; }
  .to-block { border-left: 3px solid #1d3969; padding-left: 10px; }
  .to-label { font-size: 8.5px; font-weight: bold; color: #1d3969;
              text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 3px; }
  .party-name { font-size: 16px; line-height: 1.15; font-weight: 700;
                color: #22384f; margin-bottom: 4px; }
  .cust-meta { font-size: 10px; color: #555; line-height: 1.7; margin-top: 2px; }
  .bal-banner { background: #f8f9fc; border-left: 4px solid __BAL__;
                padding: 7px 14px; margin: 10px 0; }
  .bal-banner td { vertical-align: middle; }
  .bal-banner .bb-lbl { font-size: 11px; color: #555; }
  .bal-banner .bb-amt { font-size: 15px; font-weight: bold;
                        text-align: right; color: __BAL__; }
  table.ledger { width: 100%; border-collapse: collapse; font-size: 10.5px; table-layout: fixed; }
  table.ledger thead tr { background: #1d3969; color: #fff; }
  table.ledger thead th { padding: 6px 7px; text-align: left; font-weight: 600; overflow: hidden; }
  table.ledger thead th.r { text-align: right; }
  table.ledger tbody tr:nth-child(even) { background: #f4f6fb; }
  table.ledger tbody td { padding: 5px 7px; border-bottom: 1px solid #e5eaf3;
                          vertical-align: top; overflow: hidden; word-wrap: break-word; }
  table.ledger tbody td.r { text-align: right; white-space: nowrap; }
  .bold-row td { font-weight: bold; background: #e3e8f3 !important;
                 border-top: 1px solid #b8c4dc; }
""".replace("__BAL__", bal_color)


def _make_html_doc(css, page_divs):
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n<style>'
        + css
        + "</style>\n</head>\n<body>\n"
        + "\n".join(page_divs)
        + "\n</body>\n</html>"
    )


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


def _get_supplier_address(supplier):
    row = frappe.db.sql(
        """
        SELECT CONCAT_WS(', ',
            NULLIF(a.address_line1,''), NULLIF(a.address_line2,''),
            NULLIF(a.city,''), NULLIF(a.state,''),
            NULLIF(a.pincode,''), NULLIF(a.country,'')) AS addr
        FROM `tabAddress` a
        JOIN `tabDynamic Link` dl ON dl.parent=a.name
          AND dl.link_doctype='Supplier' AND dl.link_name=%(s)s
        WHERE a.is_primary_address=1 LIMIT 1
        """,
        {"s": supplier}, as_dict=True,
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
    return """
    <div style="margin-top:24px;border-top:1px solid #ccc;padding-top:12px;">
      <div style="font-size:11px;font-weight:bold;text-transform:uppercase;
                  letter-spacing:.6px;margin-bottom:8px;color:#1a1a1a;">Terms &amp; Conditions</div>
      <ol style="font-size:9.5px;color:#333;line-height:1.8;padding-left:18px;margin:0 0 10px;">
        <li>Any discrepancies must be notified in <strong>writing within 7 days</strong>
            of receipt; failing which, the statement shall be deemed accepted.</li>
        <li>All disputes subject to <strong>Delhi</strong> jurisdiction.</li>
      </ol>
    </div>"""


# ---------------------------------------------------------------------------
# Accounts Payable helpers
# ---------------------------------------------------------------------------

def _get_ap_entries(filters):
    """Return outstanding Purchase Invoices & Debit Notes for this supplier."""
    return frappe.db.sql(
        """
        SELECT
            pi.posting_date,
            pi.name                                                      AS voucher_no,
            'Purchase Invoice'                                           AS voucher_type,
            CASE WHEN pi.is_return = 1
                 THEN CONCAT('Debit Note', {pi_reason})
                 ELSE 'Invoice'
            END AS voucher_subtype,
            pi.grand_total                                               AS invoiced_amount,
            pi.outstanding_amount,
            DATEDIFF(%(to_date)s, pi.posting_date)                       AS ageing_days
        FROM `tabPurchase Invoice` pi
        WHERE pi.company   = %(company)s
          AND pi.supplier  = %(supplier)s
          AND pi.docstatus = 1
          AND pi.outstanding_amount != 0
          AND pi.posting_date <= %(to_date)s
        ORDER BY pi.posting_date ASC, pi.name ASC
        """.format(
            pi_reason=(
                "IF(IFNULL(pi.custom_reason,'') != '', CONCAT(' (', pi.custom_reason, ')'), '')"
                if frappe.db.has_column("Purchase Invoice", "custom_reason") else "''"
            ),
        ),
        {"company": filters.company, "supplier": filters.supplier, "to_date": filters.to_date},
        as_dict=True,
    )


def _build_ap_aging(ap_entries):
    """Bucket outstanding amounts into 0-30 / 31-60 / 61-75 / 76-90 / 90+ days."""
    buckets = {"b0": 0.0, "b31": 0.0, "b61": 0.0, "b76": 0.0, "b90": 0.0}
    for e in ap_entries:
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


def _build_ap_page(ap_entries, aging, filters, currency,
                   logo_html, company_doc, supplier_doc,
                   company_addr, supplier_addr,
                   meta_line_fn, page_break=False):
    """Return the AP <div class='page'> fragment."""

    # ── AP table rows ──────────────────────────────────────────────────────
    ap_rows_html = ""
    total_outstanding = 0.0

    if ap_entries:
        for e in ap_entries:
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

            ap_rows_html += (
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

        ap_rows_html += (
            "<tr class='bold-row'>"
            "<td colspan='4'><strong>Total Outstanding</strong></td>"
            "<td class='r'><strong>{}</strong></td>"
            "<td></td>"
            "</tr>"
        ).format(_fmt(total_outstanding, currency))
    else:
        ap_rows_html = (
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

    tnc_html  = _build_tnc_html()
    pb_style  = "page-break-before:always;" if page_break else ""
    supp_code = supplier_doc.name
    supp_name = supplier_doc.supplier_name
    supp_code_line = (
        '<div class="party-name">{}</div>'.format(supp_code)
        if supp_code != supp_name else ""
    )

    return """
<div class="page" style="{pb_style}">

  <!-- ① Accent stripe -->
  <div class="accent-bar"></div>

  <!-- ② Header -->
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
          <div class="stmt-title">Accounts Payable</div>
          <div class="stmt-period">As of {to_date}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="divider"></div>

  <!-- Supplier block -->
  <div style="margin-bottom:12px;">
    <div class="to-block">
      <div class="to-label">Supplier</div>
      {supp_code_line}
      <div class="party-name">{supp_name}</div>
      <div class="cust-meta">{supp_addr}{supp_gstin_line}</div>
    </div>
  </div>

  <!-- AP Transactions Table -->
  <table class="ledger">
    <colgroup>
      <col style="width:72px;">
      <col style="width:120px;">
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
    <tbody>{ap_rows}</tbody>
  </table>

  {aging_section}
  {tnc_section}

</div>""".format(
        pb_style=pb_style,
        logo=logo_html,
        company_name=company_doc.company_name,
        co_addr=meta_line_fn(company_addr),
        co_phone=meta_line_fn(company_doc.get("phone_no", "")),
        co_email=meta_line_fn(company_doc.get("email", "")),
        to_date=formatdate(filters.to_date),
        supp_code_line=supp_code_line,
        supp_name=supp_name,
        supp_addr=meta_line_fn(supplier_addr),
        supp_gstin_line=meta_line_fn("GSTIN: {}".format(supplier_doc.get("tax_id")) if supplier_doc.get("tax_id") else ""),
        ap_rows=ap_rows_html,
        aging_section=aging_html,
        tnc_section=tnc_html,
    )


def _build_ledger_page_div(
    logo_html, company_doc, company_addr, supplier_doc, supplier_addr,
    filters, currency, rows_html,
    opening_balance, total_payments, total_bills, closing,
    bal_color, bal_label, meta_line_fn,
):
    """Return the ledger <div class='page'> fragment."""
    supp_code = supplier_doc.name
    supp_name = supplier_doc.supplier_name
    supp_code_head = supp_code if supp_code != supp_name else ""

    return """
<div class="page">

  <!-- ① Accent stripe -->
  <div class="accent-bar"></div>

  <!-- ② Header -->
  <div class="hdr-area">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="55%" style="vertical-align:top;">
          {logo}
          <div class="co-name">{company_name}</div>
          <div class="co-meta">{co_addr}{co_phone}{co_email}</div>
        </td>
        <td width="45%" style="vertical-align:top;">
          <div class="stmt-title">Statement of Accounts</div>
          <div class="stmt-period">{from_date} To {to_date}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="divider"></div>

  <!-- ③ Summary cards + Supplier block -->
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
              <span class="card-lbl">Bill Amount</span>
              <span class="card-val" style="color:#1a56db;">{bill_amt}</span>
            </td>
            <td class="card" style="border-top:3px solid #27ae60;">
              <span class="card-lbl">Amount Paid</span>
              <span class="card-val" style="color:#27ae60;">{paid_amt}</span>
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
          <div class="to-label">Supplier</div>
          {supp_code_line}
          <div class="party-name">{supp_name}</div>
          <div class="cust-meta">{supp_addr}</div>
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
        <th>Date</th><th>Transactions</th><th>Details</th>
        <th class="r">Payments</th><th class="r">Bills</th><th class="r">Balance</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <!-- Balance Due banner -->
  <table class="bal-banner" width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">
    <tr>
      <td class="bb-lbl">{bal_label}</td>
      <td class="bb-amt">{bal_amt}</td>
    </tr>
  </table>

  {tnc}

</div>""".format(
        logo=logo_html,
        company_name=company_doc.company_name,
        co_addr=meta_line_fn(company_addr),
        co_phone=meta_line_fn(company_doc.get("phone_no", "")),
        co_email=meta_line_fn(company_doc.get("email", "")),
        from_date=formatdate(filters.from_date),
        to_date=formatdate(filters.to_date),
        supp_code_line=(
            '<div class="party-name">{}</div>'.format(supp_code_head)
            if supp_code_head else ""
        ),
        supp_name=supp_name,
        supp_addr=meta_line_fn(supplier_addr),
        open_bal=_fmt(opening_balance, currency),
        bill_amt=_fmt(total_bills, currency),
        paid_amt=_fmt(total_payments, currency),
        bal_label=bal_label,
        bal_amt=_fmt(abs(closing), currency),
        bal_color=bal_color,
        rows=rows_html,
        tnc=_build_tnc_html(),
    )


# ---------------------------------------------------------------------------
# Logo helper
# ---------------------------------------------------------------------------

def _get_logo_base64(logo_url):
    import base64
    import mimetypes
    import os

    if not logo_url:
        return ""

    clean_url = logo_url.split("?")[0].split("#")[0]
    site_path = frappe.get_site_path()
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


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_supplier_ledger_pdf(filters, include_ap=0, include_ledger=1):
    from frappe.utils.pdf import get_pdf

    if isinstance(filters, str):
        filters = frappe._dict(json.loads(filters))
    else:
        filters = frappe._dict(filters or {})
    include_ap     = cint(include_ap)
    include_ledger = cint(include_ledger)

    _apply_default_filters(filters, include_ledger=include_ledger)
    _validate_filters(filters)

    currency      = _get_currency(filters)
    company_doc   = frappe.get_doc("Company", filters.company)
    supplier_doc  = frappe.get_doc("Supplier", filters.supplier)
    company_addr  = _get_company_address(filters.company)
    supplier_addr = _get_supplier_address(filters.supplier)
    opening_balance = _get_opening_balance(filters)
    gl_entries      = _get_gl_entries(filters)

    running        = opening_balance
    total_payments = 0.0
    total_bills    = 0.0
    rows_html      = ""

    def _fdate(d):
        return formatdate(d, "dd MMM yyyy") if d else ""

    rows_html += _pdf_row(
        _fdate(filters.from_date), "Opening Balance", "",
        _fmt(abs(opening_balance), currency) if opening_balance < 0 else "",
        _fmt(opening_balance, currency) if opening_balance > 0 else "",
        _fmt(opening_balance, currency), bold=True,
    )

    for e in gl_entries:
        debit   = flt(e.debit)
        credit  = flt(e.credit)
        running        += credit - debit
        total_payments += debit
        total_bills    += credit
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
                          _fmt(total_payments, currency) if total_payments else "",
                          _fmt(total_bills, currency) if total_bills else "",
                          _fmt(running, currency), bold=True)

    closing   = running
    bal_label = _("Amount Payable") if closing >= 0 else _("Advance Balance")
    bal_color = "#c0392b" if closing >= 0 else "#27ae60"

    logo_src  = _get_logo_base64(
        company_doc.get("company_logo") or "/files/WhatsApp Image 2025-11-27 at 16.04.30.jpeg"
    )
    logo_html = (
        '<img src="{src}" style="max-height:72px;max-width:220px;'
        'display:block;margin-bottom:8px;">'.format(src=logo_src)
        if logo_src else ""
    )

    def _meta_line(val):
        return "<div>{}</div>".format(val) if val else ""

    css       = _get_pdf_css(bal_color)
    page_divs = []

    if include_ledger:
        page_divs.append(
            _build_ledger_page_div(
                logo_html, company_doc, company_addr, supplier_doc, supplier_addr,
                filters, currency, rows_html,
                opening_balance, total_payments, total_bills, closing,
                bal_color, bal_label, _meta_line,
            )
        )

    if include_ap:
        ap_entries = _get_ap_entries(filters)
        aging      = _build_ap_aging(ap_entries)
        ap_div     = _build_ap_page(
            ap_entries, aging, filters, currency,
            logo_html, company_doc, supplier_doc,
            company_addr, supplier_addr,
            _meta_line,
            page_break=(include_ledger == 1),
        )
        page_divs.append(ap_div)

    html = _make_html_doc(css, page_divs)

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

    prefix = "Statement" if (include_ap and include_ledger) else ("AP" if include_ap else "Ledger")
    fname = "{}_{}_{}_to_{}.pdf".format(
        prefix,
        supplier_doc.supplier_name.replace(" ", "_"),
        filters.from_date, filters.to_date,
    )
    frappe.local.response.filename    = fname
    frappe.local.response.filecontent = pdf
    frappe.local.response.type        = "pdf"


# ---------------------------------------------------------------------------
# Email statement
# ---------------------------------------------------------------------------

@frappe.whitelist()
def email_supplier_ledger(filters, include_ap=0, include_ledger=1):
    if isinstance(filters, str):
        filters = frappe._dict(json.loads(filters))
    else:
        filters = frappe._dict(filters)

    include_ap     = int(include_ap)
    include_ledger = int(include_ledger)
    _apply_default_filters(filters, include_ledger=include_ledger)

    supplier_doc = frappe.get_doc("Supplier", filters.supplier)
    to_email = (
        supplier_doc.get("email_id")
        or frappe.db.get_value(
            "Contact Email",
            {
                "parent": frappe.db.get_value(
                    "Dynamic Link",
                    {"link_doctype": "Supplier", "link_name": filters.supplier,
                     "parenttype": "Contact"},
                    "parent",
                )
            },
            "email_id",
        )
    )

    if not to_email:
        frappe.throw(
            "No email address found for supplier <b>{}</b>. "
            "Please add an email on the Supplier or linked Contact.".format(filters.supplier)
        )

    download_supplier_ledger_pdf(filters, include_ap=include_ap, include_ledger=include_ledger)
    pdf_bytes = frappe.local.response.filecontent
    fname     = frappe.local.response.filename

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
        supplier_doc.supplier_name,
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
