# Changelog - Inter-Customer Clearing Payment Module

## Version 17.0.1.1.0 - Wizard Enhancements (Current)

### New Features

#### 1. Tax ID-Based Customer Filtering
- **Component**: Wizard (Step 1)
- **Change**: Customer field now has domain filter requiring valid Tax ID
  - `domain=[('is_company', '=', True), ('vat', '!=', False)]`
- **Benefit**: Ensures only companies with proper Tax ID setup can initiate clearing payments

#### 2. Tax ID Display in Wizard
- **Component**: All three wizard steps
- **Fields Added**:
  - `paying_partner_tax_id`: Computed field showing selected customer's Tax ID
  - `partner_tax_id`: Invoice line item field showing customer's Tax ID
- **Purpose**: Provides clear visibility of Tax ID filtering throughout the wizard

#### 3. Tax ID-Based Invoice Filtering
- **Component**: `_load_available_invoices()` method
- **Change**: Complete rewrite to filter by Tax ID
  - Finds all customers with same Tax ID as paying customer
  - Loads invoices ONLY from those customers
- **Database Query**:
  ```python
  # Get all customers with same Tax ID
  partner_with_same_tax = self.env['res.partner'].search([
      ('vat', '=', self.paying_partner_id.vat),
  ])
  
  # Load invoices from those customers
  invoices = self.env['account.move'].search([
      ('partner_id', 'in', partner_with_same_tax.ids),
      ('state', '=', 'posted'),
      ('move_type', '=', 'out_invoice'),
      ('payment_state', 'in', ['not_paid', 'partial']),
  ])
  ```

#### 4. Enhanced Auto-Fill FIFO
- **Component**: `action_auto_fill_fifo()` method
- **Change**: Now respects Tax ID filtering
  - Auto-fill uses same Tax ID filter as manual selection
  - Allocates from oldest to newest invoice among filtered customers
- **Validation**: Raises error if paying customer has no Tax ID

#### 5. Smart Allocation Line Clearing
- **Component**: `onchange_paying_partner_id()` (NEW)
- **Behavior**: When user changes paying customer, allocation lines are cleared
- **Purpose**: Prevents stale invoice selections from different Tax ID groups

### Modified Files

#### wizard/clearing_payment_wizard.py
**Lines Changed**: 16, 65-67, 79-81, 151-179, 176-214

**Specific Changes**:
1. **paying_partner_id field** (line 16):
   - Added `('vat', '!=', False)` to domain

2. **paying_partner_tax_id field** (lines 17-20):
   - NEW: Computed field to display Tax ID

3. **_compute_paying_partner_tax_id()** (lines 65-67):
   - NEW: Computes Tax ID from paying_partner_id

4. **onchange_paying_partner_id()** (lines 79-81):
   - NEW: Clears allocation lines when customer changes

5. **_load_available_invoices()** (lines 151-179):
   - Complete rewrite with Tax ID filtering
   - Validation: Raises error if no Tax ID

6. **action_auto_fill_fifo()** (lines 176-214):
   - Enhanced with Tax ID filtering logic
   - Finds customers with same Tax ID
   - Respects Tax ID constraints in FIFO calculation

#### wizard/clearing_payment_line.py
**Lines Changed**: 21-26

**Specific Changes**:
1. **partner_tax_id field** (lines 21-24):
   - NEW: Related field showing invoice customer's Tax ID

#### views/clearing_payment_wizard_views.xml
**Lines Changed**: Multiple (entire view records updated)

**Specific Changes**:

1. **view_clearing_payment_wizard_header** (lines 6-43):
   - Added info alert explaining Tax ID filtering logic
   - Added `paying_partner_tax_id` field display
   - Set `no_quick_create` option for paying_partner_id

2. **view_clearing_payment_wizard_form** (lines 45-102):
   - Added info alert with Tax ID reference
   - Added `paying_partner_tax_id` to header fields
   - Tree columns reordered: invoice_number, invoice_date, invoice_partner_id, **partner_tax_id** (NEW), branch_id, residual_amount, allocate_amount
   - Added color coding: blue for unselected, darkgreen for selected

3. **view_clearing_payment_wizard_review** (lines 104-171):
   - Added info alert
   - Added `paying_partner_tax_id` field
   - Added `partner_tax_id` to tree view
   - Reordered columns for clarity

### Error Messages (New)
```python
'Paying customer must have a Tax ID (VAT) to proceed with clearing payment.'
'Paying customer must have a Tax ID to use auto-fill feature.'
```

### Validation Rules (Updated)
- Customer selection now requires valid Tax ID (vat != False)
- _load_available_invoices() validates Tax ID before filtering
- action_auto_fill_fifo() validates Tax ID before auto-filling

### User Interface Improvements
1. **Step-by-step guidance**: Each step has instructional alert explaining its purpose
2. **Tax ID visibility**: Tax ID prominently displayed throughout wizard
3. **Visual cues**: Selected invoices highlighted in green, unselected in blue
4. **Better column ordering**: Invoice number and date shown first for quick reference
5. **Clearer labels**: All fields clearly labeled with help text where needed

### Business Logic Improvements
- **Multi-branch support**: Correctly handles entities with multiple branches under same Tax ID
- **Audit trail**: All allocations properly attributed to correct customer entities
- **Data integrity**: Tax ID serves as primary grouping criterion
- **User-friendly**: Automatic filtering reduces manual selection errors

### Backward Compatibility
- ✓ No breaking changes
- ✓ All existing fields preserved
- ✓ All existing methods preserved or enhanced
- ✓ Works with existing account configurations
- ✓ Existing clearing payment records unaffected

### Testing Recommendations
1. Test customer selection with and without Tax ID
2. Verify Tax ID filtering works with multiple customers having same Tax ID
3. Test auto-fill FIFO with Tax ID filtering
4. Verify allocation lines clear when paying customer changes
5. Test complete workflow with multi-branch scenario
6. Verify clearing entries post with correct partner references
7. Test with different Tax IDs to ensure proper isolation

### Dependencies
- No new dependencies added
- Leverages existing Odoo 17 fields and features
- Uses standard Odoo API for partner and move queries

### Migration Notes
- No database migration needed
- No existing data changes required
- Tax ID filtering uses existing `vat` field on `res.partner`
- Existing clearing payment records remain unchanged

---

**Author**: AI Assistant
**Date**: January 8, 2026
**Module Version**: 17.0.1.1.0
