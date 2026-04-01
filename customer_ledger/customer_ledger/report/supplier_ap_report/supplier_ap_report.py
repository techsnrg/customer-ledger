import frappe
from frappe.utils import flt

from customer_ledger.customer_ledger.report.supplier_ledger_report.supplier_ledger_report import (
    _get_ap_entries,
    _build_ap_aging,
    _fmt,
    _get_currency,
)


def get_columns():
    cur = {"fieldtype": "Currency", "options": "currency", "width": 130}
    return [
        {"label": "Date",               "fieldname": "posting_date",       "fieldtype": "Date",         "width": 100},
        {"label": "Voucher Type",        "fieldname": "voucher_type",       "fieldtype": "Data",         "width": 120},
        {"label": "Subtype",             "fieldname": "voucher_subtype",    "fieldtype": "Data",         "width": 110},
        {"label": "Voucher No",          "fieldname": "voucher_no",         "fieldtype": "Dynamic Link",
         "options": "voucher_type",                                                                      "width": 190},
        dict(label="Bill Amount",        fieldname="invoiced_amount",       **cur),
        dict(label="Outstanding Amount", fieldname="outstanding_amount",    **cur),
        {"label": "Ageing Days",         "fieldname": "ageing_days",        "fieldtype": "Int",          "width": 100},
        dict(label="0 - 30",  fieldname="b0",  **cur),
        dict(label="31 - 60", fieldname="b31", **cur),
        dict(label="61 - 75", fieldname="b61", **cur),
        dict(label="76 - 90", fieldname="b76", **cur),
        dict(label="90+",     fieldname="b90", **cur),
        {"label": "Currency", "fieldname": "currency", "fieldtype": "Link",
         "options": "Currency", "width": 80, "hidden": 1},
    ]


def _bucket_key(days):
    if days <= 30:
        return "b0"
    elif days <= 60:
        return "b31"
    elif days <= 75:
        return "b61"
    elif days <= 90:
        return "b76"
    else:
        return "b90"


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("company"):
        filters.company = frappe.defaults.get_user_default("company")
    if not filters.get("to_date"):
        filters.to_date = frappe.utils.today()

    currency   = _get_currency(filters)
    ap_entries = _get_ap_entries(filters) if filters.get("supplier") else []

    data = []
    total_invoiced    = 0.0
    total_outstanding = 0.0
    bucket_totals     = {"b0": 0.0, "b31": 0.0, "b61": 0.0, "b76": 0.0, "b90": 0.0}

    for e in ap_entries:
        inv_amt = flt(e.invoiced_amount)
        out_amt = flt(e.outstanding_amount)
        days    = int(e.ageing_days or 0)
        bkey    = _bucket_key(days)

        total_invoiced    += inv_amt
        total_outstanding += out_amt
        bucket_totals[bkey] += out_amt

        row = frappe._dict(
            posting_date       = e.posting_date,
            voucher_type       = e.voucher_type,
            voucher_subtype    = e.voucher_subtype or "",
            voucher_no         = e.voucher_no,
            invoiced_amount    = inv_amt,
            outstanding_amount = out_amt,
            ageing_days        = days,
            b0  = out_amt if bkey == "b0"  else 0.0,
            b31 = out_amt if bkey == "b31" else 0.0,
            b61 = out_amt if bkey == "b61" else 0.0,
            b76 = out_amt if bkey == "b76" else 0.0,
            b90 = out_amt if bkey == "b90" else 0.0,
            currency           = currency,
        )
        data.append(row)

    if data:
        data.append(
            frappe._dict(
                posting_date       = None,
                voucher_type       = "",
                voucher_subtype    = "",
                voucher_no         = "Total Outstanding",
                invoiced_amount    = total_invoiced,
                outstanding_amount = total_outstanding,
                ageing_days        = None,
                b0  = bucket_totals["b0"],
                b31 = bucket_totals["b31"],
                b61 = bucket_totals["b61"],
                b76 = bucket_totals["b76"],
                b90 = bucket_totals["b90"],
                currency           = currency,
                is_total           = 1,
            )
        )

    columns = get_columns()
    return columns, data
