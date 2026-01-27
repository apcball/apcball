# RMA Features Documentation - Warranty Management Module

## Overview

This document describes the enhanced RMA (Return Merchandise Authorization) features implemented in the `buz_warranty_management` module for Odoo 17. These features provide comprehensive stock operations, claim lines tracking, and accounting integration for warranty management.

---

## 🎯 New Features Implemented

### 1. Warranty Claim Lines (`warranty.claim.line`)

Track parts, consumables, and replacement items used in warranty repairs.

**Fields:**
- `product_id`: Product used in repair
- `description`: Item description
- `qty`: Quantity
- `uom_id`: Unit of measure (related from product)
- `lot_id`: Serial/Lot number
- `need_replacement`: Flag to mark items for replacement
- `is_consumable`: Auto-computed based on product type
- `unit_cost`: Internal cost tracking
- `unit_price`: Customer billing price (for out-of-warranty)
- `move_ids`: Linked stock moves for traceability

**Use Cases:**
- Track parts used during repair
- Mark items that need replacement
- Calculate costs for out-of-warranty billing
- Link to stock movements

---

### 2. RMA Configuration Settings

Configure operation types, locations, and accounts via **Settings > General Settings > Warranty Management**.

**Configuration Options:**

#### Stock Operations
- `warranty_rma_in_picking_type_id`: Operation type for customer returns (RMA IN)
- `warranty_replacement_out_picking_type_id`: Operation type for replacements (RMA OUT)
- `warranty_repair_location_id`: Internal location for repair/diagnosis
- `warranty_scrap_location_id`: Location for defective/scrapped items

#### Accounting
- `warranty_expense_account_id`: Expense account for under-warranty costs
- `warranty_default_service_product_id`: Default service product for repairs

---

### 3. Extended Warranty Claim Statuses

Enhanced workflow with detailed RMA tracking:

```
draft → under_review → awaiting_return → received → 
diagnosing → awaiting_parts → ready_to_issue → approved → done
```

**Status Descriptions:**
- `awaiting_return`: RMA IN created, waiting for customer shipment
- `received`: Item received at repair location
- `diagnosing`: Under diagnosis/inspection
- `awaiting_parts`: Waiting for replacement parts
- `ready_to_issue`: Ready to ship replacement to customer

---

### 4. RMA IN Wizard (`warranty.rma.receive.wizard`)

Create incoming pickings for customer returns.

**Workflow:**
1. Open claim → Click "Create RMA IN"
2. Configure:
   - Product and serial/lot number
   - Quantity
   - Destination location (repair location)
   - Notes
3. System creates:
   - Stock picking (Customer → Repair Location)
   - Stock move with lot tracking
   - Link to claim
4. Claim status updates to `awaiting_return`

**Features:**
- Auto-loads settings from configuration
- Captures serial/lot numbers
- Optional return label generation
- Posts message to claim chatter

---

### 5. Replacement Issue Wizard (`warranty.replacement.issue.wizard`)

Issue replacement items to customers.

**Workflow:**
1. Open claim → Click "Issue Replacement"
2. Add replacement lines:
   - Product, quantity, lot/serial
   - Unit price (zero for under-warranty)
3. Optional: Create Sale Order for tracking
4. System creates:
   - Stock picking (Repair Location → Customer)
   - Stock moves for each line
   - Optional SO (zero-price for warranty, normal price for OOW)
   - Links to claim lines

**Features:**
- Auto-loads claim lines marked `need_replacement`
- Under-warranty: Zero price delivery
- Out-of-warranty: Creates SO with prices from claim lines
- Serial/lot assignment for replacements
- Links stock moves to claim lines

---

### 6. Quick Invoice Wizard (`warranty.invoice.wizard`)

Generate invoices directly from claim lines.

**Workflow:**
1. Open claim → Click "Create Invoice"
2. Select journal and invoice date
3. Auto-loads claim lines with prices
4. Edit lines if needed
5. System creates:
   - Draft invoice with claim origin
   - Invoice lines from claim lines
   - Links invoice to claim

**Use Cases:**
- Quick billing for out-of-warranty repairs
- Charge for parts and labor
- Alternative to SO-based billing

---

### 7. RMA Slip Report

Professional PDF report for RMA pickings.

**Features:**
- Customer information
- Product details with serial/lot numbers
- Demand vs. Done quantities
- Source and destination locations
- Signature blocks
- Works for both RMA IN and RMA OUT pickings

**Access:** Stock Picking → Print → RMA Slip

---

## 📊 New Fields on Warranty Claim

### Relationship Fields
- `claim_line_ids`: One2many to claim lines
- `rma_in_picking_ids`: Many2many to RMA IN pickings
- `replacement_out_picking_ids`: Many2many to replacement pickings
- `invoice_ids`: Many2many to invoices
- `currency_id`: Currency for monetary fields

### Computed Fields
- `rma_in_count`: Count of RMA IN pickings
- `replacement_out_count`: Count of replacement pickings
- `invoice_count`: Count of linked invoices

---

## 🔄 Typical RMA Workflows

### Under-Warranty Replacement Flow

1. **Customer reports issue** → Create Claim
2. **Review claim** → Status: Under Review
3. **Request return** → Create RMA IN picking
4. **Customer ships** → Status: Awaiting Return
5. **Receive item** → Validate RMA IN picking → Status: Received
6. **Diagnose** → Add claim lines for needed parts → Status: Diagnosing
7. **Mark replacements** → Set `need_replacement=True` on lines
8. **Issue replacement** → Create replacement OUT picking → Status: Ready to Issue
9. **Ship to customer** → Validate picking
10. **Complete** → Status: Done

**Cost Recognition:**
- Under-warranty: Stock valuation flows to Warranty Expense account
- No invoice to customer

---

### Out-of-Warranty Repair Flow

1. **Customer reports issue** → Create Claim
2. **Check warranty** → System shows "OUT OF WARRANTY"
3. **Request return** → Create RMA IN picking
4. **Receive item** → Validate RMA IN
5. **Diagnose** → Add claim lines for parts/labor with prices
6. **Create invoice or SO**:
   - Option A: Click "Create Invoice" → Direct invoice
   - Option B: Click "Issue Replacement" → Creates SO with prices
7. **Customer pays** → Confirm SO/Invoice
8. **Issue replacement** → Validate replacement picking
9. **Complete** → Status: Done

**Billing:**
- Customer invoiced for parts and labor
- Normal FIFO cost flow for stock

---

## 🎮 User Interface Enhancements

### Smart Buttons on Claim Form
- **RMA IN** (count): View customer return pickings
- **Replacements** (count): View replacement deliveries
- **Invoices** (count): View linked invoices

### Action Buttons
- **Create RMA IN**: Open RMA receive wizard
- **Issue Replacement**: Open replacement issue wizard
- **Create Invoice**: Open quick invoice wizard (OOW only)
- **Create Quotation**: Original OOW quotation wizard

### New Notebook Pages
- **Claim Lines**: Manage parts/consumables used
- **Problem Description**: Issue details
- **Internal Notes**: Team notes
- **Resolution**: Resolution documentation

---

## 🔐 Security

All new models and wizards have proper access rights for:
- `group_warranty_user`: Read, Write, Create (no delete)
- `group_warranty_manager`: Full access

Models protected:
- `warranty.claim.line`
- `warranty.rma.receive.wizard`
- `warranty.replacement.issue.wizard`
- `warranty.replacement.issue.line`
- `warranty.invoice.wizard`
- `warranty.invoice.line`

---

## 🔧 Configuration Setup

### Initial Configuration Steps

1. **Go to Settings > General Settings**
2. **Scroll to "Warranty Management" section**
3. **Configure Stock Operations:**
   - RMA IN Picking Type: Select or create (e.g., "Receipts")
   - Repair Location: Select internal location (e.g., "WH/Repair")
   - Replacement OUT: Select outgoing type (e.g., "Delivery Orders")
   - Scrap Location: Select scrap location

4. **Configure Accounting:**
   - Warranty Expense Account: Select expense account (e.g., 5100 - Warranty Expense)
   - Default Service Product: Select service product for repairs

5. **Save settings**

---

## 📝 Data Flow Examples

### Example 1: Under-Warranty Replacement

```
Customer reports defective laptop
↓
Create Claim (Product: Laptop, Serial: LAP001)
↓
Create RMA IN (LAP001: Customer → Repair Location)
↓
Add Claim Lines:
  - Part: Motherboard, Qty: 1, Need Replacement: Yes
  - Part: RAM, Qty: 2, Need Replacement: Yes
↓
Issue Replacement:
  - Creates picking (Repair → Customer)
  - Creates moves for Motherboard + RAM
  - Optional: Creates SO with $0 prices for tracking
↓
Validate picking
↓
Cost flows: Stock Value → Warranty Expense Account
↓
Done
```

### Example 2: Out-of-Warranty Repair

```
Customer reports issue (warranty expired)
↓
Create Claim (shows OUT OF WARRANTY alert)
↓
Create RMA IN (receive defective item)
↓
Add Claim Lines:
  - Part: Screen, Qty: 1, Cost: $50, Price: $120
  - Service: Labor, Qty: 2hrs, Price: $80/hr
↓
Create Invoice (or Issue Replacement with SO):
  - Screen: $120
  - Labor: $160
  - Total: $280
↓
Customer pays invoice
↓
Issue Replacement (if applicable)
↓
Done
```

---

## 🔍 Traceability

### Stock Move Traceability
- Each claim line can be linked to multiple stock moves
- View moves from: Claim Line → Stock Moves
- Trace serial/lot from original return to replacement

### Document Chain
```
Sale Order
  ↓
Delivery Order
  ↓
Warranty Card (auto-created)
  ↓
Warranty Claim
  ↓
├─ RMA IN Picking
├─ Claim Lines
├─ Replacement OUT Picking
└─ Invoice / Sale Order
```

---

## 🆕 Differences from Basic Version

| Feature | Basic Version | Enhanced RMA Version |
|---------|---------------|---------------------|
| Claim Lines | ❌ No | ✅ Yes (parts tracking) |
| Stock Operations | ❌ No | ✅ RMA IN/OUT pickings |
| Serial/Lot Tracking | ❌ Limited | ✅ Full tracking |
| Replacement Flow | ❌ Manual | ✅ Automated wizards |
| Quick Invoice | ❌ SO only | ✅ Direct invoice wizard |
| Settings | ❌ No | ✅ Full configuration |
| Statuses | 5 basic | 10 detailed |
| Reports | 2 | 3 (added RMA slip) |
| Accounting | ❌ Manual | ✅ Configured accounts |

---

## 📚 Technical Details

### Dependencies
- `sale`: Sale order integration
- `stock`: Stock operations
- `stock_account`: Valuation and accounting
- `account`: Invoicing
- `mail`: Chatter integration
- `uom`: Unit of measure

### Key Methods

**warranty.claim**
- `action_create_rma_in()`: Open RMA receive wizard
- `action_issue_replacement()`: Open replacement wizard
- `action_create_invoice()`: Open invoice wizard
- `action_view_rma_in_pickings()`: View RMA IN pickings
- `action_view_replacement_out_pickings()`: View replacements
- `action_view_invoices()`: View invoices

**warranty.rma.receive.wizard**
- `action_create_rma_picking()`: Create RMA IN picking

**warranty.replacement.issue.wizard**
- `action_issue_replacement()`: Create replacement picking + optional SO

**warranty.invoice.wizard**
- `action_create_invoice()`: Create invoice from claim lines

---

## 🎓 Best Practices

### 1. Configuration
- Set up locations and operation types before first use
- Use dedicated repair location for better tracking
- Configure warranty expense account in chart of accounts

### 2. Workflow
- Always create RMA IN before issuing replacement
- Add claim lines during diagnosis for cost tracking
- Mark `need_replacement=True` for items to ship to customer

### 3. Pricing
- Under-warranty: Set unit_price = 0 on claim lines
- Out-of-warranty: Set realistic prices for billing
- Use service products for labor charges

### 4. Documentation
- Use claim notes for detailed problem description
- Add internal notes for team communication
- Document resolution for future reference

---

## 🐛 Troubleshooting

### Issue: "No RMA IN picking type configured"
**Solution:** Go to Settings > Warranty Management > Configure RMA IN Picking Type

### Issue: "Replacement wizard empty"
**Solution:** Add claim lines and mark `need_replacement=True`

### Issue: "Cannot create invoice"
**Solution:** Ensure claim is out-of-warranty and has claim lines with prices

### Issue: "Serial number not tracked"
**Solution:** Ensure product has tracking enabled and lot_id is set on moves

---

## 📈 Future Enhancements (Not Yet Implemented)

- Portal view for customers to check RMA status
- Auto-email notifications for RMA status changes
- Barcode scanning for quick RMA receiving
- Integration with buz_account_receipt for receipts
- Warranty analytics dashboard with KPIs
- RMA return label generation (PDF)

---

## 🏆 Summary

The enhanced RMA features provide a complete end-to-end workflow for warranty management with:

✅ Full stock operation integration
✅ Parts and consumables tracking
✅ Flexible billing options (invoice or SO)
✅ Serial/lot traceability
✅ Configurable settings
✅ Professional reports
✅ Under and out-of-warranty support

---

**Version:** 17.0.2.0.0 (Enhanced RMA)  
**Last Updated:** 2025-10-24  
**Author:** Buzzit  
**License:** LGPL-3
