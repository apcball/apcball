from odoo import models

def _sanitize_domain(domain):
    """คงโครงสร้างโดเมนเดิม:
    - รับเฉพาะ token เป็น list/tuple และ len>=3
    - field ต้องเป็น str
    - ตัด 'lot_properties.*'
    - กัน 'in' / 'not in' กับค่ากล่องว่าง
    - ไม่ flatten อะไรทั้งสิ้น
    """
    if not isinstance(domain, (list, tuple)):
        return domain

    cleaned = []
    for token in domain or []:
        if isinstance(token, (list, tuple)):
            if len(token) < 3:
                continue
            field, op, rhs = token[0], token[1], token[2]
            if not isinstance(field, str):
                continue
            if field.startswith('lot_properties.'):
                continue
            if op in ('in', 'not in'):
                empty = (rhs is None) or (isinstance(rhs, (list, tuple, set)) and len(rhs) == 0)
                if empty:
                    if op == 'in':
                        cleaned.append(['id', '=', 0])  # false เสมอ
                    # 'not in []' คือ true เสมอ -> ตัดทิ้ง
                    continue
            cleaned.append(list(token))
        else:
            # ตัวประกอบ '|', '&', '!' ปล่อยผ่าน
            cleaned.append(token)
    return cleaned

class StockQuant(models.Model):
    _inherit = 'stock.quant'
    def _search(self, domain, *args, **kwargs):
        domain = _sanitize_domain(domain)
        return super()._search(domain, *args, **kwargs)
