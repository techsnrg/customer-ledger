import frappe


def after_install():
    _ensure_module()
    _ensure_report()
    _ensure_ar_report()
    _ensure_supplier_ledger_report()
    _ensure_supplier_ap_report()
    _ensure_payment_entry_report()


def after_migrate():
    _ensure_module()
    _ensure_report()
    _ensure_ar_report()
    _ensure_supplier_ledger_report()
    _ensure_supplier_ap_report()
    _ensure_payment_entry_report()


def _ensure_module():
    """Create the Module Def so Frappe maps 'Customer Ledger' → this app."""
    if frappe.db.exists("Module Def", "Customer Ledger"):
        return
    frappe.get_doc(
        {
            "doctype": "Module Def",
            "module_name": "Customer Ledger",
            "app_name": "customer_ledger",
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_report():
    """
    Create or repair the Customer Ledger Report document.

    With module='Customer Ledger' and is_standard='Yes', Frappe will load
    the Python script from:
        apps/customer_ledger/customer_ledger/report/customer_ledger_report/
    which is exactly where our .py and .js files live.
    """
    exists = frappe.db.exists("Report", "Customer Ledger Report")

    if exists:
        # Repair in case a previous deploy stored the wrong module
        frappe.db.set_value(
            "Report", "Customer Ledger Report", "module", "Customer Ledger"
        )
        frappe.db.set_value(
            "Report", "Customer Ledger Report", "disabled", 0
        )
        frappe.db.commit()
        return

    report = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": "Customer Ledger Report",
            "report_type": "Script Report",
            "ref_doctype": "GL Entry",
            "module": "Customer Ledger",
            "is_standard": "Yes",
            "disabled": 0,
            "roles": [
                {"role": "Accounts User"},
                {"role": "Accounts Manager"},
                {"role": "System Manager"},
            ],
        }
    )
    report.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_ar_report():
    """Create or repair the Customer AR Report document."""
    exists = frappe.db.exists("Report", "Customer AR Report")

    if exists:
        frappe.db.set_value("Report", "Customer AR Report", "module", "Customer Ledger")
        frappe.db.set_value("Report", "Customer AR Report", "disabled", 0)
        frappe.db.commit()
        return

    report = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": "Customer AR Report",
            "report_type": "Script Report",
            "ref_doctype": "Sales Invoice",
            "module": "Customer Ledger",
            "is_standard": "Yes",
            "disabled": 0,
            "roles": [
                {"role": "Accounts User"},
                {"role": "Accounts Manager"},
                {"role": "System Manager"},
            ],
        }
    )
    report.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_supplier_ledger_report():
    """Create or repair the Supplier Ledger Report document."""
    exists = frappe.db.exists("Report", "Supplier Ledger Report")

    if exists:
        frappe.db.set_value("Report", "Supplier Ledger Report", "module", "Customer Ledger")
        frappe.db.set_value("Report", "Supplier Ledger Report", "disabled", 0)
        frappe.db.commit()
        return

    report = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": "Supplier Ledger Report",
            "report_type": "Script Report",
            "ref_doctype": "GL Entry",
            "module": "Customer Ledger",
            "is_standard": "Yes",
            "disabled": 0,
            "roles": [
                {"role": "Accounts User"},
                {"role": "Accounts Manager"},
                {"role": "System Manager"},
            ],
        }
    )
    report.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_supplier_ap_report():
    """Create or repair the Supplier AP Report document."""
    exists = frappe.db.exists("Report", "Supplier AP Report")

    if exists:
        frappe.db.set_value("Report", "Supplier AP Report", "module", "Customer Ledger")
        frappe.db.set_value("Report", "Supplier AP Report", "disabled", 0)
        frappe.db.commit()
        return

    report = frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": "Supplier AP Report",
            "report_type": "Script Report",
            "ref_doctype": "Purchase Invoice",
            "module": "Customer Ledger",
            "is_standard": "Yes",
            "disabled": 0,
            "roles": [
                {"role": "Accounts User"},
                {"role": "Accounts Manager"},
                {"role": "System Manager"},
            ],
        }
    )
    report.insert(ignore_permissions=True)
    frappe.db.commit()


def _ensure_payment_entry_report():
    """Create or repair the Payment Entry Report document."""
    exists = frappe.db.exists("Report", "Payment Entry Report")

    if exists:
        frappe.db.set_value("Report", "Payment Entry Report", "module", "Customer Ledger")
        frappe.db.set_value("Report", "Payment Entry Report", "disabled", 0)
        frappe.db.commit()
        return

    frappe.get_doc(
        {
            "doctype": "Report",
            "report_name": "Payment Entry Report",
            "report_type": "Script Report",
            "ref_doctype": "Payment Entry",
            "module": "Customer Ledger",
            "is_standard": "Yes",
            "disabled": 0,
            "roles": [
                {"role": "Accounts User"},
                {"role": "Accounts Manager"},
                {"role": "System Manager"},
            ],
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()
