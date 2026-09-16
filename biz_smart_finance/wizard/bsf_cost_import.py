import base64
import csv
import io
from odoo import fields, models, _
from odoo.exceptions import UserError
from ..models.bsf_cost import CATEGORIES, require_manager
from ..models.bsf_cost_math import finite_nonnegative

COLUMNS = ['source_key', 'name', 'department', 'category', 'amount', 'fixed_pct', 'one_off', 'allocation_complete']


class CostImport(models.TransientModel):
    _name = 'biz.smart.finance.cost.import'
    _inherit = 'biz.smart.finance.import.mixin'
    _description = 'นำเข้าต้นทุนรายเดือน CSV/XLSX'
    period_id = fields.Many2one('biz.smart.finance.cost.period', required=True, string='ชุดข้อมูลร่าง')
    line_ids = fields.One2many('biz.smart.finance.cost.import.line', 'wizard_id')
    _preview_fields = ('source_key', 'name', 'department', 'category', 'amount', 'fixed_pct', 'one_off', 'allocation_complete')
    _preview_context_fields = ('period_id', 'company_id')

    def _file_columns(self): return COLUMNS
    def _required_columns(self): return ['source_key', 'name', 'category', 'amount', 'fixed_pct']

    @staticmethod
    def _bool_cell(value):
        if value.lower() not in ('', '0', '1', 'true', 'false'):
            raise ValueError('ใช้ 1/0 หรือ true/false')
        return value.lower() in ('1', 'true')

    def _parse_rows(self, rows):
        return [self._parse_cells(row, {
            'source_key': ('source_key', str.strip), 'name': ('name', str.strip),
            'department': ('department', str.strip),
            'category': ('category', lambda v: self._selection(v, dict(CATEGORIES))),
            'amount': ('amount', self._to_float), 'fixed_pct': ('fixed_pct', self._to_float),
            'one_off': ('one_off', self._bool_cell), 'allocation_complete': ('allocation_complete', self._bool_cell),
        }) for row in rows]

    def _row_error(self, values, context):
        error = ''
        if not values['source_key'] or not values['name'] or not values['category']:
            error = 'ต้องระบุรหัส ชื่อ และหมวด'
        elif not finite_nonnegative(values['amount'], values['fixed_pct']) or values['fixed_pct'] > 100:
            error = 'จำนวนเงินไม่ติดลบ ส่วนคงที่ 0–100%'
        elif values['category'] == 'sales' and values['one_off']:
            error = 'ยอดขายใช้เครื่องหมายครั้งเดียวไม่ได้'
        elif values['department'] and not self.env['biz.smart.finance.cost.department'].search_count([
                ('company_id', '=', self.company_id.id), ('name', '=', values['department'])]):
            error = 'ไม่พบฝ่ายในบริษัทนี้ ให้สร้างทะเบียนฝ่ายก่อน'
        return error, values['source_key'], False

    def _import_records(self):
        require_manager(self.env)
        period = self.period_id
        if period.company_id != self.company_id or period.state != 'draft':
            raise UserError(_('เลือกชุดร่างของบริษัทเดียวกัน'))
        # Source keys are scoped to the draft. Re-import updates exactly those rows.
        for line in self.line_ids:
            dept = self.env['biz.smart.finance.cost.department'].search([
                ('company_id', '=', self.company_id.id), ('name', '=', line.department)], limit=1) if line.department else False
            vals = {k: line[k] for k in ('source_key', 'name', 'category', 'amount', 'fixed_pct', 'one_off', 'allocation_complete')}
            vals.update(period_id=period.id, department_id=dept.id if dept else False)
            existing = period.line_ids.filtered(lambda l: l.source_key == line.source_key)
            if existing:
                existing.write(vals)
            else:
                self.env['biz.smart.finance.cost.line'].create(vals)
        return {'type': 'ir.actions.act_window', 'res_model': period._name, 'res_id': period.id, 'view_mode': 'form'}

    def _download_template(self, extension):
        self.ensure_one()
        rows = [COLUMNS,
                ['sales-01', 'ยอดขายสุทธิ', '', 'sales', 10000000, 0, 0, 1],
                ['material-01', 'ต้นทุนผันแปร', '', 'material', 6000000, 0, 0, 1],
                ['salary-01', 'เงินเดือน', '', 'salary', 3000000, 100, 0, 1],
                ['fixed-01', 'ต้นทุนคงที่อื่น', '', 'other', 2000000, 100, 0, 1]]
        if extension == 'xlsx':
            from openpyxl import Workbook
            wb = Workbook()
            sheet = wb.active
            sheet.title = 'Costs'
            for row in rows: sheet.append(row)
            stream = io.BytesIO()
            wb.save(stream)
            content = stream.getvalue()
        else:
            stream = io.StringIO()
            csv.writer(stream).writerows(rows)
            content = stream.getvalue().encode('utf-8-sig')
        name = 'cfo_cost_template.' + extension
        self.write({'template_data': base64.b64encode(content), 'template_name': name})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/web/content/%s/%s/template_data/%s?download=true' % (self._name, self.id, name)}


class CostImportLine(models.TransientModel):
    _name = 'biz.smart.finance.cost.import.line'
    _inherit = 'biz.smart.finance.import.line.mixin'
    _description = 'ตัวอย่างนำเข้าต้นทุน'
    _order = 'row_index, id'
    wizard_id = fields.Many2one('biz.smart.finance.cost.import', required=True, ondelete='cascade')
    row_index = fields.Integer()
    source_key = fields.Char()
    name = fields.Char()
    department = fields.Char()
    category = fields.Selection(CATEGORIES)
    amount = fields.Float()
    fixed_pct = fields.Float()
    one_off = fields.Boolean()
    allocation_complete = fields.Boolean()
