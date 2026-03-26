import frappe
from frappe.utils import flt, formatdate

from customer_ledger.customer_ledger.report.customer_ledger_report.customer_ledger_report import (
    _get_ar_entries,
    _build_ar_aging,
    _fmt,
    _get_currency,
)


def get_columns():
    return [
        {
            "label": "Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": "Voucher Type",
            "fieldname": "voucher_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": "Subtype",
            "fieldname": "voucher_subtype",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": "Voucher No",
            "fieldname": "voucher_no",
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 200,
        },
        {
            "label": "Outstanding Amount",
            "fieldname": "outstanding_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 140,
        },
        {
            "label": "Ageing Days",
            "fieldname": "ageing_days",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": "Currency",
            "fieldname": "currency",
            "fieldtype": "Link",
            "options": "Currency",
            "width": 80,
            "hidden": 1,
        },
    ]


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("company"):
        filters.company = frappe.defaults.get_user_default("company")
    if not filters.get("to_date"):
        filters.to_date = frappe.utils.today()

    currency = _get_currency(filters)

    ar_entries = _get_ar_entries(filters) if filters.get("customer") else []

    data = []
    total_outstanding = 0.0

    for e in ar_entries:
        amt = flt(e.outstanding_amount)
        total_outstanding += amt
        data.append(
            frappe._dict(
                posting_date=e.posting_date,
                voucher_type=e.voucher_type,
                voucher_subtype=e.voucher_subtype or "",
                voucher_no=e.voucher_no,
                outstanding_amount=amt,
                ageing_days=int(e.ageing_days or 0),
                currency=currency,
            )
        )

    # ── Totals row ──────────────────────────────────────────────────────────
    if data:
        data.append(
            frappe._dict(
                posting_date=None,
                voucher_type="",
                voucher_subtype="",
                voucher_no="Total Outstanding",
                outstanding_amount=total_outstanding,
                ageing_days=None,
                currency=currency,
                is_total=1,
            )
        )

    # ── Ageing summary rows ─────────────────────────────────────────────────
    if ar_entries:
        aging = _build_ar_aging(ar_entries)
        data.append(frappe._dict(voucher_no="", is_section_break=1))
        data.append(frappe._dict(voucher_no="── AGEING SUMMARY ──", is_section_break=1))

        bucket_labels = [
            ("b0",  "0 - 30 days"),
            ("b31", "31 - 60 days"),
            ("b61", "61 - 75 days"),
            ("b76", "76 - 90 days"),
            ("b90", "90+ days"),
        ]
        for key, label in bucket_labels:
            data.append(
                frappe._dict(
                    posting_date=None,
                    voucher_type="",
                    voucher_subtype="",
                    voucher_no=label,
                    outstanding_amount=aging[key],
                    ageing_days=None,
                    currency=currency,
                    is_aging_row=1,
                )
            )

    columns = get_columns()
    return columns, data
