import calendar

import frappe
from frappe.utils import flt


def get_columns():
    cur = {"fieldtype": "Currency", "options": "currency", "width": 130}
    return [
        {"label": "Month",              "fieldname": "month",                 "fieldtype": "Data",         "width": 90},
        {"label": "Date",               "fieldname": "posting_date",          "fieldtype": "Date",         "width": 95},
        {"label": "Payment Entry",      "fieldname": "name",                  "fieldtype": "Dynamic Link",
         "options": "doctype_field",                                                                        "width": 180},
        {"label": "Customer Code",      "fieldname": "party",                 "fieldtype": "Link",
         "options": "Customer",                                                                             "width": 140},
        {"label": "Customer Name",      "fieldname": "customer_name",         "fieldtype": "Data",         "width": 170},
        {"label": "Territory",          "fieldname": "territory",             "fieldtype": "Data",         "width": 110},
        {"label": "Customer Group",     "fieldname": "customer_group",        "fieldtype": "Data",         "width": 130},
        {"label": "Parent Group",       "fieldname": "parent_customer_group", "fieldtype": "Data",         "width": 130},
        {"label": "Mode of Payment",    "fieldname": "mode_of_payment",       "fieldtype": "Data",         "width": 130},
        {"label": "Payment Type",       "fieldname": "payment_type",          "fieldtype": "Data",         "width": 110},
        dict(label="Paid Amount",       fieldname="paid_amount",              **cur),
        dict(label="Allocated",         fieldname="allocated_amount",         **cur),
        dict(label="Unallocated",       fieldname="unallocated_amount",       **cur),
        {"label": "Reference No",       "fieldname": "reference_no",          "fieldtype": "Data",         "width": 140},
        {"label": "Reference Date",     "fieldname": "reference_date",        "fieldtype": "Date",         "width": 105},
        {"label": "Currency",           "fieldname": "currency",              "fieldtype": "Link",
         "options": "Currency",                                                                             "width": 80, "hidden": 1},
        {"label": "",                   "fieldname": "doctype_field",         "fieldtype": "Data",         "width": 1, "hidden": 1},
    ]


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("company"):
        filters.company = frappe.defaults.get_user_default("company")

    # Month/Year shortcut overrides From/To Date
    if filters.get("month"):
        month_num = list(calendar.month_name).index(filters["month"])
        year = int(filters.get("year") or frappe.utils.getdate().year)
        last_day = calendar.monthrange(year, month_num)[1]
        filters["from_date"] = "{}-{:02d}-01".format(year, month_num)
        filters["to_date"]   = "{}-{:02d}-{:02d}".format(year, month_num, last_day)

    if not filters.get("from_date"):
        filters.from_date = "2025-04-01"
    if not filters.get("to_date"):
        filters.to_date = frappe.utils.today()

    # Build optional filter fragments
    date_filter         = "AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s"
    customer_filter     = "AND pe.party = %(customer)s"              if filters.get("customer")        else ""
    territory_filter    = "AND c.territory = %(territory)s"          if filters.get("territory")       else ""
    mop_filter          = "AND pe.mode_of_payment = %(mode_of_payment)s" if filters.get("mode_of_payment") else ""
    payment_type_filter = "AND pe.payment_type = %(payment_type)s"   if filters.get("payment_type")    else ""

    if filters.get("customer_group"):
        customer_group_filter = (
            "AND (c.customer_group = %(customer_group)s "
            "OR cg.parent_customer_group = %(customer_group)s)"
        )
    else:
        customer_group_filter = ""

    sql = """
        SELECT
            DATE_FORMAT(pe.posting_date, '%%b-%%Y')       AS month,
            pe.posting_date,
            pe.name,
            'Payment Entry'                                AS doctype_field,
            pe.party,
            IFNULL(c.customer_name, pe.party)             AS customer_name,
            IFNULL(c.territory, '')                       AS territory,
            IFNULL(c.customer_group, '')                  AS customer_group,
            IFNULL(cg.parent_customer_group, '')          AS parent_customer_group,
            pe.mode_of_payment,
            pe.payment_type,
            pe.paid_amount,
            (pe.paid_amount - pe.unallocated_amount)      AS allocated_amount,
            pe.unallocated_amount,
            pe.reference_no,
            pe.reference_date,
            IFNULL(pe.paid_to_account_currency,
                   pe.paid_from_account_currency)         AS currency
        FROM `tabPayment Entry` pe
        LEFT JOIN `tabCustomer`       c  ON pe.party = c.name
        LEFT JOIN `tabCustomer Group` cg ON c.customer_group = cg.name
        WHERE
            pe.docstatus = 1
            AND pe.company = %(company)s
            AND pe.party_type = 'Customer'
            {date_filter}
            {customer_filter}
            {territory_filter}
            {customer_group_filter}
            {mop_filter}
            {payment_type_filter}
        ORDER BY pe.posting_date DESC, pe.name
    """.format(
        date_filter=date_filter,
        customer_filter=customer_filter,
        territory_filter=territory_filter,
        customer_group_filter=customer_group_filter,
        mop_filter=mop_filter,
        payment_type_filter=payment_type_filter,
    )

    rows = frappe.db.sql(sql, filters, as_dict=True)

    data = []
    total_paid        = 0.0
    total_allocated   = 0.0
    total_unallocated = 0.0
    currency          = None

    for r in rows:
        paid        = flt(r.paid_amount)
        allocated   = flt(r.allocated_amount)
        unallocated = flt(r.unallocated_amount)

        total_paid        += paid
        total_allocated   += allocated
        total_unallocated += unallocated

        if not currency:
            currency = r.currency

        data.append(frappe._dict(
            month                 = r.month,
            posting_date          = r.posting_date,
            name                  = r.name,
            doctype_field         = "Payment Entry",
            party                 = r.party,
            customer_name         = r.customer_name,
            territory             = r.territory,
            customer_group        = r.customer_group,
            parent_customer_group = r.parent_customer_group,
            mode_of_payment       = r.mode_of_payment,
            payment_type          = r.payment_type,
            paid_amount           = paid,
            allocated_amount      = allocated,
            unallocated_amount    = unallocated,
            reference_no          = r.reference_no or "",
            reference_date        = r.reference_date,
            currency              = r.currency or "",
        ))

    if data:
        data.append(frappe._dict(
            month                 = "",
            posting_date          = None,
            name                  = "",
            doctype_field         = "",
            party                 = "",
            customer_name         = "Total",
            territory             = "",
            customer_group        = "",
            parent_customer_group = "",
            mode_of_payment       = "",
            payment_type          = "",
            paid_amount           = total_paid,
            allocated_amount      = total_allocated,
            unallocated_amount    = total_unallocated,
            reference_no          = "",
            reference_date        = None,
            currency              = currency or "",
            is_total              = 1,
        ))

    return get_columns(), data
