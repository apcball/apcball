# POS Lite Module for Odoo 17

**Lightweight form-based order entry for phone, LINE, and walk-in orders**

## 📋 Overview

POS Lite is a simplified Point-of-Sale module designed for manual order entry scenarios such as phone orders, LINE orders, and walk-in customers. Unlike the standard Odoo POS which uses a grid-based interface, POS Lite provides a clean, form-based interface that's easy to use on desktop and mobile devices.

## 🎯 Features

### POS Terminal
- **Odoo 19-style UI**: Modern grid layout with product cards, category filters, and search
- **Standalone HTML page**: `/pos_lite/ui` with vanilla JS (no OWL dependencies)
- **Customer info**: Name, phone, customer address, delivery address
- **Order cart**: Add/remove items, adjust quantities, real-time totals
- **Payment modal**: Cash/Transfer/Card with change calculation
- **API integration**: JSON endpoints for products and order creation

### Order Management
- **Multi-channel support**: Phone, LINE, Walk-in, Other
- **Customer information**: Name, phone, **customer address**, **delivery address**
- **Warehouse selection**: Per-order warehouse assignment
- **Pricelist support**: Automatic price calculation based on pricelist
- **Order lines**: Add products with quantity, price, discount
- **Automatic calculations**: Subtotal, tax, total, paid amount, change

### Payment Processing
- **Single payment per order**: Cash, Transfer, or Card
- **Payment wizard**: Easy payment registration
- **Journal selection**: Auto-select cash/bank journal from config

### Document Generation
- **Invoice creation**: Automatic `account.move` (out_invoice)
- **Stock picking**: Automatic `stock.picking` for product delivery
- **Receipt printing**: Three formats available
  - Thermal 58mm
  - Thermal 80mm
  - A4 PDF

### Security & Permissions
- **POS Lite User**: Can create/edit orders, register payments
- **POS Lite Manager**: Full access including configuration
- **Multi-company support**: Record rules for data isolation

## 🏗️ Module Structure

```
pos_lite/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── main.py                    # POS Terminal routes (/pos_lite/ui)
├── data/
│   └── sequence_data.xml          # Order sequence configuration
├── models/
│   ├── __init__.py
│   ├── pos_order.py               # Main order model (pos.lite.order)
│   ├── pos_payment.py             # Payment model (pos.lite.payment)
│   ├── pos_config.py              # Configuration model (pos.lite.config)
│   ├── product_product.py         # Product search enhancement
│   └── res_partner.py             # Partner search enhancement
├── report/
│   ├── __init__.py
│   ├── receipt_report.py          # Receipt report model
│   └── receipt_report.xml         # Receipt templates & paper formats
├── security/
│   ├── ir.model.access.csv        # Access control lists
│   └── security.xml               # User groups & record rules
├── views/
│   ├── menu.xml                   # Menu items
│   ├── pos_order_view.xml         # Order form/tree/search views
│   ├── pos_config_view.xml        # Configuration views
│   └── pos_lite_terminal.xml      # POS Terminal standalone HTML template
├── wizard/
│   ├── __init__.py
│   ├── payment_wizard.py          # Payment wizard model
│   ├── payment_wizard_view.xml    # Payment wizard form
│   ├── return_wizard.py           # Return wizard model
│   └── return_wizard_view.xml     # Return wizard form
└── static/
    └── description/
        └── icon.png               # Module icon
```

## 📊 Data Models

### `pos.lite.order` (POS Lite Order)
Main order model with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| name | Char | Order number (auto-generated) |
| company_id | Many2one | Company |
| state | Selection | Draft → Paid → Done → Cancelled |
| channel | Selection | Phone, LINE, Walk-in, Other |
| customer_name | Char | Customer name (for walk-in) |
| partner_id | Many2one | Linked partner |
| partner_phone | Char | Customer phone |
| partner_address | Char | Customer address |
| partner_tax_id | Char | Customer tax ID |
| warehouse_id | Many2one | Warehouse |
| pricelist_id | Many2one | Pricelist |
| line_ids | One2many | Order lines |
| payment_ids | One2many | Payments |
| amount_untaxed | Monetary | Subtotal |
| amount_tax | Monetary | Tax amount |
| amount_total | Monetary | Total |
| amount_paid | Monetary | Paid amount |
| amount_residual | Monetary | Remaining balance |
| amount_change | Monetary | Change amount |
| invoice_id | Many2one | Created invoice |
| picking_id | Many2one | Created stock picking |

### `pos.lite.order.line` (Order Line)
| Field | Type | Description |
|-------|------|-------------|
| order_id | Many2one | Parent order |
| product_id | Many2one | Product |
| description | Char | Product description |
| qty | Float | Quantity |
| price_unit | Monetary | Unit price |
| discount | Float | Discount % |
| price_subtotal | Monetary | Subtotal (computed) |
| price_tax | Monetary | Tax (computed) |
| price_total | Monetary | Total (computed) |

### `pos.lite.payment` (Payment)
| Field | Type | Description |
|-------|------|-------------|
| order_id | Many2one | Parent order |
| payment_method | Selection | Cash, Transfer, Card |
| amount | Monetary | Payment amount |
| journal_id | Many2one | Account journal |
| note | Char | Payment note |

### `pos.lite.config` (Configuration)
| Field | Type | Description |
|-------|------|-------------|
| name | Char | Config name |
| company_id | Many2one | Company |
| warehouse_id | Many2one | Default warehouse |
| pricelist_id | Many2one | Default pricelist |
| journal_id | Many2one | Default payment journal |

## 🔄 Order Workflow

```
┌─────────┐    Register     ┌─────────┐    Process     ┌─────────┐
│  Draft  │ ───Payment───→ │  Paid   │ ───Order────→ │  Done   │
└─────────┘                 └─────────┘                 └─────────┘
     │                           │
     │                           │
     └───────────Cancel──────────┘
```

### States:
1. **Draft**: Initial state, can edit order lines and register payment
2. **Paid**: Payment received, can process to create invoice/picking
3. **Done**: Order completed, invoice and picking created
4. **Cancelled**: Order cancelled (cannot cancel if invoice posted or picking done)

## 🛡️ Security

### User Groups
- **POS Lite User** (`group_pos_lite_user`):
  - Create/Edit orders, order lines, payments
  - Read-only access to configuration
  - Cannot delete records

- **POS Lite Manager** (`group_pos_lite_manager`):
  - Full access to all models including configuration
  - Inherits User permissions

### Record Rules (Multi-company)
All models have company-based record rules:
- Orders: `[('company_id', 'in', company_ids)]`
- Order Lines: `[('company_id', 'in', company_ids)]`
- Payments: `[('company_id', 'in', company_ids)]`
- Config: `[('company_id', 'in', company_ids)]`

## 📦 Dependencies

```python
'depends': [
    'base',
    'mail',           # chatter/messaging
    'contacts',       # partner management
    'product',        # product catalog
    'stock',          # inventory/picking
    'account',        # invoicing
    'sale_management', # pricelists
]
```

## 🚀 Installation

1. Copy `pos_lite` folder to your Odoo addons path
2. Update module list in Odoo
3. Install "POS Lite" module
4. Configure default settings in POS Lite Config (optional)

## ⚙️ Configuration

### Default Settings (Optional)
Navigate to **POS Lite > Configuration** to set default:
- Warehouse
- Pricelist  
- Payment Journal

This allows faster order creation by pre-filling these fields.

### Sequence Configuration
Order numbers are auto-generated using the `pos.lite.order` sequence.
Default format: `POL00001`, `POL00002`, etc.

## 🖨️ Receipt Printing

Three receipt formats are available:

### Thermal 58mm
- Paper width: 58mm
- Margins: 2mm all sides
- DPI: 90
- Best for: Small thermal printers

### Thermal 80mm  
- Paper width: 80mm
- Margins: 3mm left/right, 2mm top/bottom
- DPI: 90
- Best for: Standard thermal printers

### A4
- Standard A4 paper
- Margins: 10mm left/right, 12mm top/bottom
- DPI: 90
- Best for: Printing on regular paper

## 📝 Usage Guide

### Creating an Order

1. Navigate to **POS Lite > Orders**
2. Click **Create**
3. Fill in:
   - **Channel**: Phone/LINE/Walk-in/Other
   - **Customer**: Select existing or enter name/phone
   - **Warehouse**: Select delivery warehouse
   - **Pricelist**: Select pricing
4. Add order lines:
   - Select product
   - Enter quantity
   - Price auto-fills from pricelist
   - Apply discount if needed
5. Click **Register Payment**
6. Enter payment amount and method
7. Click **Confirm**

### Processing the Order

1. Open the paid order
2. Click **Process Order**
3. System automatically:
   - Creates customer invoice
   - Posts the invoice
   - Creates stock picking
   - Validates the picking
4. Order moves to **Done** state

### Creating a Return

1. Open completed order (state = Done)
2. Click **Create Return**
3. Return wizard opens:
   - Select products to return
   - Enter return quantity (full or partial)
   - Add return reason (optional)
4. Click **Create Return**
5. System automatically:
   - Creates return order linked to original
   - Creates Credit Note (out_refund)
   - Creates incoming picking for stock return
   - Processes refund payment
6. Return order moves to **Done** state

### Creating an Exchange

1. Open completed order (state = Done)
2. Click **Exchange**
3. Return wizard opens with Exchange mode:
   - Select products to return (quantity, reason)
   - Add new items in "Exchange — New Items" section
   - Choose **Refund Payment Method** for the return credit
   - View **Summary** box showing Return Total, Exchange Total, and Difference
4. Click **Confirm Exchange**
5. System automatically:
   - Creates **Return Order** with Credit Note (out_refund) and refund payment
   - Creates **Exchange Order** with Invoice (out_invoice) and full payment
   - Both orders moved to Done state
6. Accounting: return credit and exchange invoice are separate documents — net settlement happens during reconciliation

### Return & Exchange Features
- **Full/Partial return**: Return any quantity from original order
- **Refund payment method**: Select method for refund (Cash, Transfer, Card, PromptPay)
- **Exchange value summary**: See return total, exchange total, and difference before confirming
- **Exchange with difference**: If new items cost more, customer pays full price (invoice basis)
- **Exchange with credit back**: If returned items cost more, customer gets refund for returned items (credit note)
- **Return tracking**: Track returned quantity per line with available_return_qty

### Printing Receipt

1. Open completed order
2. Click receipt button (58mm/80mm/A4)
3. Print or save PDF

## 🔧 Technical Notes

### Model Naming
Models use `pos.lite.*` naming convention to avoid conflicts with standard Odoo POS module (`pos.order`, `pos.payment`, `pos.config`).

### Company Isolation
All models use `check_company=True` on relational fields and have record rules for multi-company data isolation.

### Performance
- Product and partner search enhancements are context-aware
- Only activates when `pos_lite_search` or `pos_lite_partner_search` context is set

## 📄 License

LGPL-3

## 👥 Authors

- AI-DEV-Module-Odoo17
- Website: https://github.com/apcball/AI-DEV-Module-Odoo17

---

*Last updated: 2026-04-29*

## 📝 Changelog

### Version 17.0.3.3.0 (Current)
**Date:** 2026-05-28  
**Changes:**
- ✅ **เปิดปุ่ม Return/Exchange** ใน form view สำหรับ Done orders (เปลี่ยนจาก `invisible="1"` → แสดงเมื่อ `state = 'done'`)
- ✅ **เพิ่ม Refund Payment Method** — เลือกวิธีคืนเงินได้ (Cash/Transfer/Card/PromptPay) แทน hardcode cash
- ✅ **Exchange Summary** — wizard แสดง Return Total, Exchange Total, Difference ก่อน confirm
- ✅ **Fix duplicate `discount_type`** — ลบ field ซ้ำใน return_wizard_view.xml
- ✅ **Fix discount_type** — ส่ง discount_type ไปยัง exchange line command ให้ถูกต้อง
- ✅ **เพิ่ม tests** — ทดสอบ refund payment method, journal, exchange summary, return value > exchange value

**Technical:**
- `wizard/return_wizard.py`: เพิ่ม `refund_payment_method`, `refund_journal_id`, computed `return_total`/`exchange_total`/`exchange_difference`/`is_customer_pays`/`is_customer_gets_refund`
- `wizard/return_wizard_view.xml`: เพิ่ม Refund Payment group + Summary box + alert indicator for difference
- `views/pos_order_view.xml`: เปลี่ยนปุ่ม Return/Exchange visibility logic
- `tests/test_return_exchange.py`: เพิ่ม 4 tests (refund method, refund journal, exchange summary, return higher value)

### Version 17.0.3.2.0
**Date:** 2026-05-21  
**Changes:**
- ✅ 新增 POS Terminal UI (Odoo 19 風格設計)
- ✅ POS Terminal 使用獨立 HTML 頁面 + vanilla JS (不再依賴 OWL)
- ✅ 產品網格、搜尋、分類篩選
- ✅ 客戶資訊 + 送貨地址
- ✅ 購物車管理 (增減數量、即時總計)
- ✅ 付款彈窗 (現金/轉帳/刷卡 + 找零計算)
- ✅ JSON API 端點 (`/pos_lite/api/products`, `/pos_lite/api/create_order`)
- ✅ 修復升級後白屏問題

**Technical:**
- Controller: `controllers/main.py` 新增 `/pos_lite/ui` route
- Template: `views/pos_lite_terminal.xml` 獨立 HTML 模板
- Menu action: 從 `ir.actions.client` 改回 `ir.actions.act_url`
- Removed: OWL JS modules, unused assets
- Removed: `website` dependency (不再需要)
- Removed: `pos_lite_ui.xml` template

### Version 17.0.3.1.0
**Date:** 2026-05-28  
**Changes:**
- ✅ เพิ่มฟิลด์ `delivery_address` (Delivery Address) ใน `pos.lite.order`
- ✅ เพิ่มการแสดง **Customer Address** และ **Delivery Address** ใน POS Order Form View
- ✅ เพิ่มการแสดงทั้งสอง Address ใน Receipt Template (58mm, 80mm, A4)
- ✅ อัปเดต Tree View ให้แสดง Delivery Address (optional column)
- ✅ เพิ่มคำอธิบาย string ให้ฟิลด์ address ทั้งสองชัดเจนขึ้น

**Technical:**
- Field `delivery_address` (Char, tracking=True) เพิ่มใน `models/pos_order.py`
- View update: `views/pos_order_view.xml` (form & tree)
- Report update: `report/receipt_report.xml` (แสดง address ในใบเสร็จ)
- ถ้าไม่กรอก Delivery Address จะแสดง Customer Address แทน (fallback)



