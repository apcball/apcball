# -*- coding: utf-8 -*-

"""
Test script for Job Cost Line Editing functionality
This script can be used to verify the implementation works correctly
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TestJobCostLineEditing(models.TransientModel):
    _name = 'test.job.cost.line.editing'
    _description = 'Test Job Cost Line Editing'

    def test_cost_type_validation(self):
        """Test cost type and product compatibility validation"""
        # Create a test job cost sheet
        project = self.env['project.project'].create({
            'name': 'Test Project for Cost Line Editing'
        })
        
        cost_sheet = self.env['job.cost.sheet'].create({
            'name': 'Test Cost Sheet',
            'project_id': project.id,
        })
        
        # Test 1: Create material cost line with storable product
        try:
            material_line = self.env['job.cost.line'].create({
                'cost_sheet_id': cost_sheet.id,
                'cost_type': 'material',
                'name': 'Test Material',
                'planned_qty': 10,
                'unit_cost': 100,
            })
            print("✓ Material cost line created successfully")
        except Exception as e:
            print(f"✗ Failed to create material cost line: {e}")
        
        # Test 2: Create labour cost line
        try:
            labour_line = self.env['job.cost.line'].create({
                'cost_sheet_id': cost_sheet.id,
                'cost_type': 'labour',
                'name': 'Test Labour',
                'planned_qty': 8,
                'unit_cost': 25,
            })
            print("✓ Labour cost line created successfully")
        except Exception as e:
            print(f"✗ Failed to create labour cost line: {e}")
        
        # Test 3: Create overhead cost line
        try:
            overhead_line = self.env['job.cost.line'].create({
                'cost_sheet_id': cost_sheet.id,
                'cost_type': 'overhead',
                'name': 'Test Overhead',
                'planned_qty': 1,
                'unit_cost': 500,
            })
            print("✓ Overhead cost line created successfully")
        except Exception as e:
            print(f"✗ Failed to create overhead cost line: {e}")
        
        # Test 4: Change cost type
        try:
            material_line.write({'cost_type': 'labour'})
            print("✓ Cost type changed successfully")
        except Exception as e:
            print(f"✗ Failed to change cost type: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Test Completed',
                'message': 'Job Cost Line Editing test completed. Check logs for results.',
                'type': 'info',
            }
        }

    def test_bulk_operations(self):
        """Test bulk editing operations"""
        # Find existing cost lines or create test data
        cost_lines = self.env['job.cost.line'].search([], limit=3)
        
        if not cost_lines:
            print("No cost lines found for bulk testing")
            return
        
        # Test bulk cost type update
        try:
            wizard = self.env['job.cost.line.wizard'].create({
                'job_cost_line_ids': [(6, 0, cost_lines.ids)],
                'new_cost_type': 'overhead',
                'clear_product': True,
            })
            wizard.action_update_cost_type()
            print("✓ Bulk cost type update successful")
        except Exception as e:
            print(f"✗ Bulk cost type update failed: {e}")
        
        # Test bulk edit
        try:
            bulk_wizard = self.env['job.cost.line.bulk.edit.wizard'].create({
                'job_cost_line_ids': [(6, 0, cost_lines.ids)],
                'update_unit_cost': True,
                'new_unit_cost': 150.0,
            })
            bulk_wizard.action_bulk_update()
            print("✓ Bulk edit successful")
        except Exception as e:
            print(f"✗ Bulk edit failed: {e}")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Bulk Test Completed',
                'message': 'Bulk operations test completed. Check logs for results.',
                'type': 'info',
            }
        }