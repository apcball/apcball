# -*- coding: utf-8 -*-
{
    'name': 'Exchange Difference - Force Payment Date',
    'version': '17.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Forces exchange difference journal entries to use payment date instead of reconciliation date',
    'description': """
        Exchange Difference - Force Payment Date
        =========================================
        
        This module fixes two critical exchange rate issues in Odoo:
        
        Problem 1: Exchange Diff Date
        -----------------------------
        * Standard Odoo: EXCH entries use reconciliation date or bill date
        * This Module: EXCH entries use PAYMENT DATE
        
        Problem 2: Payment Exchange Rate
        --------------------------------
        * Standard Odoo: When registering payment, exchange rate is fetched from TODAY
        * This Module: Exchange rate is fetched from PAYMENT DATE
        
        Example Scenario:
        ----------------
        1. Bill dated: 24/06/2025 (Rate: 33.00)
        2. Payment dated: 24/12/2025 (Rate: 35.00)
        3. Reconciliation date: 26/12/2025
        
        BEFORE this module:
        - Payment uses rate from 26/12/2025 (TODAY)
        - EXCH entry dated: 24/06/2025 (bill date)
        
        AFTER this module:
        - Payment uses rate from 24/12/2025 (payment date)
        - EXCH entry dated: 24/12/2025 (payment date)
        
        Technical:
        ----------
        * Inherits: account.move.line, account.payment, account.move, account.payment.register
        * Key Methods:
          - _prepare_exchange_difference_move_vals() - Fix EXCH date
          - _seek_for_lines() - Fix payment rate lookup
          - _compute_amount() - Fix wizard rate lookup
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
    ],
    'data': [],
    'installable': True,
    'auto_install': False,
    'application': False,
}
