# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TrialBalanceWizard(models.TransientModel):
    _name = 'account.trial.balance.wizard'
    _description = 'Trial Balance Wizard'

    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company,
    )
    target_move = fields.Selection([
        ('posted', 'Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', required=True, default='posted')
    journal_ids = fields.Many2many(
        'account.journal', string='Journals',
        domain="[('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search([('company_id', '=', self.env.company.id)]),
    )

    # ------------------------------------------------------------------
    # TRIAL BALANCE COMPUTATION
    # ------------------------------------------------------------------
    def _get_analytic_grouping_keys(self):
        """Override to add analytic dimension grouping."""
        return []

    def _query_where(self):
        """Build WHERE clause parts and params."""
        where = ["aml.company_id = %s", "aml.date >= %s", "aml.date <= %s"]
        params = [self.company_id.id, self.date_from, self.date_to]

        if self.target_move == 'posted':
            where.append("m.state = 'posted'")

        if self.journal_ids:
            placeholders = ', '.join(['%s'] * len(self.journal_ids.ids))
            where.append("aml.journal_id IN (%s)" % placeholders)
            params.extend(self.journal_ids.ids)

        return ' AND '.join(where), params

    def _query_select(self):
        """Build SELECT and GROUP BY for account-level aggregation."""
        return """
            aml.account_id            AS account_id,
            SUM(aml.debit)            AS debit,
            SUM(aml.credit)           AS credit,
            SUM(aml.balance)          AS balance
        """, """
            GROUP BY aml.account_id
        """

    def _query_from(self):
        return """
            FROM account_move_line aml
            JOIN account_move m ON m.id = aml.move_id
        """

    def _fetch_trial_balance(self):
        """Return raw aggregated rows from account_move_line."""
        where_clause, params = self._query_where()
        select_clause, group_clause = self._query_select()
        from_clause = self._query_from()
        sql = """
            SELECT %(select)s
            %(from)s
            WHERE %(where)s
            %(group)s
            ORDER BY aml.account_id
        """ % {
            'select': select_clause,
            'from': from_clause,
            'where': where_clause,
            'group': group_clause,
        }
        self.env.cr.execute(sql, params)
        return self.env.cr.dictfetchall()

    def _classify_accounts(self, account_ids):
        """Return a mapping {account_id: {'type': ..., 'type_seq': ..., 'code': ..., 'name': ...}}."""
        accounts = self.env['account.account'].sudo().browse(account_ids)
        selection = dict(self.env['account.account']._fields['account_type']._description_selection(self.env))
        res = {}
        for ac in accounts:
            t_code = ac.account_type
            res[ac.id] = {
                'code': ac.code,
                'name': ac.name,
                'type': selection.get(t_code, t_code) or 'Uncategorized',
                'type_seq': t_code or 'z',
            }
        return res

    def _get_trial_balance_data(self):
        """Compute full trial balance data grouped by account type."""
        rows = self._fetch_trial_balance()
        if not rows:
            return {'lines': [], 'group_totals': [], 'grand_total': {}}

        account_ids = [r['account_id'] for r in rows if r['account_id']]
        account_info = self._classify_accounts(account_ids)

        # Build lines with account metadata
        lines = []
        for r in rows:
            aid = r['account_id']
            info = account_info.get(aid, {})
            lines.append({
                'code': info.get('code') or '',
                'name': info.get('name', ''),
                'type': info.get('type', 'Uncategorized'),
                'type_seq': info.get('type_seq') or 'zzz',
                'debit': r['debit'] or 0.0,
                'credit': r['credit'] or 0.0,
                'balance': r['balance'] or 0.0,
            })

        # Sort by account type sequence, then code
        lines.sort(key=lambda l: (str(l['type_seq']), str(l['code'])))

        # Group by type
        grouped = []
        current_type = None
        group_total = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}
        type_lines = []
        group_totals = []

        for line in lines:
            if line['type'] != current_type:
                if current_type is not None:
                    grouped.append({
                        'type': current_type,
                        'lines': type_lines,
                        'total_debit': group_total['debit'],
                        'total_credit': group_total['credit'],
                        'total_balance': group_total['balance'],
                    })
                    group_totals.append({
                        'type': current_type,
                        'debit': group_total['debit'],
                        'credit': group_total['credit'],
                        'balance': group_total['balance'],
                    })
                current_type = line['type']
                type_lines = []
                group_total = {'debit': 0.0, 'credit': 0.0, 'balance': 0.0}

            type_lines.append(line)
            group_total['debit'] += line['debit']
            group_total['credit'] += line['credit']
            group_total['balance'] += line['balance']

        # Last group
        if current_type is not None:
            grouped.append({
                'type': current_type,
                'lines': type_lines,
                'total_debit': group_total['debit'],
                'total_credit': group_total['credit'],
                'total_balance': group_total['balance'],
            })
            group_totals.append({
                'type': current_type,
                'debit': group_total['debit'],
                'credit': group_total['credit'],
                'balance': group_total['balance'],
            })

        grand_debit = sum(t['debit'] for t in group_totals)
        grand_credit = sum(t['credit'] for t in group_totals)
        grand_balance = sum(t['balance'] for t in group_totals)

        return {
            'lines': grouped,
            'group_totals': group_totals,
            'grand_total': {
                'debit': grand_debit,
                'credit': grand_credit,
                'balance': grand_balance,
            },
        }

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------
    def _build_context_data(self):
        """Build data dict for report."""
        return {
            'ids': self.ids,
            'model': self._name,
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'target_move': self.target_move,
            'journal_ids': self.journal_ids.ids if self.journal_ids else [],
        }

    def action_print_pdf(self):
        data = self._build_context_data()
        return self.env.ref(
            'account_trial_balance.action_report_trial_balance'
        ).report_action(self, data=data)

    def action_export_xlsx(self):
        return {
            'type': 'ir.actions.act_url',
            'url': '/account_trial_balance/xlsx/%s' % self.id,
            'target': 'self',
        }
