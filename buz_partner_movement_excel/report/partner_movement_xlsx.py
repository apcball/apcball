from collections import defaultdict

from odoo import fields, models
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
        return 'Bill allocation unclear' if depth > 1 and move_type == 'entry' and ambiguous else ''

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
                    'source_account': own.account_id.display_name,
                    'source_debit': own.debit,
                    'source_credit': own.credit,
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
        header = workbook.add_format({'bold': True, 'bg_color': '#D9EAF7', 'border': 1, 'text_wrap': True})
        money = workbook.add_format({'num_format': '#,##0.00;[Red]-#,##0.00'})
        partner_format = workbook.add_format({'bold': True, 'bg_color': '#E2F0D9'})
        metadata = [
            ('บริษัท', wizard.company_id.display_name),
            ('สกุลเงินบริษัท', wizard.company_id.currency_id.name),
            ('ช่วงวันที่รายงาน', f"{wizard.date_from or 'ทั้งหมด'} ถึง {wizard.date_to}"),
            ('วันเวลาออกรายงาน', fields.Datetime.context_timestamp(
                wizard, fields.Datetime.now()
            ).strftime('%Y-%m-%d %H:%M:%S')),
            ('ทิศทาง', dict(wizard._fields['direction'].selection).get(wizard.direction, '')),
            ('สถานะรายการ', dict(wizard._fields['target_move'].selection).get(wizard.target_move, '')),
            ('รวมเอกสารที่ชำระครบแล้ว', 'ใช่' if wizard.reconciled else 'ไม่'),
            ('แสดงยอดสกุลเงินต่างประเทศ', 'ใช่' if wizard.with_currency else 'ไม่'),
            ('คู่ค้า', ', '.join(wizard.partner_ids.mapped('display_name')) or 'ทั้งหมด'),
            ('บัญชี', ', '.join(wizard.account_ids.mapped('display_name')) or 'ทั้งหมด'),
        ]
        for row, (label, value) in enumerate(metadata):
            sheet.write(row, 0, label, header)
            sheet.write(row, 1, value)
        headers = [
            'คู่ค้า / เลขที่เอกสาร', 'ประเภทเอกสาร', 'วันที่', 'สมุดรายวัน', 'บัญชีลูกหนี้/เจ้าหนี้',
            'เดบิต (สกุลเงินบริษัท)', 'เครดิต (สกุลเงินบริษัท)', 'สกุลเงินเอกสาร',
            'ยอดเอกสาร (สกุลเงินบริษัท)', 'รับ/จ่ายชำระ (สกุลเงินบริษัท)',
            'รายการปรับปรุง (สกุลเงินบริษัท)', 'ยอดคงเหลือ (สกุลเงินบริษัท)', 'สถานะ',
            'เอกสารที่เชื่อมโยง', 'บัญชีรายการที่เชื่อมโยง',
            'เดบิตรายการที่เชื่อมโยง (สกุลเงินบริษัท)', 'เครดิตรายการที่เชื่อมโยง (สกุลเงินบริษัท)',
            'ยอดจัดสรร (สกุลเงินบริษัท)',
            'ยอดจัดสรร (สกุลเงินเอกสาร)',
            'หมายเหตุ',
        ]
        header_row = len(metadata) + 1
        for col, value in enumerate(headers):
            sheet.write(header_row, col, value, header)
        row = header_row + 1
        for partner in self._report_data(wizard):
            sheet.write(row, 0, partner['partner'].display_name, partner_format)
            for col, key in ((8, 'total'), (9, 'payment_amount'), (10, 'adjustment_amount'), (11, 'residual')):
                sheet.write_number(row, col, partner[key], money)
            sheet.write(row, 12, f"รวม {partner['count']} เอกสาร", partner_format)
            row += 1
            for doc in partner['docs']:
                period = 'ยอดยกมา' if doc['period_label'] == 'Opening balance' else 'รายการในช่วง'
                status = {'Unpaid': 'ค้างชำระ', 'Partial': 'ชำระบางส่วน', 'Paid': 'ชำระครบ'}[doc['state']]
                values = [doc['number'], doc['type'], str(doc['date']), doc['journal'], doc['account'],
                          doc['debit'], doc['credit'], doc['currency'], doc['total'],
                          doc['payment_amount'], doc['adjustment_amount'], doc['residual'], f'{period} - {status}']
                for col, value in enumerate(values):
                    if col in (5, 6, 8, 9, 10, 11):
                        sheet.write_number(row, col, value, money)
                    else:
                        sheet.write(row, col, value)
                if wizard.with_currency and doc['currency'] != wizard.company_id.currency_id.name:
                    sheet.write(row, 19, f"ยอดต่างประเทศ {doc['currency']}: {doc['foreign_total']:.2f} / {doc['foreign_settled']:.2f} / {doc['foreign_residual']:.2f}")
                row += 1
                for link in doc['links']:
                    sheet.write(row, 0, f"{'  ' * link['depth']}↳ {link['number']}")
                    sheet.write(row, 1, link['type'])
                    sheet.write(row, 2, str(link['date']))
                    sheet.write(row, 3, link['journal'])
                    sheet.write(row, 4, link['source_account'])
                    sheet.write_number(row, 5, link['source_debit'], money)
                    sheet.write_number(row, 6, link['source_credit'], money)
                    sheet.write(row, 7, link['currency'])
                    sheet.write(row, 13, link['number'])
                    sheet.write(row, 14, link['target_account'])
                    sheet.write_number(row, 15, link['debit'], money)
                    sheet.write_number(row, 16, link['credit'], money)
                    sheet.write_number(row, 17, link['allocated'], money)
                    sheet.write(row, 18, f"{link['allocated_currency']:.2f} {link['source_currency']}")
                    sheet.write(row, 19, link['warning'])
                    row += 1
        sheet.freeze_panes(header_row + 1, 0)
        sheet.set_column('A:A', 34)
        sheet.set_column('B:D', 19)
        sheet.set_column('E:E', 28)
        sheet.set_column('F:G', 16, money)
        sheet.set_column('H:H', 13)
        sheet.set_column('I:L', 18, money)
        sheet.set_column('M:M', 25)
        sheet.set_column('N:O', 30)
        sheet.set_column('P:R', 20, money)
        sheet.set_column('S:S', 26)
        sheet.set_column('T:T', 42)
