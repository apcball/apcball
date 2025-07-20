# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api
from odoo.tests import TransactionCase

_logger = logging.getLogger(__name__)

class TestActualCostsDebug(TransactionCase):
    """Test class to debug actual costs computation issues"""
    
    def setUp(self):
        super(TestActualCostsDebug, self).setUp()
        
        # Create test data
        self.project = self.env['project.project'].create({
            'name': 'Test Project for Actual Costs',
        })
        
        self.analytic_account = self.env['account.analytic.account'].create({
            'name': 'Test Analytic Account',
            'plan_id': self.env['account.analytic.plan'].search([], limit=1).id,
        })
        
        self.job_cost_sheet = self.env['job.cost.sheet'].create({
            'name': 'Test Cost Sheet',
            'project_id': self.project.id,
            'analytic_account_id': self.analytic_account.id,
        })
        
        # Create service product for labour
        self.labour_product = self.env['product.product'].create({
            'name': 'Labour Service',
            'detailed_type': 'service',
            'standard_price': 500.0,
            'uom_id': self.env.ref('uom.product_uom_hour').id,
        })
        
        # Create labour cost line
        self.labour_cost_line = self.env['job.cost.line'].create({
            'cost_sheet_id': self.job_cost_sheet.id,
            'cost_type': 'labour',
            'product_id': self.labour_product.id,
            'name': 'Test Labour',
            'planned_qty': 10.0,
            'unit_cost': 500.0,
            'uom_id': self.env.ref('uom.product_uom_hour').id,
            'analytic_account_id': self.analytic_account.id,
        })
        
        # Create employee
        self.employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
        })
    
    def test_labour_actual_costs_debug(self):
        """Debug labour actual costs computation"""
        
        _logger.info("=== DEBUGGING LABOUR ACTUAL COSTS ===")
        
        # Check initial state
        _logger.info(f"Initial labour cost line:")
        _logger.info(f"  - planned_qty: {self.labour_cost_line.planned_qty}")
        _logger.info(f"  - unit_cost: {self.labour_cost_line.unit_cost}")
        _logger.info(f"  - total_cost: {self.labour_cost_line.total_cost}")
        _logger.info(f"  - actual_qty: {self.labour_cost_line.actual_qty}")
        _logger.info(f"  - actual_unit_cost: {self.labour_cost_line.actual_unit_cost}")
        _logger.info(f"  - actual_cost: {self.labour_cost_line.actual_cost}")
        _logger.info(f"  - timesheet_ids count: {len(self.labour_cost_line.timesheet_ids)}")
        
        # Create timesheet entry
        timesheet = self.env['account.analytic.line'].create({
            'name': 'Test Timesheet Entry',
            'account_id': self.analytic_account.id,
            'employee_id': self.employee.id,
            'unit_amount': 8.0,  # 8 hours
            'amount': -4000.0,   # Cost (negative in Odoo)
            'job_cost_line_id': self.labour_cost_line.id,
        })
        
        _logger.info(f"Created timesheet:")
        _logger.info(f"  - unit_amount: {timesheet.unit_amount}")
        _logger.info(f"  - amount: {timesheet.amount}")
        _logger.info(f"  - job_cost_line_id: {timesheet.job_cost_line_id.id}")
        
        # Force recomputation
        self.labour_cost_line._compute_actual_qty()
        self.labour_cost_line._compute_actual_unit_cost()
        self.labour_cost_line._compute_actual_cost()
        
        _logger.info(f"After timesheet creation:")
        _logger.info(f"  - actual_qty: {self.labour_cost_line.actual_qty}")
        _logger.info(f"  - actual_unit_cost: {self.labour_cost_line.actual_unit_cost}")
        _logger.info(f"  - actual_cost: {self.labour_cost_line.actual_cost}")
        _logger.info(f"  - timesheet_ids count: {len(self.labour_cost_line.timesheet_ids)}")
        
        # Check timesheet linking
        for ts in self.labour_cost_line.timesheet_ids:
            _logger.info(f"  - Linked timesheet: unit_amount={ts.unit_amount}, amount={ts.amount}")
        
        # Test job cost sheet totals
        self.job_cost_sheet._compute_actual_costs()
        
        _logger.info(f"Job cost sheet totals:")
        _logger.info(f"  - actual_labour_cost: {self.job_cost_sheet.actual_labour_cost}")
        _logger.info(f"  - actual_total_cost: {self.job_cost_sheet.actual_total_cost}")
        
        return True
    
    def test_material_actual_costs_debug(self):
        """Debug material actual costs computation"""
        
        _logger.info("=== DEBUGGING MATERIAL ACTUAL COSTS ===")
        
        # Create material product
        material_product = self.env['product.product'].create({
            'name': 'Test Material',
            'detailed_type': 'product',
            'standard_price': 100.0,
        })
        
        # Create material cost line
        material_cost_line = self.env['job.cost.line'].create({
            'cost_sheet_id': self.job_cost_sheet.id,
            'cost_type': 'material',
            'product_id': material_product.id,
            'name': 'Test Material',
            'planned_qty': 50.0,
            'unit_cost': 100.0,
            'analytic_account_id': self.analytic_account.id,
        })
        
        _logger.info(f"Initial material cost line:")
        _logger.info(f"  - planned_qty: {material_cost_line.planned_qty}")
        _logger.info(f"  - unit_cost: {material_cost_line.unit_cost}")
        _logger.info(f"  - total_cost: {material_cost_line.total_cost}")
        _logger.info(f"  - actual_qty: {material_cost_line.actual_qty}")
        _logger.info(f"  - actual_unit_cost: {material_cost_line.actual_unit_cost}")
        _logger.info(f"  - actual_cost: {material_cost_line.actual_cost}")
        _logger.info(f"  - purchase_order_line_ids count: {len(material_cost_line.purchase_order_line_ids)}")
        
        # Create vendor
        vendor = self.env['res.partner'].create({
            'name': 'Test Vendor',
            'is_company': True,
            'supplier_rank': 1,
        })
        
        # Create purchase order
        purchase_order = self.env['purchase.order'].create({
            'partner_id': vendor.id,
            'job_cost_sheet_id': self.job_cost_sheet.id,
        })
        
        # Create purchase order line
        po_line = self.env['purchase.order.line'].create({
            'order_id': purchase_order.id,
            'product_id': material_product.id,
            'name': material_product.name,
            'product_qty': 30.0,
            'price_unit': 120.0,
            'job_cost_line_id': material_cost_line.id,
        })
        
        _logger.info(f"Created PO line:")
        _logger.info(f"  - product_qty: {po_line.product_qty}")
        _logger.info(f"  - price_unit: {po_line.price_unit}")
        _logger.info(f"  - price_subtotal: {po_line.price_subtotal}")
        _logger.info(f"  - job_cost_line_id: {po_line.job_cost_line_id.id}")
        
        # Confirm purchase order
        purchase_order.button_confirm()
        
        _logger.info(f"PO state after confirmation: {purchase_order.state}")
        
        # Simulate receipt
        po_line.qty_received = 25.0
        
        _logger.info(f"After receipt simulation:")
        _logger.info(f"  - qty_received: {po_line.qty_received}")
        
        # Force recomputation
        material_cost_line._compute_actual_qty()
        material_cost_line._compute_actual_unit_cost()
        material_cost_line._compute_actual_cost()
        
        _logger.info(f"After PO confirmation and receipt:")
        _logger.info(f"  - actual_qty: {material_cost_line.actual_qty}")
        _logger.info(f"  - actual_unit_cost: {material_cost_line.actual_unit_cost}")
        _logger.info(f"  - actual_cost: {material_cost_line.actual_cost}")
        
        return True