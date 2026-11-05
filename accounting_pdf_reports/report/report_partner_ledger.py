import time

from odoo import api, models, _
from odoo.exceptions import UserError


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_partnerledger'
    _description = 'Partner Ledger Report'

    def _lines(self, data, partner):
        full_account = []
        currency = self.env['res.currency']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        params = [partner.id, tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        query = """
            SELECT "account_move_line".id, "account_move_line".date, j.code, acc.code as a_code, acc.name as a_name, "account_move_line".ref, m.name as move_name, "account_move_line".name, "account_move_line".debit, "account_move_line".credit, "account_move_line".amount_currency,"account_move_line".currency_id, c.symbol AS currency_code
            FROM """ + query_get_data[0] + """
            LEFT JOIN account_journal j ON ("account_move_line".journal_id = j.id)
            LEFT JOIN account_account acc ON ("account_move_line".account_id = acc.id)
            LEFT JOIN res_currency c ON ("account_move_line".currency_id=c.id)
            LEFT JOIN account_move m ON (m.id="account_move_line".move_id)
            WHERE "account_move_line".partner_id = %s
                AND m.state IN %s
                AND "account_move_line".account_id IN %s AND """ + query_get_data[1] + reconcile_clause + """
                ORDER BY "account_move_line".date"""
        self.env.cr.execute(query, tuple(params))
        res = self.env.cr.dictfetchall()
        sum = 0.0
        lang_code = self.env.context.get('lang') or 'en_US'
        lang = self.env['res.lang']
        lang_id = lang._lang_get(lang_code)
        date_format = lang_id.date_format
        for r in res:
            r['date'] = r['date']
            r['displayed_name'] = '-'.join(
                r[field_name] for field_name in ('move_name', 'ref', 'name')
                if r[field_name] not in (None, '', '/')
            )
            sum += r['debit'] - r['credit']
            r['progress'] = sum
            r['currency_id'] = currency.browse(r.get('currency_id'))
            full_account.append(r)
        return full_account

    def _sum_partner(self, data, partner, field):
        if field not in ['debit', 'credit', 'debit - credit']:
            return
        result = 0.0
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '

        params = [partner.id, tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        query = """SELECT sum(""" + field + """)
                FROM """ + query_get_data[0] + """, account_move AS m
                WHERE "account_move_line".partner_id = %s
                    AND m.id = "account_move_line".move_id
                    AND m.state IN %s
                    AND account_id IN %s
                    AND """ + query_get_data[1] + reconcile_clause
        self.env.cr.execute(query, tuple(params))

        contemp = self.env.cr.fetchone()
        if contemp is not None:
            result = contemp[0] or 0.0
        return result

    def _get_bill_payment_details(self, bills, account_ids, form):
        result = {}
        date_from = form.get('date_from') or ''
        date_to = form.get('date_to') or ''
        journal_ids = set(form.get('journal_ids') or [])
        for bill in bills:
            bill_lines = bill.line_ids.filtered(
                lambda line: line.account_id.id in account_ids and line.partner_id
            )
            partials = bill_lines.mapped('matched_debit_ids') | bill_lines.mapped('matched_credit_ids')
            payment_events = {}
            other_events = []

            for partial in partials:
                if partial.debit_move_id.move_id == bill:
                    counterpart = partial.credit_move_id
                    bill_currency_amount = partial.debit_amount_currency
                elif partial.credit_move_id.move_id == bill:
                    counterpart = partial.debit_move_id
                    bill_currency_amount = partial.credit_amount_currency
                else:
                    continue

                # shortcut: direct statement reconciliations lack an account.payment number; add explicit statement-reference support if required.
                payment = counterpart.move_id.payment_id
                event = {
                    'date': payment.date if payment else partial.max_date,
                    'id': partial.id,
                    'amount': partial.amount,
                    'amount_currency': bill_currency_amount,
                    'payment': payment,
                    'journal_id': (payment.move_id.journal_id.id if payment else counterpart.journal_id.id),
                }
                if payment:
                    grouped = payment_events.setdefault(payment.id, {
                        'date': payment.date,
                        'id': partial.id,
                        'amount': 0.0,
                        'amount_currency': 0.0,
                        'payment': payment,
                        'journal_id': event['journal_id'],
                    })
                    grouped['id'] = min(grouped['id'], partial.id)
                    grouped['amount'] += event['amount']
                    grouped['amount_currency'] += event['amount_currency']
                else:
                    other_events.append(event)

            company_currency = bill.company_id.currency_id
            bill_currency = bill.currency_id or company_currency
            remaining = sum(-line.balance for line in bill_lines)
            remaining_currency = sum(-line.amount_currency for line in bill_lines)
            payment_rows = []
            events = other_events + list(payment_events.values())
            for event in sorted(events, key=lambda item: (str(item['date'] or ''), item['id'])):
                event_date = str(event['date'] or '')
                if date_from and event_date and event_date < date_from:
                    remaining = company_currency.round(remaining - event['amount'])
                    remaining_currency = bill_currency.round(
                        remaining_currency - event['amount_currency']
                    )
                    continue
                if date_to and event_date and event_date > date_to:
                    continue
                remaining = company_currency.round(remaining - event['amount'])
                remaining_currency = bill_currency.round(
                    remaining_currency - event['amount_currency']
                )
                if not journal_ids or event['journal_id'] in journal_ids:
                    payment = event['payment']
                    payment_rows.append({
                        'payment_number': payment.name if payment else None,
                        'payment_date': event['date'],
                        'paid_amount': event['amount'],
                        'remaining': remaining,
                        'paid_amount_currency': event['amount_currency'],
                        'remaining_currency': remaining_currency,
                        'currency': bill_currency,
                    })

            result[bill.id] = {
                'payments': payment_rows,
                'remaining': (
                    remaining if date_to else sum(-line.amount_residual for line in bill_lines)
                ),
                'remaining_currency': (
                    remaining_currency if date_to else
                    sum(-line.amount_residual_currency for line in bill_lines)
                ),
            }
        return result

    def _lines_with_payment_details(self, data, partner):
        lines = self._lines(data, partner)
        move_lines = self.env['account.move.line'].browse(
            [line['id'] for line in lines]
        )
        move_line_by_id = {line.id: line for line in move_lines}
        bills = move_lines.mapped('move_id').filtered(
            lambda move: move.move_type == 'in_invoice'
        )
        payment_details = self._get_bill_payment_details(
            bills, set(data['computed']['account_ids']), data['form'],
        )

        report_lines = []
        written_bills = set()
        for line in lines:
            move = move_line_by_id[line['id']].move_id
            bill = move if move.move_type == 'in_invoice' else False
            if not bill or bill.id in written_bills:
                report_lines.append({
                    **line,
                    'payment_detail': None,
                    'show_accounting_values': True,
                })
                continue

            written_bills.add(bill.id)
            bill_details = payment_details[bill.id]
            payment_rows = bill_details['payments'] or [{
                'payment_number': None,
                'payment_date': None,
                'paid_amount': None,
                'remaining': bill_details['remaining'],
                'paid_amount_currency': None,
                'remaining_currency': bill_details['remaining_currency'],
                'currency': bill.currency_id,
            }]
            for index, payment_detail in enumerate(payment_rows):
                report_line = dict(line)
                if index:
                    report_line.update({
                        'date': None,
                        'code': None,
                        'a_code': None,
                        'displayed_name': bill.name,
                        'debit': None,
                        'credit': None,
                        'progress': None,
                        'amount_currency': None,
                    })
                report_line.update({
                    'payment_detail': payment_detail,
                    'show_accounting_values': not index,
                })
                report_lines.append(report_line)
        return report_lines

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        data['computed'] = {}

        obj_partner = self.env['res.partner']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        data['computed']['move_state'] = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            data['computed']['move_state'] = ['posted']
        result_selection = data['form'].get('result_selection', 'customer')
        if result_selection == 'supplier':
            data['computed']['ACCOUNT_TYPE'] = ['liability_payable']
        elif result_selection == 'customer':
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable']
        else:
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable', 'liability_payable']

        self.env.cr.execute("""
            SELECT a.id
            FROM account_account a
            WHERE a.account_type IN %s
            AND NOT a.deprecated""", (tuple(data['computed']['ACCOUNT_TYPE']),))
        data['computed']['account_ids'] = [a for (a,) in self.env.cr.fetchall()]
        params = [tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        query = """
            SELECT DISTINCT "account_move_line".partner_id
            FROM """ + query_get_data[0] + """, account_account AS account, account_move AS am
            WHERE "account_move_line".partner_id IS NOT NULL
                AND "account_move_line".account_id = account.id
                AND am.id = "account_move_line".move_id
                AND am.state IN %s
                AND "account_move_line".account_id IN %s
                AND NOT account.deprecated
                AND """ + query_get_data[1] + reconcile_clause
        self.env.cr.execute(query, tuple(params))
        if data['form']['partner_ids']:
            partner_ids = data['form']['partner_ids']
        else:
            partner_ids = [res['partner_id'] for res in
                           self.env.cr.dictfetchall()]
        partners = obj_partner.browse(partner_ids)
        partners = sorted(partners, key=lambda x: (x.ref or '', x.name or ''))

        return {
            'doc_ids': partner_ids,
            'doc_model': self.env['res.partner'],
            'data': data,
            'docs': partners,
            'time': time,
            'lines': self._lines,
            'lines_with_payment_details': self._lines_with_payment_details,
            'sum_partner': self._sum_partner,
        }
