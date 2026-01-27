# -*- coding: utf-8 -*-

"""
Test script to verify actual costs computation
Run this in Odoo shell to test actual costs functionality
"""

def test_labour_actual_costs():
    """Test labour actual costs computation"""
    
    # Get environment
    env = globals().get('env')
    if not env:
        print("This script should be run in Odoo shell")
        return
    
    print("=== Testing Labour Actual Costs ===")
    
    # Find or create test data
    project = env['project.project'].search([('name', 'ilike', 'test')], limit=1)
    if not project:
        project = env['project.project'].create({
            'name': 'Test Project for Actual Costs',
        })
        print(f"Created test project: {project.name}")
    
    # Find or create analytic account
    analytic_account = env['account.analytic.account'].search([('name', 'ilike', 'test')], limit=1)
    if not analytic_account:
        analytic_plan = env['account.analytic.plan'].search([], limit=1)
        analytic_account = env['account.analytic.account'].create({
            'name': 'Test Analytic Account',
            'plan_id': analytic_plan.id if analytic_plan else False,
        })
        print(f"Created test analytic account: {analytic_account.name}")
    
    # Find or create job cost sheet
    job_cost_sheet = env['job.cost.sheet'].search([
        ('project_id', '=', project.id),
        ('analytic_account_id', '=', analytic_account.id)
    ], limit=1)
    
    if not job_cost_sheet:
        job_cost_sheet = env['job.cost.sheet'].create({
            'name': 'Test Cost Sheet',
            'project_id': project.id,
            'analytic_account_id': analytic_account.id,
            'state': 'approved',
        })
        print(f"Created test job cost sheet: {job_cost_sheet.name}")
    
    # Find or create labour product
    labour_product = env['product.product'].search([
        ('detailed_type', '=', 'service'),
        ('name', 'ilike', 'labour')
    ], limit=1)
    
    if not labour_product:
        hours_uom = env['uom.uom'].search([('name', 'ilike', 'hour')], limit=1)
        labour_product = env['product.product'].create({
            'name': 'Labour Service Test',
            'detailed_type': 'service',
            'standard_price': 500.0,
            'uom_id': hours_uom.id if hours_uom else env.ref('uom.product_uom_hour').id,
        })
        print(f"Created test labour product: {labour_product.name}")
    
    # Find or create labour cost line
    labour_cost_line = env['job.cost.line'].search([
        ('cost_sheet_id', '=', job_cost_sheet.id),
        ('cost_type', '=', 'labour')
    ], limit=1)
    
    if not labour_cost_line:
        labour_cost_line = env['job.cost.line'].create({
            'cost_sheet_id': job_cost_sheet.id,
            'cost_type': 'labour',
            'product_id': labour_product.id,
            'name': 'Test Labour Work',
            'planned_qty': 10.0,
            'unit_cost': 500.0,
            'uom_id': labour_product.uom_id.id,
            'analytic_account_id': analytic_account.id,
        })
        print(f"Created test labour cost line: {labour_cost_line.name}")
    
    # Find or create employee
    employee = env['hr.employee'].search([('name', 'ilike', 'test')], limit=1)
    if not employee:
        employee = env['hr.employee'].create({
            'name': 'Test Employee',
        })
        print(f"Created test employee: {employee.name}")
    
    print(f"\nInitial state:")
    print(f"  Labour cost line: {labour_cost_line.name}")
    print(f"  Planned qty: {labour_cost_line.planned_qty}")
    print(f"  Unit cost: {labour_cost_line.unit_cost}")
    print(f"  Total cost: {labour_cost_line.total_cost}")
    print(f"  Actual qty: {labour_cost_line.actual_qty}")
    print(f"  Actual unit cost: {labour_cost_line.actual_unit_cost}")
    print(f"  Actual cost: {labour_cost_line.actual_cost}")
    print(f"  Timesheet count: {len(labour_cost_line.timesheet_ids)}")
    
    # Create timesheet entry
    timesheet = env['account.analytic.line'].create({
        'name': 'Test Timesheet Entry',
        'account_id': analytic_account.id,
        'employee_id': employee.id,
        'unit_amount': 8.0,  # 8 hours
        'amount': -4000.0,   # Cost (negative in Odoo)
        'job_cost_line_id': labour_cost_line.id,
    })
    
    print(f"\nCreated timesheet:")
    print(f"  Name: {timesheet.name}")
    print(f"  Unit amount: {timesheet.unit_amount}")
    print(f"  Amount: {timesheet.amount}")
    print(f"  Job cost line: {timesheet.job_cost_line_id.name if timesheet.job_cost_line_id else 'None'}")
    
    # Force recomputation
    labour_cost_line.invalidate_recordset()
    labour_cost_line._compute_actual_qty()
    labour_cost_line._compute_actual_unit_cost()
    labour_cost_line._compute_actual_cost()
    
    print(f"\nAfter timesheet creation:")
    print(f"  Actual qty: {labour_cost_line.actual_qty}")
    print(f"  Actual unit cost: {labour_cost_line.actual_unit_cost}")
    print(f"  Actual cost: {labour_cost_line.actual_cost}")
    print(f"  Timesheet count: {len(labour_cost_line.timesheet_ids)}")
    
    # Check linked timesheets
    for ts in labour_cost_line.timesheet_ids:
        print(f"  Linked timesheet: {ts.name}, unit_amount={ts.unit_amount}, amount={ts.amount}")
    
    # Test job cost sheet totals
    job_cost_sheet.invalidate_recordset()
    job_cost_sheet._compute_actual_costs()
    
    print(f"\nJob cost sheet totals:")
    print(f"  Actual labour cost: {job_cost_sheet.actual_labour_cost}")
    print(f"  Actual total cost: {job_cost_sheet.actual_total_cost}")
    print(f"  Labour variance: {job_cost_sheet.labour_variance}")
    
    # Test sync function
    print(f"\nTesting sync function...")
    result = job_cost_sheet.action_sync_actual_costs()
    print(f"Sync result: {result}")
    
    print(f"\nAfter sync:")
    print(f"  Actual labour cost: {job_cost_sheet.actual_labour_cost}")
    print(f"  Actual total cost: {job_cost_sheet.actual_total_cost}")
    
    return {
        'job_cost_sheet': job_cost_sheet,
        'labour_cost_line': labour_cost_line,
        'timesheet': timesheet,
    }

def test_timesheet_auto_linking():
    """Test automatic timesheet linking"""
    
    env = globals().get('env')
    if not env:
        print("This script should be run in Odoo shell")
        return
    
    print("=== Testing Timesheet Auto-linking ===")
    
    # Find existing test data
    analytic_account = env['account.analytic.account'].search([('name', 'ilike', 'test')], limit=1)
    job_cost_sheet = env['job.cost.sheet'].search([('analytic_account_id', '=', analytic_account.id)], limit=1)
    employee = env['hr.employee'].search([('name', 'ilike', 'test')], limit=1)
    
    if not all([analytic_account, job_cost_sheet, employee]):
        print("Please run test_labour_actual_costs() first")
        return
    
    # Create timesheet without job_cost_line_id
    timesheet = env['account.analytic.line'].create({
        'name': 'Auto-link Test Timesheet',
        'account_id': analytic_account.id,
        'employee_id': employee.id,
        'unit_amount': 4.0,  # 4 hours
        'amount': -2000.0,   # Cost
    })
    
    print(f"Created timesheet without job_cost_line_id:")
    print(f"  Name: {timesheet.name}")
    print(f"  Job cost line before: {timesheet.job_cost_line_id.name if timesheet.job_cost_line_id else 'None'}")
    
    # Trigger auto-linking
    timesheet._auto_link_to_job_cost_line()
    
    print(f"  Job cost line after auto-link: {timesheet.job_cost_line_id.name if timesheet.job_cost_line_id else 'None'}")
    
    return timesheet

# Instructions for running in Odoo shell:
print("""
To run these tests in Odoo shell:

1. Start Odoo shell:
   python odoo-bin shell -d your_database

2. Run the tests:
   exec(open('/path/to/job_costing_management/test_actual_costs_fix.py').read())
   test_data = test_labour_actual_costs()
   test_timesheet_auto_linking()
""")