# MCP Server Client Guide — Odoo 17

คู่มือสำหรับ AI agent / developer ที่ต้องสร้าง MCP client เชื่อมต่อกับ Odoo 17 MCP Server module

---

## สถาปัตยกรรม

```
AI Agent (Claude, Cursor, ฯลฯ)
   │  stdio (JSON-RPC / MCP protocol)
   ▼
MCP Client (mcp_odoo.py)
   │  HTTP POST (JSON + X-API-Key)
   ▼
Odoo 17 → MCP Controller (/mcp/call/*)
   │  .sudo() + ORM
   ▼
Odoo Database
```

- **Backend**: Odoo module `mcp_server` รันอยู่ใน Odoo instance เป็น HTTP endpoints
- **Client**: `mcp_odoo.py` เป็น stdio-based MCP server ที่ AI agent เรียกผ่าน MCP protocol (JSON-RPC over stdin/stdout)
- **Transport**: Client ↔ Backend ใช้ HTTP POST พร้อม `X-API-Key` header

---

## ข้อกำหนดเบื้องต้น

### 1. Odoo Server
- Odoo 17 ติดตั้ง module `mcp_server` แล้ว
- สร้าง API Key ใน Odoo: **Settings → MCP Server → API Keys**

### 2. MCP Client Runtime
- Python 3.10+
- `httpx` package (`pip install httpx`)

---

## ตั้งค่า MCP Client

### Environment Variables

| Variable | คำอธิบาย | ตัวอย่าง |
|----------|-----------|----------|
| `ODOO_URL` | URL ของ Odoo instance (ไม่มี trailing slash) | `https://your-odoo.com` |
| `ODOO_API_KEY` | API Key จาก MCP Server settings | `LU3mBHnMnNGd6pzS...` |

### Config สำหรับ Claude Desktop / thClaws

ไฟล์ `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "/path/to/python3",
      "args": ["/path/to/mcp_odoo.py"],
      "env": {
        "ODOO_URL": "https://your-odoo.com",
        "ODOO_API_KEY": "your-api-key"
      }
    }
  }
}
```

### Config สำหรับ Cursor IDE

ไฟล์ `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "odoo": {
      "command": "/path/to/python3",
      "args": ["/path/to/mcp_odoo.py"],
      "env": {
        "ODOO_URL": "https://your-odoo.com",
        "ODOO_API_KEY": "your-api-key"
      }
    }
  }
}
```

---

## MCP Protocol

Client รองรับ JSON-RPC methods ดังนี้:

### `initialize`
Client ส่งเพื่อเริ่มการเชื่อมต่อ

**Response:**
```json
{
  "protocolVersion": "2024-11-05",
  "capabilities": {"tools": {}},
  "serverInfo": {"name": "odoo-mcp", "version": "0.1.0"}
}
```

### `notifications/initialized`
Client ack — ไม่ต้องตอบกลับ

### `tools/list`
ขอรายการ tools ทั้งหมด — คืน array ของ tool definitions พร้อม `name`, `description`, `inputSchema`

### `tools/call`
เรียกใช้ tool

**Request:**
```json
{
  "method": "tools/call",
  "params": {
    "name": "sale_order_search",
    "arguments": {"domain": [["state", "=", "sale"]], "limit": 10}
  }
}
```

**Response (success):**
```json
{
  "result": {
    "content": [{"type": "text", "text": "{...json data...}"}]
  }
}
```

**Response (error):**
```json
{
  "result": {
    "isError": true,
    "content": [{"type": "text", "text": "Error: ..."}]
  }
}
```

### `ping`
Health check — ตอบ `{}`

---

## Tools Reference — ทั้งหมด 20 tools

### Sale Order

| Tool | Endpoint | คำอธิบาย |
|------|----------|----------|
| `sale_order_search` | `/mcp/call/sale_order_search` | ค้นหา SO ด้วย Odoo domain |
| `sale_order_read` | `/mcp/call/sale_order_read` | อ่าน SO ตาม ID |
| `sale_order_create` | `/mcp/call/sale_order_create` | สร้าง SO ใหม่ |
| `sale_order_write` | `/mcp/call/sale_order_write` | แก้ไข SO |
| `sale_order_confirm` | `/mcp/call/sale_order_confirm` | ยืนยัน SO (action_confirm) |
| `sale_order_create_invoice` | `/mcp/call/sale_order_create_invoice` | สร้าง Invoice จาก SO |
| `sale_report` | `/mcp/call/sale_report` | รายงานยอดขาย |

### Invoice / Accounting

| Tool | Endpoint | คำอธิบาย |
|------|----------|----------|
| `invoice_confirm` | `/mcp/call/invoice_confirm` | Post invoice (action_post) |
| `accounting_audit` | `/mcp/call/accounting_audit` | ตรวจสอบบัญชี (unbalanced, date mismatch, stale draft) |
| `gl_report` | `/mcp/call/gl_report` | รายงาน General Ledger |
| `gl_variance` | `/mcp/call/gl_variance` | เปรียบเทียบยอด GL 2 ช่วงเวลา |
| `account_move_search` | `/mcp/call/account_move_search` | ค้นหา journal entries |

### Product

| Tool | Endpoint | คำอธิบาย |
|------|----------|----------|
| `product_search` | `/mcp/call/product_search` | ค้นหาสินค้า |
| `product_read` | `/mcp/call/product_read` | อ่านสินค้าตาม ID |
| `product_create` | `/mcp/call/product_create` | สร้างสินค้าใหม่ |
| `product_write` | `/mcp/call/product_write` | แก้ไขสินค้า |

### Partner

| Tool | Endpoint | คำอธิบาย |
|------|----------|----------|
| `partner_search` | `/mcp/call/partner_search` | ค้นหา partner |
| `partner_read` | `/mcp/call/partner_read` | อ่าน partner ตาม ID |
| `partner_create` | `/mcp/call/partner_create` | สร้าง partner ใหม่ |

### Company

| Tool | Endpoint | คำอธิบาย |
|------|----------|----------|
| `company_list` | `/mcp/call/company_list` | รายการบริษัททั้งหมด |
| `company_search` | `/mcp/call/company_search` | ค้นหาบริษัท |

---

## API Endpoint Format

ทุก endpoint รับ `POST` พร้อม JSON body และ `X-API-Key` header

**Request Format:**
```
POST /mcp/call/{tool_name}
Content-Type: application/json
X-API-Key: your-api-key

{"key": "value", ...}
```

**Response Format:**
```json
{"success": true, "data": {...}}
// หรือ
{"success": false, "error": "error message"}
```

---

## ตัวอย่างการใช้งาน

### สร้าง Sale Order + Confirm + Invoice

```json
// 1. สร้าง SO
POST /mcp/call/sale_order_create
{
  "values": {
    "company_id": 1,
    "partner_id": 706,
    "order_line": [[0, 0, {
      "name": "ค่าบริการดูแลสวน",
      "price_unit": 2000.0,
      "product_id": 2046,
      "product_uom_qty": 1
    }]]
  }
}
// → {"success": true, "data": {"id": 21, "name": "ASO2600003", ...}}

// 2. Confirm SO
POST /mcp/call/sale_order_confirm
{"id": 21}
// → {"success": true, "data": {"state": "sale", "invoice_status": "to invoice"}}

// 3. สร้าง Invoice
POST /mcp/call/sale_order_create_invoice
{"id": 21}
// → {"success": true, "data": {"id": 382, "name": "INV/2026/00002", "state": "draft"}}

// 4. Post Invoice
POST /mcp/call/invoice_confirm
{"id": 382}
// → {"success": true, "data": {"state": "posted"}}
```

### ค้นหาข้อมูล

```json
// ค้นหา SO ที่ยืนยันแล้วของบริษัท BLUE ZONE HILL
POST /mcp/call/sale_order_search
{
  "domain": [["company_id", "=", 5], ["state", "in", ["sale", "done"]]],
  "fields": ["name", "partner_id", "amount_total", "state"],
  "limit": 20
}

// ค้นหาสินค้า
POST /mcp/call/product_search
{
  "domain": [["name", "ilike", "สวน"]],
  "fields": ["name", "list_price", "type"],
  "limit": 10
}

// ค้นหา partner
POST /mcp/call/partner_search
{
  "domain": [["name", "ilike", "นภาพร"]],
  "fields": ["name", "phone", "email"]
}
```

### รายงาน

```json
// รายงานยอดขาย
POST /mcp/call/sale_report
{
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "group_by": "month,salesperson"
}

// ตรวจสอบบัญชี
POST /mcp/call/accounting_audit
{
  "date_from": "2025-01-01",
  "date_to": "2025-12-31",
  "checks": ["unbalanced", "stale_draft"]
}

// General Ledger
POST /mcp/call/gl_report
{
  "date_from": "2025-01-01",
  "date_to": "2025-06-30",
  "group_by": "account_partner",
  "account_codes": ["1100", "1200"]
}

// เปรียบเทียบ GL 2 ช่วงเวลา
POST /mcp/call/gl_variance
{
  "period1_from": "2025-01-01", "period1_to": "2025-03-31",
  "period2_from": "2025-04-01", "period2_to": "2025-06-30",
  "variance_threshold": 1000
}
```

---

## การเพิ่ม Tools ใหม่

### 1. Backend (Odoo controller)

เพิ่ม route ใหม่ใน `modules/mcp_server/controllers/mcp.py`:

```python
@http.route('/mcp/call/your_tool', type='http', auth='public', methods=['POST'], csrf=False)
def your_tool(self, **kwargs):
    try:
        self._verify_api_key()
        data = json.loads(request.httprequest.data)
        # business logic here
        records = request.env['your.model'].sudo().search([...])
        result = records.read(['field1', 'field2'])
        return request.make_json_response({'success': True, 'data': result})
    except Exception as e:
        return request.make_json_response({'success': False, 'error': str(e)}, status=400)
```

### 2. Tool Definition

เพิ่มใน `mcp_tools()` method และ `/mcp/tools` response:

```python
{
    'name': 'your_tool',
    'description': 'What this tool does',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'param1': {'type': 'string', 'description': 'Description'},
        },
        'required': ['param1']
    }
}
```

### 3. MCP Client (`mcp_odoo.py`)

เพิ่ม tool definition ใน `TOOLS` list และ dispatch ใน `_exec_tool`:

```python
# ใน TOOLS list
{
    "name": "your_tool",
    "description": "What this tool does",
    "inputSchema": {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "Description"},
        },
    },
},

# ใน _exec_tool
elif name == "your_tool":
    return odoo_call("/mcp/call/your_tool", {
        "param1": args.get("param1"),
    })
```

### 4. Security

เพิ่ม access rights ใน `security/ir.model.access.csv` ถ้าใช้ model ใหม่:

```csv
access_mcp_your_model,mcp.your.model,model_your_model,base.group_user,1,1,1,0
```

### 5. Deploy

```bash
./odoo-bin -u mcp_server -d your_db
```

---

## ข้อควรระวัง

1. **Company context** — `property_payment_term_id`, `property_account_position_id` เป็น company-dependent fields ต้อง query ในบริบทบริษัทที่ถูกต้อง
2. **API Key** ผูกกับ user + company แต่ `_verify_api_key` set `allowed_company_ids` เป็นทุกบริษัทที่ user เข้าถึงได้
3. **`.sudo()`** — controller ใช้ sudo() ข้าม access rights แต่ยังอยู่ใน multi-company rules
4. **Order line format** — สร้าง SO พร้อม line ใช้ `[[0, 0, {fields}]]` (one2many create command)
5. **Invoice creation** — partner ต้องมี `property_payment_term_id` ตั้งไว้ในบริษัทที่สร้าง invoice ไม่เช่นนั้นจะ error due date
6. **Odoo domain** — ใช้ syntax `[[field, operator, value]]` เช่น `[["state", "=", "sale"]]`

---

## โครงสร้างไฟล์

```
modules/mcp_server/
├── __manifest__.py
├── controllers/
│   └── mcp.py              # Backend endpoints (20 tools)
├── models/
│   └── mcp_api_key.py      # API Key model
├── security/
│   └── ir.model.access.csv
├── views/
│   └── mcp_server_views.xml
└── docs/
    └── MCP_CLIENT_GUIDE.md  # คู่มือนี้

mcp-odoo/
├── mcp_odoo.py              # MCP Client (stdio transport)
├── claude_desktop_config.json
├── pyproject.toml
└── README.md
```

---

*Last updated: 2025-05-12*
*MCP Server version: 17.0.1.0.0*
