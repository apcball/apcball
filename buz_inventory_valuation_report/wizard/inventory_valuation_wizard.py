# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import base64


class InventoryValuationWizard(models.TransientModel):
    _name = 'inventory.valuation.wizard'
    _description = 'Inventory Valuation Report Wizard'

    @api.model
    def _get_default_start_date(self):
        """Get the first day of current month as default start date"""
        today = fields.Date.today()
        return today.replace(day=1)

    @api.model
    def _get_default_end_date(self):
        """Get today as default end date"""
        return fields.Date.today()

    start_date = fields.Date(
        string='Report Date From',
        required=True,
        default=_get_default_start_date,
        help='Starting date for the report period (for reference only)'
    )
    end_date = fields.Date(
        string='Report Date To',
        required=True,
        default=_get_default_end_date,
        help='Ending date for the report period (for reference only)'
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        'wizard_warehouse_rel',
        'wizard_id',
        'warehouse_id',
        string='Warehouses',
        help='Select specific warehouses. Leave empty to include all warehouses.'
    )
    location_ids = fields.Many2many(
        'stock.location',
        'wizard_location_rel',
        'wizard_id',
        'location_id',
        string='Locations',
        domain=[('usage', '=', 'internal')],
        help='Select specific locations. Leave empty to include all locations.'
    )
    product_ids = fields.Many2many(
        'product.product',
        'wizard_product_rel',
        'wizard_id',
        'product_id',
        string='Products',
        domain=[('type', '=', 'product')],
        help='Select specific products. Leave empty to include all products.'
    )
    category_ids = fields.Many2many(
        'product.category',
        'wizard_category_rel',
        'wizard_id',
        'category_id',
        string='Product Categories',
        help='Select specific product categories. Leave empty to include all categories.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    report_type = fields.Selection([
        ('xlsx', 'Excel Report')
    ], string='Report Type', default='xlsx', required=True)

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        """Validate that start date is not greater than end date"""
        for record in self:
            if record.start_date and record.end_date:
                if record.start_date > record.end_date:
                    raise ValidationError(_('Start date cannot be greater than end date.'))

    @api.onchange('warehouse_ids')
    def _onchange_warehouse_ids(self):
        """Update location domain when warehouses change"""
        if self.warehouse_ids:
            warehouse_locations = self.warehouse_ids.mapped('lot_stock_id')
            return {
                'domain': {
                    'location_ids': [('id', 'in', warehouse_locations.ids)]
                }
            }
        else:
            return {
                'domain': {
                    'location_ids': [('usage', '=', 'internal')]
                }
            }

    @api.onchange('category_ids')
    def _onchange_category_ids(self):
        """Update product domain when categories change"""
        if self.category_ids:
            products_in_category = self.env['product.product'].search([
                ('categ_id', 'in', self.category_ids.ids),
                ('type', '=', 'product')
            ])
            return {
                'domain': {
                    'product_ids': [('id', 'in', products_in_category.ids)]
                }
            }
        else:
            return {
                'domain': {
                    'product_ids': [('type', '=', 'product')]
                }
            }

    def _prepare_report_data(self):
        """Prepare data for the report based on stock movements in date range"""
        domain = []
        
        # Date filter for stock moves
        domain.append(('date', '<=', self.end_date))
        domain.append(('state', '=', 'done'))
        
        # Location filter - we need to check both source and destination locations
        location_domain = []
        if self.location_ids:
            location_domain = [
                '|', 
                ('location_id', 'in', self.location_ids.ids),
                ('location_dest_id', 'in', self.location_ids.ids)
            ]
        elif self.warehouse_ids:
            warehouse_locations = []
            for warehouse in self.warehouse_ids:
                # Get all internal locations for the warehouse
                locations = self.env['stock.location'].search([
                    ('location_id', 'child_of', warehouse.view_location_id.id),
                    ('usage', '=', 'internal')
                ])
                warehouse_locations.extend(locations.ids)
            if warehouse_locations:
                location_domain = [
                    '|', 
                    ('location_id', 'in', warehouse_locations),
                    ('location_dest_id', 'in', warehouse_locations)
                ]
        
        if location_domain:
            domain.extend(location_domain)
        
        # Product filter
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.category_ids:
            products_in_category = self.env['product.product'].search([
                ('categ_id', 'in', self.category_ids.ids),
                ('type', '=', 'product')
            ])
            domain.append(('product_id', 'in', products_in_category.ids))
        else:
            # Only include stockable products
            domain.append(('product_id.type', '=', 'product'))
        
        # Company filter
        domain.append(('company_id', '=', self.company_id.id))
        
        # Get stock moves within the date range
        stock_moves = self.env['stock.move'].search(domain, order='date desc, id desc')
        
        # Calculate inventory balances by product and location
        inventory_balance = {}
        
        for move in stock_moves:
            product = move.product_id
            
            # Skip if not a stockable product
            if product.type != 'product':
                continue
                
            # Determine if this move affects our target locations
            source_internal = move.location_id.usage == 'internal'
            dest_internal = move.location_dest_id.usage == 'internal'
            
            # Apply location filters if specified
            source_in_filter = True
            dest_in_filter = True
            
            if self.location_ids:
                source_in_filter = move.location_id.id in self.location_ids.ids
                dest_in_filter = move.location_dest_id.id in self.location_ids.ids
            elif self.warehouse_ids:
                warehouse_locations = []
                for warehouse in self.warehouse_ids:
                    locations = self.env['stock.location'].search([
                        ('location_id', 'child_of', warehouse.view_location_id.id),
                        ('usage', '=', 'internal')
                    ])
                    warehouse_locations.extend(locations.ids)
                source_in_filter = move.location_id.id in warehouse_locations
                dest_in_filter = move.location_dest_id.id in warehouse_locations
            
            # Process moves that affect our target locations
            if dest_internal and dest_in_filter:
                # Incoming stock to our location
                key = (product.id, move.location_dest_id.id)
                if key not in inventory_balance:
                    inventory_balance[key] = {
                        'product': product,
                        'location': move.location_dest_id,
                        'quantity': 0.0,
                        'total_value': 0.0,
                    }
                
                qty = move.product_uom_qty
                cost = move.price_unit or product.standard_price
                
                inventory_balance[key]['quantity'] += qty
                inventory_balance[key]['total_value'] += qty * cost
            
            if source_internal and source_in_filter:
                # Outgoing stock from our location
                key = (product.id, move.location_id.id)
                if key not in inventory_balance:
                    inventory_balance[key] = {
                        'product': product,
                        'location': move.location_id,
                        'quantity': 0.0,
                        'total_value': 0.0,
                    }
                
                qty = move.product_uom_qty
                cost = move.price_unit or product.standard_price
                
                inventory_balance[key]['quantity'] -= qty
                inventory_balance[key]['total_value'] -= qty * cost
        
        # Convert to report format and filter positive quantities only
        inventory_data = []
        total_value = 0.0
        
        for balance in inventory_balance.values():
            if balance['quantity'] > 0:  # Only show positive stock
                unit_cost = balance['total_value'] / balance['quantity'] if balance['quantity'] > 0 else 0
                
                inventory_data.append({
                    'product_code': balance['product'].default_code or '',
                    'product_name': balance['product'].name,
                    'category': balance['product'].categ_id.name,
                    'location': balance['location'].complete_name,
                    'quantity': balance['quantity'],
                    'uom': balance['product'].uom_id.name,
                    'unit_cost': unit_cost,
                    'total_value': balance['total_value'],
                })
                total_value += balance['total_value']
        
        # Sort by product name for better readability
        inventory_data = sorted(inventory_data, key=lambda x: x['product_name'])
        
        return {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'company': self.company_id,
            'warehouses': self.warehouse_ids,
            'locations': self.location_ids,
            'products': self.product_ids,
            'categories': self.category_ids,
            'inventory_data': inventory_data,
            'total_value': total_value,
        }

    def action_generate_report(self):
        """Generate the selected report type"""
        self.ensure_one()
        
        # Only XLSX is supported now
        return self.action_print_xlsx()

    def action_print_pdf(self):
        """PDF report is no longer supported"""
        raise UserError(_('PDF reports have been removed. Please use Excel format instead.'))

    def action_print_xlsx(self):
        """Generate XLSX report directly"""
        self.ensure_one()
        data = self._prepare_report_data()
        
        # Create the XLSX content
        report_model = self.env['report.buz_inventory_valuation_report.xlsx_template']
        content = report_model._create_xlsx_report(data)
        
        # Create attachment
        filename = f"inventory_valuation_{self.start_date}_to_{self.end_date}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
