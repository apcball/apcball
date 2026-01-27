#!/usr/bin/env python3
"""
Script to delete old dashboard action before upgrade
"""
import os
import sys

# Add the Odoo path
odoo_path = '/opt/instance1/odoo17'
if odoo_path not in sys.path:
    sys.path.insert(0, odoo_path)

import odoo
from odoo import api
from odoo.modules import registry

def delete_old_action():
    """Delete old action to allow changing type"""
    db_name = 'MOG_LIVE_15_08'  # Adjust if your database name is different
    
    try:
        # Use the correct way to get registry
        reg = registry.Registry(db_name)
        
        with reg.cursor() as cr:
            env = api.Environment(cr, 1, {})
            
            # Find and delete old action
            IrModelData = env['ir.model.data']
            
            # Look for the external ID
            data_record = IrModelData.search([
                ('module', '=', 'buz_warranty_management'),
                ('name', '=', 'action_warranty_dashboard')
            ])
            
            if data_record:
                print(f"Found external ID record: {data_record.id}")
                print(f"Model: {data_record.model}, Res ID: {data_record.res_id}")
                
                # Get the actual action record
                if data_record.model == 'ir.actions.act_window':
                    action = env['ir.actions.act_window'].browse(data_record.res_id)
                    if action.exists():
                        print(f"Deleting old act_window action: {action.name}")
                        action.unlink()
                
                # Delete the external ID record
                print("Deleting external ID record")
                data_record.unlink()
                
                print("Old action deleted successfully!")
            else:
                print("No old action found - this is fine if it's first install")
            
            cr.commit()
            
    except Exception as e:
        print(f"Error deleting old action: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    delete_old_action()
