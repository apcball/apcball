# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

# Core models first
from . import res_company
from . import res_config_settings
from . import res_partner

# Product models
from . import product
# from . import product_wht  # Temporarily disabled - field dependency issues

# Account base models
from . import account
from . import account_tax
from . import account_move_tax_invoice

# Withholding tax models - must be loaded before extending models
from . import account_withholding_tax
from . import withholding_tax_code_income
from . import withholding_tax_cert
from . import personal_income_tax

# Account move and payment models (extends withholding models)
from . import account_move
from . import account_move_odoo17
from . import account_partial_reconcile
from . import account_payment
# from . import account_payment_wht  # Merged into account_payment.py
from . import account_withholding_move

# HR extension
from . import hr_expense
