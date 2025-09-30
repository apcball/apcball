# Qwen Development Context

**Project:** buz_payment_receipt (Odoo 17 Custom Addon)

**Date:** วันจันทร์ที่ 29 กันยายน 2568

**Operating System:** Linux

**Project Directory:** /opt/instance1/odoo17/custom-addons/buz_payment_receipt

## Project Structure
```
/opt/instance1/odoo17/custom-addons/buz_payment_receipt/
├───__init__.py
├───__manifest__.py
├───models/
│   ├───account_payment.py
│   └───__init__.py
├───__pycache__/
│   └───__manifest__.cpython-312.pyc
├───reports/
│   ├───payment_receipt_report.xml
│   ├───payment_receipt_template.xml
│   └───payment_voucher_report.xml
├───security/
│   └───ir.model.access.csv
├───static/
│   ├───description/
│   │   └───icon.png
│   ├───fonts/
│   └───src/
└───views/
    └───payment_receipt_views.xml
```

## Project Description
This is an Odoo 17 custom addon for handling payment receipts. It includes models, reports, and views for managing payment receipts in the system.

## Key Components
- **Models**: Payment-related data models (account_payment.py)
- **Reports**: Payment receipt and voucher report templates
- **Views**: UI components for payment receipts
- **Security**: Access control configuration