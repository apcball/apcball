# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # Note: wht_tax_id field already exists in account_move.py
    # We'll use the existing field and enhance its functionality
    wht_invoice_amount = fields.Monetary(
        string="WHT Amount",
        compute="_compute_wht_invoice_amount",
        store=True,
        help="Withholding tax amount for this line",
    )
    
    wht_invoice_base = fields.Monetary(
        string="WHT Base",
        compute="_compute_wht_invoice_amount", 
        store=True,
        help="Base amount for withholding tax calculation",
    )

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Override to ensure WHT fields are visible in invoice lines"""
        result = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        # Add WHT fields to tree view if not present
        if view_type == 'tree' and 'wht_tax_id' not in result['arch']:
            import xml.etree.ElementTree as ET
            doc = ET.fromstring(result['arch'])
            
            # Find tax_ids field and add WHT fields after it
            for tax_field in doc.xpath("//field[@name='tax_ids']"):
                # Create WHT field elements using existing wht_tax_id field
                wht_tax_field = ET.Element('field', {
                    'name': 'wht_tax_id',
                    'string': 'WHT',
                    'optional': 'show'
                })
                wht_amount_field = ET.Element('field', {
                    'name': 'wht_invoice_amount', 
                    'string': 'WHT Amount',
                    'optional': 'hide',
                    'readonly': '1'
                })
                
                # Insert after tax_ids
                parent = tax_field.getparent()
                tax_index = list(parent).index(tax_field)
                parent.insert(tax_index + 1, wht_tax_field)
                parent.insert(tax_index + 2, wht_amount_field)
                break
                
            result['arch'] = ET.tostring(doc, encoding='unicode')
            
        return result

    @api.depends('wht_tax_id', 'price_subtotal')
    def _compute_wht_invoice_amount(self):
        """คำนวณยอด WHT สำหรับ invoice line เพื่อให้บันทึก Withholding Tax Move ถูกต้อง"""
        for line in self:
            try:
                wht_tax = line.wht_tax_id
                base_amount = abs(line.price_subtotal) if line.price_subtotal else 0
                
                if wht_tax and base_amount:
                    line.wht_invoice_base = base_amount
                    line.wht_invoice_amount = base_amount * (abs(wht_tax.amount) / 100)
                else:
                    line.wht_invoice_base = 0
                    line.wht_invoice_amount = 0
            except Exception:
                line.wht_invoice_base = 0
                line.wht_invoice_amount = 0

    def _prepare_wht_move_vals(self):
        """เตรียม values สำหรับสร้าง withholding tax move"""
        self.ensure_one()
        wht_tax = self.wht_tax_id
        
        if not wht_tax:
            return {}
            
        return {
            'partner_id': self.partner_id.id,
            'amount_income': self.wht_invoice_base,
            'amount_wht': self.wht_invoice_amount,
            'wht_tax_id': wht_tax.id,
            'wht_cert_income_type': wht_tax.wht_cert_income_type or '1',
            'wht_cert_income_desc': wht_tax.wht_cert_income_desc or 'Services',
        }


class AccountMove(models.Model):
    _inherit = "account.move"

    # WHT summary fields - รวมยอด WHT ทั้งหมดในเอกสาร
    invoice_wht_total_base = fields.Monetary(
        string="Total WHT Base (Invoice)",
        compute="_compute_invoice_wht_totals",
        store=True,
        help="Total base amount for withholding tax from invoice lines",
    )
    
    invoice_wht_total_tax = fields.Monetary(
        string="Total WHT Tax (Invoice)",
        compute="_compute_invoice_wht_totals",
        store=True,
        help="Total withholding tax amount from invoice lines",
    )

    @api.depends('invoice_line_ids.wht_invoice_amount', 'invoice_line_ids.wht_invoice_base')
    def _compute_invoice_wht_totals(self):
        """คำนวณยอดรวม WHT ในเอกสาร invoice"""
        for move in self:
            try:
                if move.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                    wht_lines = move.invoice_line_ids.filtered(
                        lambda l: l.wht_tax_id
                    )
                    move.invoice_wht_total_base = sum(wht_lines.mapped('wht_invoice_base'))
                    move.invoice_wht_total_tax = sum(wht_lines.mapped('wht_invoice_amount'))
                else:
                    move.invoice_wht_total_base = 0
                    move.invoice_wht_total_tax = 0
            except Exception:
                move.invoice_wht_total_base = 0
                move.invoice_wht_total_tax = 0

    def _post(self, soft=True):
        """สร้าง withholding tax moves เมื่อ post เอกสาร"""
        # Call original _post first
        result = super()._post(soft=soft)
        
        for move in self:
            # สร้าง withholding tax moves สำหรับ invoice lines ที่มี WHT
            if move.move_type in ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'):
                move._create_wht_moves_from_invoice_lines()
        
        return result

    def _create_wht_moves_from_invoice_lines(self):
        """สร้าง withholding tax moves จาก invoice lines ที่มี WHT"""
        self.ensure_one()
        
        # ลบ wht_moves เดิมที่อาจมีปัญหา
        self.wht_move_ids.unlink()
        
        # หา invoice lines ที่มี WHT
        wht_lines = self.invoice_line_ids.filtered(
            lambda l: l.wht_tax_id and l.wht_invoice_amount > 0
        )
        
        if not wht_lines:
            return
            
        # สร้าง withholding moves สำหรับแต่ละ line ที่มี WHT
        wht_moves = []
        for line in wht_lines:
            wht_vals = line._prepare_wht_move_vals()
            if wht_vals:
                wht_vals['move_id'] = self.id
                wht_moves.append((0, 0, wht_vals))
        
        if wht_moves:
            self.write({'wht_move_ids': wht_moves})
            _logger.info(f"Created {len(wht_moves)} WHT moves for invoice {self.name}")

    def action_create_wht_certificate_from_invoice(self):
        """สร้างใบหัก ณ ที่จ่าย จาก invoice ที่มี WHT"""
        self.ensure_one()
        
        if self.wht_cert_ids:
            raise UserError(_("WHT Certificate already exists for this document"))
            
        if not self.invoice_wht_total_tax:
            raise UserError(_("No withholding tax found in invoice lines"))
        
        # สร้างใบหัก ณ ที่จ่าย
        cert_vals = {
            'move_id': self.id,
            'partner_id': self.partner_id.id,
            'date': self.date or fields.Date.today(),
            'income_tax_form': '1',
            'wht_line': []
        }
        
        # รวม WHT lines ตาม tax และ partner
        wht_groups = {}
        for line in self.invoice_line_ids.filtered(lambda l: l.wht_invoice_amount > 0):
            wht_tax = line.wht_tax_id
            if wht_tax:
                key = (wht_tax.id, line.partner_id.id)
                if key not in wht_groups:
                    wht_groups[key] = {
                        'wht_tax_id': wht_tax.id,
                        'partner_id': line.partner_id.id,
                        'base': 0,
                        'amount': 0,
                        'income_type': wht_tax.wht_cert_income_type or '1',
                        'income_desc': wht_tax.wht_cert_income_desc or 'Services',
                    }
                wht_groups[key]['base'] += line.wht_invoice_base
                wht_groups[key]['amount'] += line.wht_invoice_amount
        
        # สร้าง certificate lines
        for group in wht_groups.values():
            cert_vals['wht_line'].append((0, 0, {
                'wht_cert_income_type': group['income_type'],
                'wht_cert_income_desc': group['income_desc'],
                'base': group['base'],
                'amount': group['amount'],
                'wht_tax_id': group['wht_tax_id'],
            }))
        
        cert = self.env['withholding.tax.cert'].create(cert_vals)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Withholding Tax Certificate'),
            'res_model': 'withholding.tax.cert',
            'res_id': cert.id,
            'view_mode': 'form',
            'target': 'current',
        }
