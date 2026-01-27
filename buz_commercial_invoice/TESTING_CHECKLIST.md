# Installation & Testing Checklist

## Pre-Installation Checklist

- [ ] Odoo 17 instance is running
- [ ] Module is located in: `/opt/instance1/odoo17/custom-addons/buz_commercial_invoice/`
- [ ] All files are present:
  - [ ] `__manifest__.py`
  - [ ] `__init__.py`
  - [ ] `models/sale_order.py` (NEW)
  - [ ] `models/account_move.py`
  - [ ] `models/stock_picking.py`
  - [ ] `data/sequence.xml`
  - [ ] `views/sale_order_view.xml` (NEW)
  - [ ] `views/account_move_view.xml`
  - [ ] `views/stock_picking_view.xml`
  - [ ] `report/commercial_invoice_sale_order_report.xml` (NEW)
  - [ ] `report/commercial_invoice_report.xml`
  - [ ] `report/report_action.xml`
  - [ ] `report/paperformat.xml`
  - [ ] `security/ir.model.access.csv`

## Installation Steps

1. **Update Module List**
   ```
   Settings > Apps > Update Apps List
   ```
   - [ ] Module list refreshed

2. **Install Module**
   ```
   Apps > Search "Commercial Invoice" 
   Click on "Custom Commercial Invoice Report"
   Click "Install"
   ```
   - [ ] Module installed successfully
   - [ ] No error messages

3. **Verify Sequence Created**
   ```
   Settings > Technical > Sequences
   Search for "Commercial Invoice"
   ```
   - [ ] Sequence "Commercial Invoice Sequence" exists
   - [ ] Sequence code: "commercial.invoice.sequence"
   - [ ] Prefix: "CIV-"
   - [ ] Padding: 6

## Testing Procedures

### Test 1: Create Sale Order with Commercial Invoice

**Steps:**
1. Go to **Sales > Orders > Quotations**
2. Create new quotation or open existing one
3. Fill in basic details (Customer, Products)
4. Go to **Commercial Invoice** tab
5. Check **Generate Commercial Invoice** checkbox

**Expected Results:**
- [ ] Commercial Invoice No. field auto-fills with "CIV-000001" (or next number)
- [ ] Number is read-only
- [ ] Tab contains all fields: Incoterms, Loading Date, Shipping Mark, Shipping By, Bank Info
- [ ] Amount in Words field shows computed value

**Test 2: Multiple CIV Numbers**

**Steps:**
1. Create second quotation
2. Enable Commercial Invoice
3. Check that CIV number is "CIV-000002"

**Expected Results:**
- [ ] Each sale order gets unique sequential number
- [ ] No gaps in numbering
- [ ] Second order shows different number than first

### Test 3: Optional Fields

**Steps:**
1. Open sale order with CIV enabled
2. Fill in all optional fields:
   - Incoterms: FOB Bangkok
   - Loading Date: 2024-01-20
   - Shipping Mark: FRAGILE
   - Shipping By: By Sea
   - Bank Info: Bank of Thailand, Account 123456

**Expected Results:**
- [ ] All fields save without error
- [ ] Fields remain populated after saving

### Test 4: Print Commercial Invoice

**Steps:**
1. Open sale order with CIV enabled and number assigned
2. Click **Print Commercial Invoice** button (in Commercial Invoice tab)
3. Or: Go to top menu > **Print** > **Commercial Invoice**

**Expected Results:**
- [ ] PDF generates successfully
- [ ] PDF shows:
  - [ ] Document title: "Commercial Invoice"
  - [ ] CIV number: "CIV-XXXXXX"
  - [ ] Company logo and details
  - [ ] Customer information
  - [ ] All sale order line items
  - [ ] Quantities and prices
  - [ ] Total amounts
  - [ ] Amount in words
  - [ ] Signature blocks
- [ ] PDF is printable
- [ ] Filename includes CIV number

### Test 5: Print Without Enabling

**Steps:**
1. Open sale order WITHOUT enabling Commercial Invoice
2. Attempt to print (if button available)

**Expected Results:**
- [ ] Button is hidden or disabled (attributes prevent it)
- [ ] If accessible, error message appears: "Commercial Invoice is not enabled..."

### Test 6: List View Display

**Steps:**
1. Go to **Sales > Orders > Quotations**
2. View list of quotations

**Expected Results:**
- [ ] New column "Commercial Invoice No." appears in list
- [ ] Shows CIV number for enabled orders
- [ ] Shows blank for non-enabled orders
- [ ] Sortable and filterable

### Test 7: Invoice Integration

**Steps:**
1. Open sale order with CIV enabled
2. Create invoice from sale order
   - **Order > Create Invoice**
3. Open created invoice

**Expected Results:**
- [ ] Invoice form shows Commercial Invoice tab with inherited fields
- [ ] Commercial Invoice number visible (if configured to copy)
- [ ] Commercial Invoice report accessible from invoice

### Test 8: Amount in Words

**Steps:**
1. Create quotation with:
   - Product: Unit Price = 100, Qty = 10 (Subtotal = 1000)
   - Ensure currency is USD (or test currency)
2. Enable Commercial Invoice

**Expected Results:**
- [ ] Amount in Words shows: "One Thousand US Dollars" (or equivalent)
- [ ] Field updates automatically when line items change
- [ ] Works with different currencies

### Test 9: Multiple Checkbox Toggles

**Steps:**
1. Create quotation
2. Check "Generate Commercial Invoice" → CIV-000XXX assigned
3. Uncheck "Generate Commercial Invoice"
4. Check again

**Expected Results:**
- [ ] First check: CIV-000XXX1
- [ ] Uncheck: CIV number remains (read-only)
- [ ] Second check: CIV number remains (no new number generated)
- [ ] No duplicate numbers created

### Test 10: Report from Different Models

**Steps:**
1. Test printing from Sale Order
2. Test printing from Stock Picking (if implemented)
3. Test printing from Invoice (legacy)

**Expected Results:**
- [ ] All print correctly from their respective models
- [ ] No errors in report generation
- [ ] Content appropriate to each document type

## Error Handling Tests

### Error Test 1: Print with Disabled CIV

**Expected:** Error message "Commercial Invoice is not enabled..."
- [ ] Error caught and displayed gracefully

### Error Test 2: Missing Required Fields

**Test with:**
1. Sale order without customer
2. Sale order without products
3. Sale order without amounts

**Expected:** Report still generates (fields show empty/default)
- [ ] No fatal errors
- [ ] Partial data displays correctly

### Error Test 3: Concurrent Sequence Access

**Steps (if multi-user testing available):**
1. Multiple users simultaneously enable CIV on different orders
2. Check for duplicate numbers

**Expected:**
- [ ] No duplicate numbers generated
- [ ] Sequence maintains integrity

## Performance Tests

### Performance Test 1: Report Generation Time
- [ ] Report generates within 5 seconds
- [ ] PDF quality is acceptable
- [ ] No memory leaks

### Performance Test 2: Large Order Lines
- [ ] Create quotation with 100+ line items
- [ ] Print report

**Expected:**
- [ ] Report generates successfully
- [ ] All items display correctly
- [ ] No pagination issues

## User Acceptance Tests

### UAT Test 1: User Workflow
1. Sales person creates quotation
2. Adds products and customer
3. Enables Commercial Invoice
4. Fills in shipping details
5. Prints report for export documentation
6. Sends to customer

**Expected:** All steps work smoothly without confusion

### UAT Test 2: Document Management
1. Print multiple commercial invoices
2. Save PDFs to file system
3. Archive for records

**Expected:** 
- [ ] Filenames are meaningful (include CIV number)
- [ ] PDFs are organized and easy to retrieve
- [ ] Print quality is professional

### UAT Test 3: Customization
1. Modify company logo/address
2. Add company-specific terms
3. Reprint report

**Expected:**
- [ ] Changes reflect in report
- [ ] Customization persists
- [ ] No data loss

## Sign-Off Checklist

### Functional Sign-Off
- [ ] All features work as specified
- [ ] All tests passed
- [ ] No critical bugs found

### Performance Sign-Off
- [ ] Report generation is fast enough
- [ ] No system slowdown observed
- [ ] Sequence generation is reliable

### User Sign-Off
- [ ] Users can easily enable CIV
- [ ] Print process is intuitive
- [ ] Report quality is acceptable
- [ ] No training required

### Security Sign-Off
- [ ] Access control working (if configured)
- [ ] No data exposure
- [ ] Audit trail captured

## Go-Live Checklist

- [ ] Module tested in staging environment
- [ ] Database backup created
- [ ] Rollback plan documented
- [ ] Users trained
- [ ] Support team briefed
- [ ] Monitoring configured
- [ ] Deployment window scheduled

## Post-Installation

**After successful installation, verify:**

1. **Database Integrity**
   ```sql
   SELECT * FROM ir_sequence WHERE code = 'commercial.invoice.sequence';
   ```
   - [ ] Sequence record exists
   - [ ] Sequence number_next is > 0

2. **Module Registry**
   ```
   Settings > Apps > Installed Apps
   Search "Commercial Invoice"
   ```
   - [ ] Module shows as Installed
   - [ ] No warning or error icons

3. **User Access**
   - [ ] Correct user groups have access
   - [ ] Sales team can see Commercial Invoice tab
   - [ ] Print button is available

## Troubleshooting

### Issue: CIV Number Not Generated

**Solution:**
1. Check sequence exists: Settings > Technical > Sequences
2. Verify sequence code is "commercial.invoice.sequence"
3. Check box must be checked to trigger generation
4. Restart Odoo service if needed

### Issue: Commercial Invoice Tab Not Visible

**Solution:**
1. Clear browser cache (Ctrl+Shift+Del)
2. Refresh page (Ctrl+R)
3. Check module installation status
4. Verify views are loaded

### Issue: Print Button Not Working

**Solution:**
1. Ensure Commercial Invoice is enabled
2. Ensure CIV number is generated
3. Check report permissions
4. Try different browser
5. Check Odoo logs for errors

### Issue: PDF Not Generating

**Solution:**
1. Check wkhtmltopdf installation
2. Verify paperformat exists
3. Check Odoo logs
4. Try direct SQL test of report data

## Success Criteria

Module is successfully deployed when:

✓ CIV numbers automatically generate when checkbox is enabled
✓ Numbers are sequential and unique
✓ Report prints successfully with all data
✓ All optional fields can be filled and saved
✓ Commercial Invoice tab appears on all quotations
✓ No error messages appear during normal use
✓ Multiple users can use simultaneously without conflicts
✓ Print quality is professional and suitable for export
