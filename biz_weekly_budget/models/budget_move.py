# -*- coding: utf-8 -*-
from odoo import api, fields, models

class BudgetMove(models.Model):
    _name = 'budget.move'
    _description = 'Budget Move Ledger'
    _order = 'date desc, id desc'

    name = fields.Char(string='Description', required=True)
    
    allocation_id = fields.Many2one(
        'monthly.budget.allocation',
        string='Budget Allocation',
        required=True,
        ondelete='cascade',
        index=True
    )
    plan_id = fields.Many2one(
        related='allocation_id.plan_id',
        string='Budget Plan',
        store=True,
        index=True
    )
    
    source_model = fields.Selection([
        ('purchase.order', 'Purchase Order'),
        ('employee.purchase.requisition', 'Purchase Requisition'),
        ('material.requisition', 'Material Requisition'),
        ('account.move', 'Vendor Bill')
    ], string='Source Model', required=True)
    
    source_id = fields.Integer(string='Source Record ID', required=True, index=True)
    source_line_id = fields.Integer(string='Source Line ID', index=True, help="Specific document line ID if applicable")
    
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        index=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        index=True,
        required=False
    )
    month_key = fields.Char(string='Month Key', compute='_compute_keys', store=True)
    week_key = fields.Char(string='Week Key', compute='_compute_keys', store=True)

    reservation_date = fields.Date(string='Reservation Date', default=fields.Date.context_today)
    aging_days = fields.Integer(string='Aging Days', compute='_compute_aging_days', store=True)
    
    amount = fields.Float(string='Amount', required=True)
    move_type = fields.Selection([
        ('reserved', 'Reserved'),
        ('used', 'Used'),
        ('forecast', 'Forecast')
    ], string='Type', required=True, index=True)
    
    date = fields.Date(string='Date', required=True, index=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_source_company',
        store=True,
        index=True
    )
    currency_id = fields.Many2one(
        related='allocation_id.plan_id.currency_id',
        string='Currency',
        store=True
    )

    @api.depends('date')
    def _compute_keys(self):
        for rec in self:
            if rec.date:
                rec.month_key = rec.date.strftime('%Y-%m')
                rec.week_key = rec.date.strftime('%Y-W%W')
            else:
                rec.month_key = False
                rec.week_key = False

    @api.depends('source_model', 'source_id', 'department_id')
    def _compute_source_company(self):
        for rec in self:
            company = False
            if rec.source_model and rec.source_id:
                try:
                    source_doc = self.env[rec.source_model].sudo().browse(rec.source_id)
                    if source_doc.exists() and getattr(source_doc, 'company_id', False):
                        company = source_doc.company_id
                except Exception:
                    pass
            
            # Fallback to department's company if source is missing
            if not company and rec.department_id and rec.department_id.company_id:
                company = rec.department_id.company_id
                
            rec.company_id = company

    @api.depends('reservation_date')
    def _compute_aging_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.reservation_date and rec.move_type == 'reserved':
                delta = today - rec.reservation_date
                rec.aging_days = delta.days
            else:
                rec.aging_days = 0

    @api.model
    def _create_move(self, vals):
        """Helper handler for budget movements"""
        return self.create(vals)

    @api.model
    def extract_analytic_distribution(self, line):
        """
        Takes a document line (PO line, Bill line, PR line, MR line)
        and returns a list of dicts:
        [{'analytic_account_id': id, 'department_id': id, 'percentage': float}]

        Department priority (for budget charging):
        1. MR source department (if linked via material_requisition_line_id) — authoritative
        2. PR source department (if linked via requisition_order/pr_number)
        3. Line-level department_id
        4. Header-level department_id / dept_id
        """
        res = []
        acc_id = getattr(line, 'analytic_account_id', False)
        dept_id = False  # Will be resolved below in priority order

        # -----------------------------------------------------------
        # Priority 1: MR source department (authoritative for budget)
        # -----------------------------------------------------------
        mr_line_linked = getattr(line, 'material_requisition_line_id', False)
        if mr_line_linked and mr_line_linked.requisition_id:
            mr_dept = mr_line_linked.requisition_id.department_id
            if mr_dept:
                dept_id = mr_dept
            if not acc_id:
                acc_id = mr_line_linked.analytic_account_id or mr_line_linked.requisition_id.analytic_account_id

        # -----------------------------------------------------------
        # Priority 2: PR source department (via PO header link)
        # -----------------------------------------------------------
        if not dept_id:
            order = getattr(line, 'order_id', False)
            if order:
                pr_name = getattr(order, 'requisition_order', False) or getattr(order, 'pr_number', False)
                if pr_name:
                    pr = self.env['employee.purchase.requisition'].sudo().search(
                        [('name', '=', pr_name)], limit=1)
                    if pr:
                        pr_dept = pr.dept_id or getattr(pr, 'department_id', False)
                        if pr_dept:
                            dept_id = pr_dept

        # -----------------------------------------------------------
        # Priority 3: Line-level department_id
        # -----------------------------------------------------------
        if not dept_id:
            dept_id = getattr(line, 'department_id', False)

        # -----------------------------------------------------------
        # Priority 4: Header-level fallback
        # -----------------------------------------------------------
        # Identify header to pull fallback department/analytic info.
        order = (
            getattr(line, 'order_id', False)
            or getattr(line, 'requisition_id', False)
            or getattr(line, 'material_requisition_id', False)
            or getattr(line, 'requisition_product_id', False)
        )

        if not order:
            # Bill line → linked PO via purchase_line_id
            po_line = getattr(line, 'purchase_line_id', False)
            if po_line:
                order = getattr(po_line, 'order_id', False)

        if not order:
            # Last resort: the parent document itself (e.g., the bill header)
            order = getattr(line, 'move_id', False)

        if order:
            if not acc_id:
                acc_id = getattr(order, 'analytic_account_id', False) or getattr(order, 'expense_code_id', False)
            if not dept_id:
                dept_id = getattr(order, 'department_id', False) or getattr(order, 'dept_id', False)

        # Budgets are mapped 100% strictly to the line's department, ignoring analytic splits.
        res.append({
            'analytic_account_id': acc_id.id if hasattr(acc_id, 'id') else (acc_id or False),
            'department_id': dept_id.id if hasattr(dept_id, 'id') else (dept_id or False),
            'percentage': 1.0
        })

        return res

    @api.model
    def action_release_aged_reservations(self):
        """Cron action: Find reserved moves exceeding the aging days limit and release them."""
        # Note: We can only release reservations by either deleting the move or creating an offsetting move.
        # Deleting the move is cleaner and aligns with '_clear_budget_moves' behavior for resetting.
        # However, we only do this for purely aged PR/MR without linked POs? 
        # Actually simplest is just to unlink them entirely or add an offsetting minus move.
        moves = self.search([('move_type', '=', 'reserved')])
        for move in moves:
            limit = move._get_aging_limit()
            if limit and move.aging_days > limit:
                _logger.info(f"Releasing aged reservation {move.id} for {move.name}")
                move.unlink()

    def _get_aging_limit(self):
        """Helper to get company limit, fall back to default"""
        if self.company_id and hasattr(self.company_id, 'budget_aging_days_limit'):
            return self.company_id.budget_aging_days_limit
        return 30
