from collections import defaultdict

from odoo import models
from odoo.osv import expression


class PartnerMovementXlsx(models.AbstractModel):
    _name = 'report.buz_partner_movement_excel.partner_movement_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Partner Movement Excel Report'

    @staticmethod
    def _signed_residual(balance, settled):
        return balance - settled if balance > 0 else balance + settled

    @staticmethod
    def _move_states(target_move):
        return ['draft', 'posted'] if target_move == 'all' else ['posted']

    @staticmethod
    def _account_types(direction):
        if direction == 'receivable':
            return ['asset_receivable']
        if direction == 'payable':
            return ['liability_payable', 'liability_current']
        return ['asset_receivable', 'liability_payable', 'liability_current']

    @staticmethod
    def _period_label(document_date, date_from):
        return 'Opening balance' if date_from and document_date < date_from else 'Period activity'

    def _amounts_as_of(self, lines, date_as_of):
        partials = self.env['account.partial.reconcile'].search([
            ('max_date', '<=', date_as_of),
            '|', ('debit_move_id', 'in', lines.ids), ('credit_move_id', 'in', lines.ids),
        ])
        settled = defaultdict(float)
        settled_currency = defaultdict(float)
        for partial in partials:
            settled[partial.debit_move_id.id] += partial.amount
            settled[partial.credit_move_id.id] += partial.amount
            settled_currency[partial.debit_move_id.id] += partial.debit_amount_currency
            settled_currency[partial.credit_move_id.id] += partial.credit_amount_currency
        company_residuals = {}
        currency_residuals = {}
        for line in lines:
            company_residuals[line.id] = self._signed_residual(line.balance, settled[line.id])
            currency_residuals[line.id] = line.amount_currency - settled_currency[line.id]
        return company_residuals, currency_residuals, partials

    def _document_rows(self, move, date_to, date_from):
        lines = move.line_ids.filtered(lambda line: line.account_id.account_type in (
            'asset_receivable', 'liability_payable',
        ))
        residuals, currency_residuals, partials = self._amounts_as_of(lines, date_to)
        settled = sum(abs(line.balance - residuals[line.id]) for line in lines)
        total = sum(abs(line.balance) for line in lines)
        residual = sum(abs(residuals[line.id]) for line in lines)
        foreign_total = sum(abs(line.amount_currency) for line in lines)
        foreign_settled = sum(abs(line.amount_currency - currency_residuals[line.id]) for line in lines)
        foreign_residual = sum(abs(currency_residuals[line.id]) for line in lines)
        payment_amount = 0.0
        adjustment_amount = 0.0
        payment_moves = self.env['account.payment'].search([('move_id', 'in', partials.mapped('debit_move_id.move_id').ids + partials.mapped('credit_move_id.move_id').ids)])
        payment_move_ids = set(payment_moves.mapped('move_id').ids)
        for partial in partials:
            if partial.debit_move_id.move_id == move:
                counterpart = partial.credit_move_id.move_id
            elif partial.credit_move_id.move_id == move:
                counterpart = partial.debit_move_id.move_id
            else:
                continue
            if counterpart.id in payment_move_ids or counterpart.payment_id:
                payment_amount += partial.amount
            else:
                adjustment_amount += partial.amount
        kind = dict(move._fields['move_type'].selection).get(move.move_type) or 'Journal Entry'
        rows = []
        seen = set()

        def append_links(source_move, depth=1):
            if depth > 4 or source_move.id in seen:
                return
            seen.add(source_move.id)
            source_lines = source_move.line_ids
            _, _, links = self._amounts_as_of(source_lines, date_to)
            for partial in links:
                debit, credit = partial.debit_move_id, partial.credit_move_id
                own = debit if debit.move_id == source_move else credit
                other = credit if own == debit else debit
                target = other.move_id
                if target == source_move or target.id in seen:
                    continue
                rows.append({
                    'depth': depth,
                    'type': dict(target._fields['move_type'].selection).get(target.move_type) or 'Journal Entry',
                    'number': target.name,
                    'date': target.date,
                    'document_total': target.amount_total_signed or max(
                        sum(target.line_ids.mapped('debit')), sum(target.line_ids.mapped('credit')),
                    ),
                    'allocated': partial.amount,
                    'currency': target.currency_id.name or target.company_id.currency_id.name,
                    'warning': 'Bill allocation unclear' if depth > 1 else '',
                })
                if target.move_type == 'entry':
                    append_links(target, depth + 1)

        append_links(move)
        state = 'Unpaid' if not settled else ('Paid' if residual <= 0.00001 else 'Partial')
        return {
            'type': kind, 'number': move.name, 'date': move.date,
            'total': total, 'settled': settled, 'payment_amount': payment_amount,
            'adjustment_amount': adjustment_amount, 'residual': residual,
            'foreign_total': foreign_total, 'foreign_settled': foreign_settled,
            'foreign_residual': foreign_residual,
            'state': state, 'currency': move.currency_id.name or move.company_id.currency_id.name,
            'links': rows, 'period_label': self._period_label(move.invoice_date or move.date, date_from),
        }

    def _report_data(self, wizard):
        account_types = self._account_types(wizard.direction)
        accounts = self.env['account.account'].search([
            ('company_id', '=', wizard.company_id.id), ('account_type', 'in', account_types),
            ('deprecated', '=', False),
        ])
        if wizard.direction in ('payable', 'both'):
            accounts |= self.env['account.account'].search([
                ('company_id', '=', wizard.company_id.id),
                ('account_type', '=', 'liability_current'), ('deprecated', '=', False),
            ])
        if wizard.account_ids:
            accounts &= wizard.account_ids.filtered(lambda account: account.company_id == wizard.company_id)
        domain = [
            ('company_id', '=', wizard.company_id.id),
            ('state', 'in', self._move_states(wizard.target_move)),
            ('move_type', 'in', ('out_invoice', 'in_invoice')),
            ('line_ids.account_id', 'in', accounts.ids),
        ]
        if wizard.date_to:
            domain = expression.AND([domain, expression.OR([
                [('invoice_date', '<=', wizard.date_to)],
                [('invoice_date', '=', False), ('date', '<=', wizard.date_to)],
            ])])
        if wizard.date_from:
            domain = expression.AND([domain, expression.OR([
                [('invoice_date', '>=', wizard.date_from)],
                [('invoice_date', '=', False), ('date', '>=', wizard.date_from)],
            ])])
        if wizard.partner_ids:
            domain.append(('partner_id', 'in', wizard.partner_ids.ids))
        moves = self.env['account.move'].search(domain, order='partner_id, date, name')
        partners = []
        for partner in moves.mapped('partner_id'):
            partner_moves = moves.filtered(lambda move: move.partner_id == partner)
            docs = []
            for move in partner_moves:
                doc = self._document_rows(move, wizard.date_to, wizard.date_from)
                if doc['period_label'] == 'Opening balance' and doc['residual'] <= 0.00001:
                    continue
                if not wizard.reconciled and doc['residual'] <= 0.00001:
                    continue
                docs.append(doc)
            if not docs:
                continue
            partners.append({
                'partner': partner,
                'docs': docs,
                'count': len(docs),
                'total': sum(doc['total'] for doc in docs),
                'payment_amount': sum(doc['payment_amount'] for doc in docs),
                'adjustment_amount': sum(doc['adjustment_amount'] for doc in docs),
                'residual': sum(doc['residual'] for doc in docs),
            })
        return partners

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards.ensure_one()
        sheet = workbook.add_worksheet('Partner Movement')
        header = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1})
        money = workbook.add_format({'num_format': '#,##0.00'})
        bold = workbook.add_format({'bold': True})
        sheet.write(0, 0, 'Start Date', header)
        sheet.write(0, 1, str(wizard.date_from or ''))
        sheet.write(1, 0, 'End Date', header)
        sheet.write(1, 1, str(wizard.date_to))
        headers = ['Partner / Document', 'Type', 'Date', 'Currency', 'Document Total (company currency)',
                   'Payments', 'Adjustments', 'Remaining', 'Status', 'Linked Document Total',
                   'Allocated Amount', 'Link Note']
        for col, value in enumerate(headers):
            sheet.write(2, col, value, header)
        row = 3
        for partner in self._report_data(wizard):
            sheet.write(row, 0, partner['partner'].display_name, bold)
            for col, key in ((4, 'total'), (5, 'payment_amount'), (6, 'adjustment_amount'), (7, 'residual')):
                sheet.write_number(row, col, partner[key], money)
            sheet.write(row, 8, f"{partner['count']} documents", bold)
            row += 1
            for doc in partner['docs']:
                state = f"{doc['period_label']} - {doc['state']}"
                values = [doc['number'], doc['type'], str(doc['date']), wizard.company_id.currency_id.name,
                          doc['total'], doc['payment_amount'], doc['adjustment_amount'], doc['residual'], state]
                for col, value in enumerate(values):
                    sheet.write_number(row, col, value, money) if col in (4, 5, 6, 7) else sheet.write(row, col, value)
                if wizard.with_currency and doc['currency'] != wizard.company_id.currency_id.name:
                    sheet.write(row, 11, f"Foreign currency {doc['currency']}: total/settled/remaining {doc['foreign_total']:.2f} / {doc['foreign_settled']:.2f} / {doc['foreign_residual']:.2f}")
                row += 1
                for link in doc['links']:
                    sheet.write(row, 0, f"{'  ' * link['depth']}↳ {link['number']}")
                    sheet.write(row, 1, link['type'])
                    sheet.write(row, 2, str(link['date']))
                    sheet.write(row, 3, link['currency'])
                    sheet.write_number(row, 9, link['document_total'], money)
                    sheet.write_number(row, 10, link['allocated'], money)
                    sheet.write(row, 11, link['warning'])
                    row += 1
        sheet.freeze_panes(3, 0)
        sheet.set_column('A:A', 34)
        sheet.set_column('B:D', 16)
        sheet.set_column('E:K', 20)
        sheet.set_column('L:L', 35)
