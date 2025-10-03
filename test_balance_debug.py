#!/usr/bin/env python3
"""
Test advance box balance calculation
"""
import sys
import os

# Add Odoo path
sys.path.append('/opt/instance1/odoo17')

print("=== Test Balance Calculation ===")

# สร้าง test script ที่ run ใน Odoo shell
odoo_test_script = '''
# Run this in Odoo shell: python3 odoo-bin shell -c config_file -d database_name

# 1. Test Advance Box Balance
advance_boxes = env['employee.advance.box'].search([])
for box in advance_boxes[:3]:  # Test first 3 boxes
    print(f"\\n=== Box ID: {box.id} Employee: {box.employee_id.name} ===")
    print(f"Account: {box.account_id.code if box.account_id else 'No Account'}")
    print(f"Current Balance: {box.balance}")
    
    # Force recompute
    box._compute_balance()
    print(f"Recomputed Balance: {box.balance}")
    
    # Check Partner
    if box.employee_id:
        employee_partner = env['res.partner'].search([
            ('name', '=', box.employee_id.name),
            ('is_company', '=', False)
        ], limit=1)
        
        if employee_partner:
            print(f"Employee Partner: {employee_partner.name} (ID: {employee_partner.id})")
        else:
            print("No employee partner found")
            
        # Check fallback partners
        if hasattr(box.employee_id, 'address_home_id') and box.employee_id.sudo().address_home_id:
            print(f"address_home_id: {box.employee_id.sudo().address_home_id.id}")
        if box.employee_id.user_id:
            print(f"user partner_id: {box.employee_id.user_id.partner_id.id}")

# 2. Check Account Move Lines
print("\\n=== Recent Account Move Lines ===")
recent_moves = env['account.move.line'].search([
    ('create_date', '>=', (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')),
    ('move_id.state', '=', 'posted')
], order='create_date desc', limit=10)

for line in recent_moves:
    print(f"Date: {line.date} | Partner: {line.partner_id.name if line.partner_id else 'No Partner'}")
    print(f"Account: {line.account_id.code} | Dr: {line.debit} | Cr: {line.credit}")
    print(f"Move: {line.move_id.name}")
    print("---")
'''

print("=== Odoo Shell Test Script ===")
print(odoo_test_script)

print("\n=== Manual Check Commands ===")
manual_check = '''
# 1. Check specific advance box
box = env['employee.advance.box'].browse(1)  # Change ID as needed
print("Employee:", box.employee_id.name)
print("Account:", box.account_id.code if box.account_id else None)
print("Balance:", box.balance)

# 2. Check partner matching
emp_partner = env['res.partner'].search([('name', '=', box.employee_id.name), ('is_company', '=', False)], limit=1)
print("Employee Partner:", emp_partner.name if emp_partner else "Not Found")

# 3. Check account move lines
if emp_partner and box.account_id:
    lines = env['account.move.line'].search([
        ('account_id', '=', box.account_id.id),
        ('move_id.state', '=', 'posted'),
        ('partner_id', '=', emp_partner.id),
    ])
    print(f"Found {len(lines)} account move lines")
    for line in lines:
        print(f"  {line.date} | {line.name} | Dr: {line.debit} | Cr: {line.credit}")
'''

print(manual_check)