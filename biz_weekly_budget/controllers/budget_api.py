# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class BudgetAPI(http.Controller):

    @http.route('/budget/api/matrix', type='json', auth='user')
    def get_budget_matrix(self, plan_id):
        # We assume plan_id is the Monthly plan here as the UI will pass the monthly plan IDs.
        plan = request.env['monthly.budget.plan'].browse(plan_id)
        if not plan.exists():
            return {'error': 'Plan not found'}

        lines = request.env['monthly.budget.allocation'].search([('plan_id', '=', plan_id)])
        
        column_key = plan.date_from.strftime('%Y-%m-%d') if plan.date_from else 'empty'
        weeks = {
            column_key: {
                'key': column_key,
                'label': plan.name,
                'date_from': plan.date_from.strftime('%Y-%m-%d') if plan.date_from else '',
                'date_to': plan.date_to.strftime('%Y-%m-%d') if plan.date_to else ''
            }
        }
        sorted_weeks = [weeks[column_key]]

        rows_dict = {}
        for line in lines:
            dept_id = line.department_id.id if line.department_id else 0
            row_key = f"{dept_id}"
            
            if row_key not in rows_dict:
                dept_name = line.department_id.sudo().name if line.department_id else 'Base / General'
                rows_dict[row_key] = {
                    'key': row_key,
                    'department_id': dept_id,
                    'label': dept_name,
                    'cells': {}
                }
                
            rows_dict[row_key]['cells'][column_key] = {
                'line_id': line.id,
                'limit': line.amount,
                'forecast': line.forecast_amount,
                'used': line.amount_used,
                'reserved': line.amount_reserved,
                'available': line.amount_available
            }

        return {
            'weeks': sorted_weeks,
            'rows': list(rows_dict.values())
        }

    @http.route('/budget/api/update_cell', type='json', auth='user')
    def update_budget_cell(self, line_id, amount_limit=None, forecast_amount=None):
        line = request.env['monthly.budget.allocation'].browse(line_id)
        if line.exists():
            if forecast_amount is not None:
                request.env['budget.move'].search([
                    ('allocation_id', '=', line.id),
                    ('move_type', '=', 'forecast')
                ]).unlink()
                if float(forecast_amount) > 0:
                    request.env['budget.move'].create({
                        'name': 'Manual Forecast',
                        'allocation_id': line.id,
                        'source_model': 'monthly.budget.allocation',
                        'source_id': line.id,
                        'department_id': line.department_id.id,
                        'amount': float(forecast_amount),
                        'move_type': 'forecast',
                        'date': line.date_to or fields.Date.today()
                    })
            return {'status': 'success'}
        return {'error': 'Line not found'}

    @http.route('/budget/api/dashboard_data', type='json', auth='user')
    def get_dashboard_data(self, selectedPlanId=None, selectedYear=None, selectedMonth=None, **kwargs):
        domain = [('plan_state', '=', 'confirmed')]
        
        if selectedPlanId and selectedPlanId != 'all':
            domain.append(('plan_id', '=', int(selectedPlanId)))
            
        BudgetAllocation = request.env['monthly.budget.allocation'].sudo()
        lines = BudgetAllocation.search(domain, order='date_from asc')
        
        if selectedYear and selectedYear != 'all':
            lines = lines.filtered(lambda l: l.date_from and str(l.date_from.year) == str(selectedYear))
        if selectedMonth and selectedMonth != 'all':
            lines = lines.filtered(lambda l: l.date_from and str(l.date_from.month) == str(selectedMonth))
                
        # 1. SUMMARY
        summary = {
            'total_budget': sum(lines.mapped('amount')),
            'total_used': sum(lines.mapped('amount_used')),
            'total_reserved': sum(lines.mapped('amount_reserved')),
            'forecast': sum(lines.mapped('forecast_amount')),
        }
        total_used = summary['total_used']
        total_reserved = summary['total_reserved']
        
        summary['remaining'] = summary['total_budget'] - total_used - summary['total_reserved'] - summary['forecast']
        summary['utilization'] = ((total_used + total_reserved) / summary['total_budget'] * 100) if summary['total_budget'] else 0

        # 2. PIE CHART (Budget Health)
        available = max(0, summary['total_budget'] - total_used - total_reserved)
        pie_data = {
            'labels': ['Used', 'Reserved', 'Available'],
            'values': [total_used, total_reserved, available]
        }

        # 3. WEEKS DATA (For Line Chart)
        months_dict = {}
        for line in lines:
            w_label = line.plan_id.name if line.plan_id else "Unknown"
            if w_label not in months_dict:
                months_dict[w_label] = {'name': w_label, 'budget': 0, 'actual': 0, 'reserved': 0, 'forecast': 0, 'date_from': line.date_from}
            months_dict[w_label]['budget'] += line.amount
            months_dict[w_label]['actual'] += line.amount_used
            months_dict[w_label]['reserved'] += line.amount_reserved
            months_dict[w_label]['forecast'] += line.forecast_amount
        
        sorted_weeks = sorted(months_dict.values(), key=lambda w: w['date_from'] or '')

        # 4. DEPARTMENT DATA (For Bar Chart)
        dept_dict = {}
        for line in lines:
            d_label = line.department_id.name if line.department_id else 'General'
            if d_label not in dept_dict:
                dept_dict[d_label] = {'name': d_label, 'limit': 0, 'used': 0, 'reserved': 0, 'forecast': 0}
            dept_dict[d_label]['limit'] += line.amount
            dept_dict[d_label]['used'] += line.amount_used
            dept_dict[d_label]['reserved'] += line.amount_reserved
            dept_dict[d_label]['forecast'] += line.forecast_amount

        return {
            'summary': summary,
            'weeks': [
                {
                    'name': w['name'],
                    'budget': w['budget'],
                    'actual': w['actual'],
                    'reserved': w['reserved'],
                    'forecast': w['forecast']
                } for w in sorted_weeks
            ],
            'departments': list(dept_dict.values()),
            'pie_data': pie_data
        }
