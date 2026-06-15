from odoo import api, models, fields, _
from odoo.tools import format_date

class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.buz_gl_report_excel.report_general_ledger'
    _description = 'General Ledger Report'

    def _get_initial_balances(self, accounts, date_from, target_move, company_id):
        cr = self.env.cr
        init_balances = {}
        
        if not date_from:
            return init_balances

        # state_cond = "AND m.state = 'posted'" if target_move == 'posted' else ""
        
        if not accounts:
            return {}
            
        # Build domain for initial balance
        domain = [('account_id', 'in', accounts.ids), ('date', '<', date_from), ('company_id', '=', company_id)]
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        else:
             # In v17, 'state' on directly move_line? 
             # Standard is move_id.state. recent versions use parent_state on line used for performance
             # or we join. 'parent_state' field exists on account.move.line in v17.
             pass

        # Use _where_calc for cleaner query generation compatible with v17
        query = self.env['account.move.line']._where_calc(domain)
        from_clause, where_clause, where_params = query.get_sql()

        sql = """
            SELECT account_move_line.account_id, 
                   SUM(account_move_line.debit) AS debit, 
                   SUM(account_move_line.credit) AS credit, 
                   SUM(account_move_line.balance) AS balance
            FROM """ + from_clause + """
            WHERE """ + where_clause + """
            GROUP BY account_move_line.account_id
        """
        
        cr.execute(sql, where_params)
        
        for row in cr.dictfetchall():
            init_balances[row['account_id']] = {
                'debit': row['debit'],
                'credit': row['credit'],
                'balance': row['balance']
            }
        return init_balances

    def _get_account_move_entry(self, accounts, date_from, date_to, target_move, sortby, company_id):
        cr = self.env.cr
        move_lines = {}
        
        if not accounts:
            return {}

        # Build Domain based on input
        domain = [('account_id', 'in', accounts.ids), ('company_id', '=', company_id)]
        if date_from:
            domain.append(('date', '>=', date_from))
        if date_to:
            domain.append(('date', '<=', date_to))
        
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))

        # Use _where_calc
        query = self.env['account.move.line']._where_calc(domain)
        from_clause, where_clause, where_params = query.get_sql()

        # Sort
        # default sort
        order_by = 'account_move_line.date, account_move_line.move_id'
        if sortby == 'sort_journal_partner':
            # We need to ensure joins if we sort by joined fields.
            # _where_calc handles the main table.
            # We might need manual joins for ordering if they aren't in the from_clause
            # But usually we can join manually in the query string if needed, 
            # Or safer: just select the IDs and let ORM read? No, high volume requirement.
            
            # Simple approach: Left join in the main query text for sorting fields
            order_by = 'j.code, p.name, account_move_line.move_id'

        sql = ('''
            SELECT account_move_line.account_id, account_move_line.date, 
            j.code AS journal_code, p.name AS partner_name, 
            account_move_line.ref, m.name AS move_name, account_move_line.name AS entry_label,
            account_move_line.debit, account_move_line.credit, account_move_line.balance,
            account_move_line.amount_currency, c.symbol AS currency_symbol,
            NULL AS analytic_account
            FROM ''' + from_clause + '''
            JOIN account_move m ON (account_move_line.move_id=m.id)
            LEFT JOIN res_currency c ON (account_move_line.currency_id=c.id)
            LEFT JOIN res_partner p ON (account_move_line.partner_id=p.id)
            LEFT JOIN account_journal j ON (account_move_line.journal_id=j.id)
            WHERE ''' + where_clause + '''
            ORDER BY ''' + order_by)
        
        cr.execute(sql, where_params)

        for row in cr.dictfetchall():
            acc_id = row['account_id']
            if acc_id not in move_lines:
                move_lines[acc_id] = []
            move_lines[acc_id].append(row)

        return move_lines

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
             raise UserError(_("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))
        
        form_data = data['form']
        date_from = form_data.get('date_from')
        date_to = form_data.get('date_to')
        target_move = form_data.get('target_move')
        sortby = form_data.get('sortby')
        display_account = form_data.get('display_account')
        init_balance = form_data.get('initial_balance')
        journal_ids = form_data.get('journal_ids')
        account_ids = form_data.get('account_ids')

        company_id = form_data.get('company_id')
        if company_id:
            company_id = company_id[0] if isinstance(company_id, (list, tuple)) else company_id
        else:
            company_id = self.env.company.id

        domain = []
        if account_ids:
            domain.append(('id', 'in', account_ids))
        
        accounts = self.env['account.account'].search(domain)

        # Get Moves
        move_lines = self._get_account_move_entry(accounts, date_from, date_to, target_move, sortby, company_id)
        
        # Get Initial Balances
        init_balances = {}
        if init_balance:
            init_balances = self._get_initial_balances(accounts, date_from, target_move, company_id)

        final_accounts = []
        
        # Identify relevant account IDs
        relevant_ids = set()
        if display_account == 'all':
            relevant_ids = set(accounts.ids)
        else:
            if display_account == 'movement':
                 relevant_ids.update(move_lines.keys())
            
            if display_account == 'not_zero':
                 relevant_ids.update(move_lines.keys())
                 relevant_ids.update(init_balances.keys()) # rough check

        for account in accounts:
            if display_account != 'all' and account.id not in relevant_ids:
                continue

            lines = move_lines.get(account.id, [])
            bal_data = init_balances.get(account.id, {'debit':0,'credit':0,'balance':0})
            
            balance = 0.0
            if init_balance:
                balance = bal_data['balance']
            
            # Double check display logic
            if display_account == 'movement' and not lines:
                continue
            
            current_balance = balance + sum(l['balance'] for l in lines)
            
            if display_account == 'not_zero' and current_balance == 0:
                # Need to be careful: if it had movement but ended at 0?
                # Usually "balance not 0" filters out accounts that HAVE 0 balance at the end.
                continue

            # Standard Odoo 17 might favor fetching objects for qweb efficiency if fields are needed,
            # but we are using dicts for speed as per user request (implied "large amounts of data").
            
            final_accounts.append({
                'id': account.id,
                'code': account.code,
                'name': account.name,
                'init_balance': bal_data if init_balance else False,
                'lines': lines,
                'end_balance': current_balance
            })

        return {
            'doc_ids': docids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'accounts': final_accounts,
            'date_from': date_from,
            'date_to': date_to,
            'company_id': company_id,
        }
