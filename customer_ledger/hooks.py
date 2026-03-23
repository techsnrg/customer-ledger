app_name = "customer_ledger"
app_title = "Customer Ledger"
app_publisher = "Your Company"
app_description = "Custom Customer Ledger Report for ERPNext"
app_email = "info@yourcompany.com"
app_license = "MIT"

# Apps to be loaded before this app
# required_apps = ["erpnext"]

fixtures = [
    {
        "doctype": "Report",
        "filters": [["name", "in", ["Customer Ledger Report"]]],
    }
]
