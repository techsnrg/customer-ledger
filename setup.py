from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="customer_ledger",
    version="0.0.1",
    description="Custom Customer Ledger Report for ERPNext",
    author="Your Company",
    author_email="info@yourcompany.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
