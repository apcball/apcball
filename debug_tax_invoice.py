#!/usr/bin/env python3
# Test script to debug tax invoice creation
import sys
import os
sys.path.append('/opt/instance1/odoo17')

import odoo
from odoo.api import Environment

# Connect to database
db_name = 'mogdev_db'
odoo.tools.config.parse_config([])
odoo.tools.config['db_host'] = 'localhost'
odoo.tools.config['db_port'] = 5432
odoo.tools.config['db_user'] = 'mogdev'
odoo.tools.config['db_password'] = 'Apc@2558'

# Initialize registry
from odoo.modules.registry import Registry
registry = Registry.new(db_name)

with registry.cursor() as cr:
    env = Environment(cr, 1, {})  # uid=1 (admin)
    
    # Check if Thai tax module is installed
    print("=== Checking Thai Tax Module ===")
    thai_module = env['ir.module.module'].search([('name', '=', 'l10n_th_account_tax')])
    if thai_module:
        print(f"Thai tax module state: {thai_module.state}")
    else:
        print("Thai tax module not found")
    
    # Check account.move.tax.invoice model
    try:
        tax_invoice_model = env['account.move.tax.invoice']
        print(f"account.move.tax.invoice model exists: {tax_invoice_model}")
        
        # Check fields
        fields = tax_invoice_model._fields
        relevant_fields = ['tax_invoice_number', 'tax_invoice_date', 'move_id', 'move_line_id', 'tax_base_amount', 'balance']
        for field in relevant_fields:
            if field in fields:
                print(f"  Field {field}: {fields[field]}")
            else:
                print(f"  Field {field}: NOT FOUND")
                
    except Exception as e:
        print(f"Error accessing account.move.tax.invoice: {e}")
    
    # Test creating a simple move with taxes
    print("\n=== Testing Move Creation ===")
    try:
        # Find a tax
        vat_tax = env['account.tax'].search([('name', 'ilike', 'vat'), ('amount', '>', 0)], limit=1)
        if not vat_tax:
            vat_tax = env['account.tax'].search([('amount', '>', 0)], limit=1)
        
        if vat_tax:
            print(f"Using tax: {vat_tax.name} ({vat_tax.amount}%)")
            
            # Find accounts
            expense_account = env['account.account'].search([('account_type', '=', 'expense')], limit=1)
            cash_account = env['account.account'].search([('account_type', '=', 'asset_cash')], limit=1)
            journal = env['account.journal'].search([('type', '=', 'general')], limit=1)
            
            if expense_account and cash_account and journal:
                print(f"Expense account: {expense_account.code} - {expense_account.name}")
                print(f"Cash account: {cash_account.code} - {cash_account.name}")
                print(f"Journal: {journal.name}")
                
                # Create test move
                move = env['account.move'].create({
                    'move_type': 'entry',
                    'journal_id': journal.id,
                    'date': '2025-01-16',
                    'ref': 'Test Tax Invoice',
                    'line_ids': [
                        (0, 0, {
                            'name': 'Test Expense',
                            'account_id': expense_account.id,
                            'debit': 100.0,
                            'credit': 0.0,
                            'tax_ids': [(6, 0, vat_tax.ids)],
                        }),
                        (0, 0, {
                            'name': 'Cash Payment',
                            'account_id': cash_account.id,
                            'debit': 0.0,
                            'credit': 107.0,  # 100 + 7% VAT
                        }),
                    ],
                })
                
                print(f"Created move: {move.name}")
                
                # Recompute taxes
                move._recompute_dynamic_lines(recompute_all_taxes=True)
                print("Recomputed tax lines")
                
                # Check move lines
                for line in move.line_ids:
                    print(f"  Line: {line.name}, Account: {line.account_id.code}, Debit: {line.debit}, Credit: {line.credit}, Tax Line ID: {line.tax_line_id}")
                
                # Check tax invoice records
                if hasattr(move, 'tax_invoice_ids'):
                    print(f"Move tax_invoice_ids: {move.tax_invoice_ids}")
                    for ti in move.tax_invoice_ids:
                        print(f"  Tax Invoice: {ti.tax_invoice_number} / {ti.tax_invoice_date}")
                
                # Check from move lines
                for line in move.line_ids.filtered('tax_line_id'):
                    if hasattr(line, 'tax_invoice_ids'):
                        print(f"Line {line.name} tax_invoice_ids: {line.tax_invoice_ids}")
                        for ti in line.tax_invoice_ids:
                            print(f"  Tax Invoice: {ti.tax_invoice_number} / {ti.tax_invoice_date}")
                
                # Try to post
                try:
                    move._post()
                    print("Move posted successfully!")
                except Exception as e:
                    print(f"Error posting move: {e}")
                
            else:
                print("Required accounts/journal not found")
        else:
            print("No tax found for testing")
            
    except Exception as e:
        print(f"Error in test: {e}")
        import traceback
        traceback.print_exc()