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
    def _partner_account_types():
        return ['asset_receivable', 'liability_payable', 'liability_current']

    @staticmethod
    def _period_label(document_date, date_from):
        return 'Opening balance' if date_from and document_date < date_from else 'Period activity'

    @staticmethod
    def _skip_sibling_invoice(depth, move_type):
        return depth > 1 and move_type in ('out_invoice', 'in_invoice')

    @staticmethod
    def _link_warning(depth, move_type, ambiguous):
        return 'ตรวจสอบการจัดสรร' if depth > 1 and move_type == 'entry' and ambiguous else ''

    @staticmethod
    def _has_ambiguous_links(source_move, links, seen):
        related_move_ids = set()
        for partial in links:
            debit, credit = partial.debit_move_id, partial.credit_move_id
            own = debit if debit.move_id == source_move else credit
            target = (credit if own == debit else debit).move_id
            if target != source_move and target.id not in seen:
                related_move_ids.add(target.id)
        return len(related_move_ids) > 1

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
        lines = move.line_ids.filtered(
            lambda line: line.account_id.account_type in self._partner_account_types()
        )
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
            ambiguous_links = self._has_ambiguous_links(source_move, links, seen)
            for partial in links:
                debit, credit = partial.debit_move_id, partial.credit_move_id
                own = debit if debit.move_id == source_move else credit
                other = credit if own == debit else debit
                target = other.move_id
                if target == source_move or target.id in seen:
                    continue
                if self._skip_sibling_invoice(depth, target.move_type):
                    continue
                rows.append({
                    'depth': depth,
                    'type': dict(target._fields['move_type'].selection).get(target.move_type) or 'Journal Entry',
                    'number': target.name,
                    'date': target.date,
                    'allocated': partial.amount,
                    'currency': target.currency_id.name or target.company_id.currency_id.name,
                    'warning': self._link_warning(depth, target.move_type, ambiguous_links),
                    'journal': target.journal_id.display_name,
                    'target_account': other.account_id.display_name,
                    'debit': other.debit,
                    'credit': other.credit,
                    'allocated_currency': partial.debit_amount_currency if own == debit else partial.credit_amount_currency,
                    'source_currency': own.currency_id.name or own.company_id.currency_id.name,
                })
                if target.move_type == 'entry':
                    append_links(target, depth + 1)

        append_links(move)
        state = 'Unpaid' if not settled else ('Paid' if residual <= 0.00001 else 'Partial')
        return {
            'type': kind, 'number': move.name, 'date': move.date,
            'journal': move.journal_id.display_name,
            'account': ', '.join(sorted(set(line.account_id.display_name for line in lines))),
            'debit': sum(lines.mapped('debit')), 'credit': sum(lines.mapped('credit')),
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
        header = workbook.add_format({
            'bold': True, 'bg_color': '#D9EAF7', 'border': 1,
            'text_wrap': True, 'valign': 'vcenter',
        })
        money = workbook.add_format({'num_format': '#,##0.00;[Red]-#,##0.00'})
        wrapped = workbook.add_format({'text_wrap': True, 'valign': 'top'})
        partner_format = workbook.add_format({'bold': True, 'bg_color': '#E2F0D9'})
        headers = [
            'คู่ค้า / เลขที่เอกสาร', 'ประเภทเอกสาร', 'วันที่', 'สมุดรายวัน / บัญชี',
            'เดบิต (สกุลเงินบริษัท)', 'เครดิต (สกุลเงินบริษัท)',
            'ยอดเอกสาร (สกุลเงินบริษัท)', 'รับ/จ่ายชำระ (สกุลเงินบริษัท)',
            'รายการปรับปรุง (สกุลเงินบริษัท)', 'ยอดคงเหลือ (สกุลเงินบริษัท)',
            'สกุลเงินเอกสาร', 'ยอดจัดสรร (สกุลเงินบริษัท)', 'สถานะ / หมายเหตุ',
        ]
        for col, value in enumerate(headers):
            sheet.write(0, col, value, header)
        row = 1
        for partner in self._report_data(wizard):
            sheet.write(row, 0, partner['partner'].display_name, partner_format)
            for col, key in ((6, 'total'), (7, 'payment_amount'), (8, 'adjustment_amount'), (9, 'residual')):
                sheet.write_number(row, col, partner[key], money)
            sheet.write(row, 10, wizard.company_id.currency_id.name, partner_format)
            sheet.write(row, 12, f"รวม {partner['count']} เอกสาร", partner_format)
            row += 1
            for doc in partner['docs']:
                period = 'ยอดยกมา' if doc['period_label'] == 'Opening balance' else 'รายการในช่วง'
                status = {'Unpaid': 'ค้างชำระ', 'Partial': 'ชำระบางส่วน', 'Paid': 'ชำระครบ'}[doc['state']]
                sheet.write(row, 0, doc['number'])
                sheet.write(row, 1, doc['type'])
                sheet.write(row, 2, str(doc['date']))
                sheet.write(row, 3, f"{doc['journal']}\n{doc['account']}", wrapped)
                sheet.write_number(row, 4, doc['debit'], money)
                sheet.write_number(row, 5, doc['credit'], money)
                for col, key in (
                    (6, 'total'), (7, 'payment_amount'),
                    (8, 'adjustment_amount'), (9, 'residual'),
                ):
                    sheet.write_number(row, col, doc[key], money)
                sheet.write(row, 10, doc['currency'])
                sheet.write(row, 12, f'{period} · {status}')
                if wizard.with_currency and doc['currency'] != wizard.company_id.currency_id.name:
                    foreign_summary = (
                        f"ยอดเอกสาร/ชำระแล้ว/คงเหลือ: {doc['foreign_total']:.2f} / "
                        f"{doc['foreign_settled']:.2f} / {doc['foreign_residual']:.2f} {doc['currency']}"
                    )
                    sheet.write(row, 12, f'{period} · {status}\n{foreign_summary}', wrapped)
                sheet.set_row(row, 30)
                row += 1
                for link in doc['links']:
                    sheet.write(row, 0, f"{'  ' * link['depth']}↳ {link['number']}", wrapped)
                    sheet.write(row, 1, link['type'])
                    sheet.write(row, 2, str(link['date']))
                    sheet.write(row, 3, f"{link['journal']}\n{link['target_account']}", wrapped)
                    sheet.write_number(row, 4, link['debit'], money)
                    sheet.write_number(row, 5, link['credit'], money)
                    sheet.write(row, 10, link['currency'])
                    sheet.write_number(row, 11, link['allocated'], money)
                    note = link['warning']
                    if wizard.with_currency and link['source_currency'] != wizard.company_id.currency_id.name:
                        foreign_amount = f"{link['allocated_currency']:.2f} {link['source_currency']}"
                        note = f'{note}\n' if note else ''
                        note += f'จัดสรร {foreign_amount}'
                    if note:
                        sheet.write(row, 12, note, wrapped)
                    sheet.set_row(row, 30)
                    row += 1
        sheet.freeze_panes(1, 3)
        sheet.set_row(0, 36)
        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 22)
        sheet.set_column('C:C', 13)
        sheet.set_column('D:D', 28)
        sheet.set_column('E:J', 18, money)
        sheet.set_column('K:K', 14)
        sheet.set_column('L:L', 18, money)
        sheet.set_column('M:M', 40, wrapped)
