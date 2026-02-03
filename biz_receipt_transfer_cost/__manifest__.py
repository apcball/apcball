# -*- coding: utf-8 -*-
{
    'name': 'Receipt Transfer with Cost Price',
    'version': '17.0.1.1.0',
    'category': 'Warehouse',
    'summary': 'กำหนดราคาต้นทุนบน Receipt Transfer และสร้าง Inventory Valuation',
    'description': """
Receipt Transfer with Cost Price
================================
ระบบกำหนดราคาต้นทุนสินค้าบน Receipt Transfer

คุณสมบัติ / Features:
--------------------
* เพิ่มฟิลด์ Cost Price บน Stock Move / Stock Move Line
* สามารถแก้ไขราคาต้นทุนได้ที่ Receipt (Picking)
* ราคาต้นทุนถูกดึงมาจาก Product's Cost เป็นค่าเริ่มต้น
* เมื่อ Validate Receipt จะสร้าง Inventory Valuation ตามราคาที่กำหนด
* รองรับทั้ง Odoo Community และ Enterprise

Use Cases:
----------
* Receipt โดยไม่ผ่าน Purchase Order ต้องการระบุราคาต้นทุนเอง
* ปรับราคาต้นทุนสินค้าขณะรับเข้า
* Landed Cost / Additional Cost ที่ต้องการรวมเข้าต้นทุน

Thai Description:
-----------------
โมดูลนี้ใช้สำหรับกำหนดราคาต้นทุนบนใบรับสินค้า (Receipt) 
เมื่อสร้าง Receipt โดยไม่มี Purchase Order จะสามารถใส่ราคาต้นทุนได้เอง
และระบบจะสร้าง Inventory Valuation ตามราคาที่กำหนด
    """,
    'author': 'BizTech',
    'website': 'https://www.biztech.co.th',
    'license': 'LGPL-3',
    'depends': [
        'stock',
        'stock_account',
        'purchase_stock',
    ],
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        # Views
        'views/stock_picking_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
