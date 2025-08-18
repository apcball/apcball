#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test script to check valuation settings
Run this after creating a transfer to debug valuation issues
"""

import xmlrpc.client

# Odoo connection settings
url = 'http://mogdev.work:8069'
db = 'MOG_LIVE_28-06'
username = 'apichart@mogen.co.th'  # Replace with actual username
password = '471109538'  # Replace with actual password

def test_valuation_settings():
    try:
        # Connect to Odoo
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            print("Authentication failed!")
            return
            
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        # Check product categories
        print("=== Product Categories Valuation Settings ===")
        categories = models.execute_kw(db, uid, password, 'product.category', 'search_read', 
                                     [[]], {'fields': ['name', 'property_cost_method', 'property_valuation']})
        
        for cat in categories:
            print(f"Category: {cat['name']}")
            print(f"  Cost Method: {cat.get('property_cost_method', 'N/A')}")
            print(f"  Valuation: {cat.get('property_valuation', 'N/A')}")
            print()
        
        # Check company settings
        print("=== Company Settings ===")
        company = models.execute_kw(db, uid, password, 'res.company', 'search_read',
                                  [[('id', '=', 1)]], {'fields': ['name', 'anglo_saxon_accounting']})
        
        if company:
            print(f"Company: {company[0]['name']}")
            print(f"Anglo-Saxon Accounting: {company[0].get('anglo_saxon_accounting', False)}")
            print()
        
        # Check recent stock moves with price_unit
        print("=== Recent Stock Moves with Price Unit ===")
        moves = models.execute_kw(db, uid, password, 'stock.move', 'search_read',
                                [[('create_date', '>=', '2024-01-01'), ('price_unit', '>', 0)]],
                                {'fields': ['name', 'product_id', 'price_unit', 'state', 'location_id', 'location_dest_id'],
                                 'limit': 10, 'order': 'create_date desc'})
        
        for move in moves:
            print(f"Move: {move['name']}")
            print(f"  Product: {move['product_id'][1] if move['product_id'] else 'N/A'}")
            print(f"  Price Unit: {move['price_unit']}")
            print(f"  State: {move['state']}")
            print(f"  From: {move['location_id'][1] if move['location_id'] else 'N/A'}")
            print(f"  To: {move['location_dest_id'][1] if move['location_dest_id'] else 'N/A'}")
            print()
        
        # Check stock valuation layers
        print("=== Recent Stock Valuation Layers ===")
        svls = models.execute_kw(db, uid, password, 'stock.valuation.layer', 'search_read',
                               [[('create_date', '>=', '2024-01-01')]],
                               {'fields': ['stock_move_id', 'product_id', 'quantity', 'unit_cost', 'value'],
                                'limit': 10, 'order': 'create_date desc'})
        
        if svls:
            for svl in svls:
                print(f"SVL: {svl['id']}")
                print(f"  Move: {svl['stock_move_id'][1] if svl['stock_move_id'] else 'N/A'}")
                print(f"  Product: {svl['product_id'][1] if svl['product_id'] else 'N/A'}")
                print(f"  Quantity: {svl['quantity']}")
                print(f"  Unit Cost: {svl['unit_cost']}")
                print(f"  Value: {svl['value']}")
                print()
        else:
            print("No stock valuation layers found!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_valuation_settings()
