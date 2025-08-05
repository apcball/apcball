# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class InventoryValuationReport(models.TransientModel):
    _name = 'inventory.valuation.report'
    _description = 'Inventory Valuation Report'

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
        string='Start Date',
        required=True,
        default=_get_default_start_date
    )
    end_date = fields.Date(
        string='End Date',
        required=True,
        default=_get_default_end_date
    )
    warehouse_ids = fields.Many2many(
        'stock.warehouse',
        string='Warehouses',
        help='Select specific warehouses. Leave empty to include all warehouses.'
    )
    location_ids = fields.Many2many(
        'stock.location',
        string='Locations',
        help='Select specific locations. Leave empty to include all locations.'
    )
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        help='Select specific products. Leave empty to include all products.'
    )
    category_ids = fields.Many2many(
        'product.category',
        string='Product Categories',
        help='Select specific product categories. Leave empty to include all categories.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        """Validate that start date is not greater than end date"""
        for record in self:
            if record.start_date and record.end_date:
                if record.start_date > record.end_date:
                    raise ValueError(_('Start date cannot be greater than end date.'))

    def _get_domain_filters(self):
        """Build domain filters based on wizard selections"""
        domain = []
        
        # Date filter
        if self.start_date:
            domain.append(('date', '>=', self.start_date))
        if self.end_date:
            domain.append(('date', '<=', self.end_date))
        
        # Location filter
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        elif self.warehouse_ids:
            # If warehouses are selected but not locations, use warehouse locations
            warehouse_locations = self.warehouse_ids.mapped('lot_stock_id')
            domain.append(('location_id', 'in', warehouse_locations.ids))
        
        # Product filter
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        elif self.category_ids:
            # If categories selected but not products, filter by category
            products_in_category = self.env['product.product'].search([
                ('categ_id', 'in', self.category_ids.ids)
            ])
            domain.append(('product_id', 'in', products_in_category.ids))
        
        # Company filter
        domain.append(('company_id', '=', self.company_id.id))
        
        return domain

    def _get_inventory_data(self):
        """Get inventory valuation data based on filters"""
        domain = self._get_domain_filters()
        
        # Get stock moves for the period
        stock_moves = self.env['stock.move'].search(domain + [('state', '=', 'done')])
        
        inventory_data = {}
        
        for move in stock_moves:
            product = move.product_id
            location = move.location_dest_id if move.location_dest_id.usage == 'internal' else move.location_id
            
            key = (product.id, location.id)
            
            if key not in inventory_data:
                inventory_data[key] = {
                    'product': product,
                    'location': location,
                    'quantity': 0.0,
                    'value': 0.0,
                    'cost_price': product.standard_price,
                }
            
            # Calculate quantity and value based on move direction
            if move.location_dest_id.usage == 'internal':
                # Incoming move
                inventory_data[key]['quantity'] += move.product_uom_qty
                inventory_data[key]['value'] += move.product_uom_qty * product.standard_price
            else:
                # Outgoing move
                inventory_data[key]['quantity'] -= move.product_uom_qty
                inventory_data[key]['value'] -= move.product_uom_qty * product.standard_price

        return list(inventory_data.values())

    def action_print_pdf_report(self):
        """Generate PDF report"""
        data = {
            'ids': self.ids,
            'model': self._name,
            'form': self.read()[0],
            'inventory_data': self._get_inventory_data(),
        }
        return self.env.ref('buz_inventory_valuation_report.action_inventory_valuation_pdf_report').report_action(self, data=data)

    def action_print_xlsx_report(self):
        """Generate XLSX report"""
        # This will be implemented with the XLSX report functionality
        inventory_data = self._get_inventory_data()
        
        # For now, we'll create a simple implementation
        # In a full implementation, you would use xlsxwriter or openpyxl
        data = {
            'inventory_data': inventory_data,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'company': self.company_id.name,
        }
        
        return {
            'type': 'ir.actions.report',
            'report_name': 'buz_inventory_valuation_report.xlsx_template',
            'report_type': 'xlsx',
            'data': data,
            'context': self.env.context,
        }
