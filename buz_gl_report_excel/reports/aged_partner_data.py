from odoo import api, models, fields, _
from odoo.exceptions import UserError

class ReportAgedPartner(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_partner'
    _description = 'Aged Partner Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form', {}) or {}
        
        date_from = form_data.get('date_from') or data.get('date_from')
        date_to = form_data.get('date_to') or data.get('date_to')
        result_selection = form_data.get('result_selection') or data.get('result_selection', 'customer')
        direction_selection = form_data.get('direction_selection') or data.get('direction_selection', 'past')
        period_length = form_data.get('period_length', 30) or data.get('period_length', 30)
        target_move = form_data.get('target_move') or data.get('target_move', 'posted')
        show_uncleared_items = form_data.get('show_uncleared_items', True)
        partner_ids = form_data.get('partner_ids') or data.get('partner_ids')
        account_ids = form_data.get('account_ids') or data.get('account_ids')
        journal_ids = form_data.get('journal_ids') or data.get('journal_ids')

        move_state = {'posted': ['posted'], 'all': ['draft', 'posted']}[target_move]

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        partners = self.env['res.partner'].browse(partner_ids) if partner_ids else self.env['res.partner'].search([])
        accounts = self.env['account.account'].browse(account_ids) if account_ids else []

        domain = []
        if result_selection == 'customer':
            account_types = ['asset_receivable']
            domain.append(('account_type', 'in', account_types))
        elif result_selection == 'supplier':
            account_types = ['liability_payable']
            domain.append(('account_type', 'in', account_types))
        elif result_selection == 'customer_supplier':
            domain.append(('account_type', 'in', ['asset_receivable', 'liability_payable']))

        if accounts:
            domain.append(('account_id', 'in', accounts.ids))

        if direction_selection == 'past':
            domain.append(('date', '<=', date_to))
        else:
            domain.append(('date', '>=', date_from))
            domain.append(('date', '<=', date_to))

        if show_uncleared_items:
            domain.append(('reconciled', '=', False))

        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))

        if journal_ids:
            domain.append(('journal_id', 'in', journal_ids))

        move_lines = self.env['account.move.line'].search(domain)

        partners_data = {}
        for partner in partners:
            partners_data[partner.id] = {
                'partner': partner,
                'partner_name': partner.name,
                'periods': {},
                'total': 0.0
            }

        for line in move_lines:
            partner_id = line.partner_id.id if line.partner_id else None
            if not partner_id or partner_id not in partners_data:
                continue

            if direction_selection == 'past':
                date_diff = (date_to - line.date).days
                period_num = int(date_diff // period_length) if date_diff >= 0 else 0
                period_key = f"{period_num * period_length + 1}-{(period_num + 1) * period_length}"
            else:
                date_diff = (line.date - date_from).days
                period_num = int(date_diff // period_length) if date_diff >= 0 else 0
                period_key = f"{period_num * period_length + 1}-{(period_num + 1) * period_length}"

            if period_key not in partners_data[partner_id]['periods']:
                partners_data[partner_id]['periods'][period_key] = 0.0

            amount = line.amount_residual if result_selection == 'customer' else -line.amount_residual
            partners_data[partner_id]['periods'][period_key] += amount
            partners_data[partner_id]['total'] += amount

        sorted_partners = []
        for partner_id, data in partners_data.items():
            if data['total'] != 0:
                sorted_partners.append(data)

        sorted_partners.sort(key=lambda x: x['partner_name'])

        return {
            'doc_ids': docids,
            'doc_model': 'aged.partner.wizard',
            'data': form_data,
            'docs': self.env['aged.partner.wizard'].browse(docids),
            'partners': sorted_partners,
            'date_from': date_from,
            'date_to': date_to,
            'period_length': period_length,
            'direction_selection': direction_selection,
            'result_selection': result_selection,
        }
