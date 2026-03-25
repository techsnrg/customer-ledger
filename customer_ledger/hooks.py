app_name = "customer_ledger"
app_title = "Customer Ledger"
app_publisher = "Your Company"
app_description = "Custom Customer Ledger Report for ERPNext"
app_email = "info@yourcompany.com"
app_license = "MIT"

after_install = "customer_ledger.setup.after_install"
after_migrate = "customer_ledger.setup.after_migrate"

doctype_js = {
    "Customer": "public/js/customer_ledger_button.js"
}
