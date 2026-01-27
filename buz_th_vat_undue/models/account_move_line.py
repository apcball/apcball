from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override เพื่อป้องกันการสร้าง account.move.tax.invoice 
        สำหรับ VAT Undue tax lines เมื่อ post bill
        
        Tax Invoice จะถูกสร้างตอนกด "Use VAT" ที่หน้า Taxes Undue แทน
        """
        # เรียก super ก่อน
        move_lines = super().create(vals_list)
        
        # ตรวจสอบและลบ tax invoice records ที่สร้างสำหรับ VAT Undue
        for line in move_lines:
            # ตรวจสอบว่าเป็น tax line และเป็น VAT Undue หรือไม่
            if line.tax_line_id and hasattr(line.tax_line_id, 'is_vat_undue') and line.tax_line_id.is_vat_undue:
                # หา tax invoice records ที่เพิ่งสร้างสำหรับ line นี้
                tax_invoices_to_remove = line.tax_invoice_ids
                
                if tax_invoices_to_remove:
                    _logger.info(
                        f"Preventing tax invoice creation for VAT Undue line: "
                        f"Move={line.move_id.name}, Tax={line.tax_line_id.name}, "
                        f"Removing {len(tax_invoices_to_remove)} tax invoice record(s)"
                    )
                    
                    # ลบ tax invoice records
                    # ใช้ sudo() และ with_context เพื่อให้แน่ใจว่าลบได้
                    tax_invoices_to_remove.with_context(
                        force_remove_tax_invoice=True
                    ).sudo().unlink()
        
        return move_lines
