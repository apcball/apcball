from odoo import api, models, fields, _
from odoo.tools import float_is_zero

class AgedReceivableReport(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_aged_receivable'
    _description = 'Aged Receivable Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        form_data = data.get('form', {}) or {}
        
        date_as_of = form_data.get('date_as_of')
        company_id = form_data.get('company_id')
        if company_id:
            company_id = company_id[0] if isinstance(company_id, (list, tuple)) else company_id
        else:
            company_id = self.env.company.id
            
        direction_selection = form_data.get('direction_selection', 'past')
        period_length = form_data.get('period_length', 30)
        target_move = form_data.get('target_move', 'posted')
        partner_ids = form_data.get('partner_ids', [])
        account_ids = form_data.get('account_ids', [])
        journal_ids = form_data.get('journal_ids', [])
        result_selection = form_data.get('result_selection', 'customer')

        if isinstance(date_as_of, str):
            date_as_of = fields.Date.from_string(date_as_of)

        account_types = ['asset_receivable']

        query = """
            SELECT
                l.id AS line_id,
                l.partner_id,
                p.name AS partner_name,
                l.move_name AS move_name,
                l.date AS date,
                l.date_maturity AS date_maturity,
                l.currency_id,
                c.name AS currency_name,
                l.amount_currency AS original_amount_currency,
                l.balance AS original_amount,
                (l.balance 
                 - COALESCE((SELECT SUM(amount) FROM account_partial_reconcile pr WHERE pr.debit_move_id = l.id AND pr.max_date <= %s), 0.0)
                 + COALESCE((SELECT SUM(amount) FROM account_partial_reconcile pr WHERE pr.credit_move_id = l.id AND pr.max_date <= %s), 0.0)
                ) AS residual_amount,
                (l.amount_currency 
                 - COALESCE((SELECT SUM(debit_amount_currency) FROM account_partial_reconcile pr WHERE pr.debit_move_id = l.id AND pr.max_date <= %s), 0.0)
                 + COALESCE((SELECT SUM(credit_amount_currency) FROM account_partial_reconcile pr WHERE pr.credit_move_id = l.id AND pr.max_date <= %s), 0.0)
                ) AS residual_amount_currency
            FROM account_move_line l
            LEFT JOIN res_partner p ON l.partner_id = p.id
            LEFT JOIN res_currency c ON l.currency_id = c.id
            JOIN account_account a ON l.account_id = a.id
            JOIN account_move m ON l.move_id = m.id
            WHERE l.date <= %s AND a.account_type IN %s AND l.company_id = %s
        """
        
        params = [date_as_of, date_as_of, date_as_of, date_as_of, date_as_of, tuple(account_types), company_id]
        
        if account_ids:
            query += " AND l.account_id IN %s"
            params.append(tuple(account_ids))
        if partner_ids:
            query += " AND l.partner_id IN %s"
            params.append(tuple(partner_ids))
        if journal_ids:
            query += " AND l.journal_id IN %s"
            params.append(tuple(journal_ids))
        if target_move == 'posted':
            query += " AND m.state = 'posted'"
            
        self.env.cr.execute(query, params)
        lines = self.env.cr.dictfetchall()

        partners_data = {}
        
        # Mapping for result_selection (sign logic: positive means we are owed, negative means we owe)
        # Receivable: Assets -> Debit > 0 means residual is positive
        # Payable: Liabilities -> Credit > 0 means residual is negative 
        # Standard: Show absolute amounts or always positive for aging.
        # We will flip the sign for payable so it shows as a positive balance.
        sign = 1 if 'receivable' in account_types[0] else -1
        # For customer_supplier, we can just flip payable ones.

        company = self.env['res.company'].browse(company_id)
        currency_dp = company.currency_id.decimal_places

        for line in lines:
            if float_is_zero(line['residual_amount'], precision_digits=currency_dp):
                continue
                
            partner_id = line['partner_id'] or False
            partner_name = line['partner_name'] or 'Unknown Partner'
            
            if partner_id not in partners_data:
                partners_data[partner_id] = {
                    'partner_name': partner_name,
                    'total': 0.0,
                    'periods': {
                        'Not Due': 0.0,
                        '1-30': 0.0,
                        '31-60': 0.0,
                        '61-90': 0.0,
                        '91-120': 0.0,
                        '120+': 0.0
                    },
                    'lines': []
                }
                
            # Flip sign if it's a payable account
            # But wait, we filtered by account_types. If it's pure payable, sign is -1.
            # If customer_supplier, we need to check the exact line type.
            # Let's verify by just looking at original amount sign if needed, but easier is: if residual is negative and we're looking at payables.
            line_sign = 1

            residual_amount = line['residual_amount'] * line_sign
            
            # Bucketing logic based on maturity date vs as of date
            due_date = line['date_maturity'] or line['date']
            
            if direction_selection == 'past':
                # Past aging (Standard): As of date - Due date (How late is it?)
                diff = (date_as_of - due_date).days
            else:
                # Future aging: Due date - As of date (How soon is it due?)
                diff = (due_date - date_as_of).days
                
            if diff <= 0:
                bucket = 'Not Due'
            elif diff <= period_length:
                bucket = '1-30'
            elif diff <= period_length * 2:
                bucket = '31-60'
            elif diff <= period_length * 3:
                bucket = '61-90'
            elif diff <= period_length * 4:
                bucket = '91-120'
            else:
                bucket = '120+'

            partners_data[partner_id]['periods'][bucket] += residual_amount
            partners_data[partner_id]['total'] += residual_amount
            
            partners_data[partner_id]['lines'].append({
                'move_name': line['move_name'],
                'date': line['date'],
                'date_maturity': due_date,
                'currency_name': line['currency_name'],
                'original_amount_currency': line['original_amount_currency'],
                'residual_amount_currency': line['residual_amount_currency'],
                'residual_amount': residual_amount,
                'bucket': bucket
            })

        # Sort partners by name
        sorted_partners = list(partners_data.values())
        sorted_partners.sort(key=lambda x: x['partner_name'])
        
        # Sort lines inside partner
        for p in sorted_partners:
            p['lines'].sort(key=lambda x: x['date'] or fields.Date.context_today(self))

        return {
            'doc_ids': docids,
            'doc_model': form_data.get('model', 'ir.ui.menu'),
            'data': form_data,
            'partners': sorted_partners,
            'date_as_of': date_as_of.strftime('%Y-%m-%d'),
            'period_length': period_length,
            'direction_selection': direction_selection,
            'result_selection': result_selection,
            'company_id': company_id,
        }
