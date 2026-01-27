# Inter-Customer Clearing Payment - Wizard Improvements

## Overview
Implemented advanced wizard functionality for filtering customers and invoices by Tax ID (VAT), enabling efficient allocation of payments across multiple branches/entities with the same Tax ID.

## Key Features Implemented

### 1. Customer Selection with Tax ID Filter
- **Field**: `paying_partner_id` now has domain filter: `domain=[('is_company', '=', True), ('vat', '!=', False)]`
- **Purpose**: Only allows selection of companies with a valid Tax ID
- **Display**: New computed field `paying_partner_tax_id` displays the selected customer's Tax ID
- **User Experience**: Clear visual indication of which Tax ID is being used for filtering

### 2. Tax ID-Based Invoice Filtering
- **Logic**: When user selects a paying customer in Step 1, the wizard automatically:
  1. Retrieves the customer's Tax ID (VAT)
  2. Finds ALL customers with the SAME Tax ID
  3. Loads unpaid and partially paid invoices ONLY from those customers

- **Method**: `_load_available_invoices()` updated with:
  ```python
  # Get all customers with the same Tax ID
  partner_with_same_tax = self.env['res.partner'].search([
      ('vat', '=', self.paying_partner_id.vat),
  ])
  
  # Load invoices from customers with same Tax ID
  invoices = self.env['account.move'].search([
      ('partner_id', 'in', partner_with_same_tax.ids),
      ('state', '=', 'posted'),
      ('move_type', '=', 'out_invoice'),
      ('payment_state', 'in', ['not_paid', 'partial']),
  ])
  ```

### 3. Enhanced Invoice Display
- **New Column**: `partner_tax_id` - Shows Tax ID of each invoice's customer
- **Visual Cues**: 
  - Selected invoices highlighted in dark green
  - Unselected invoices in blue
- **Columns Displayed**:
  - Invoice Number
  - Invoice Date
  - Customer Name
  - **Tax ID (NEW)**
  - Branch
  - Residual Amount
  - Allocation Amount

### 4. Improved Auto-Fill FIFO Feature
- **Enhancement**: Now filters by Tax ID when auto-filling
- **Logic**: 
  1. Gets all customers with same Tax ID
  2. Retrieves their unpaid invoices sorted by date (oldest first)
  3. Auto-allocates payment in FIFO order
  4. Only allocates to invoices from customers with matching Tax ID

### 5. User Experience Enhancements

#### Step 1: Select Paying Customer
- Added instructional alert explaining Tax ID filtering:
  > "Select a customer who is making the payment. The system will automatically find all invoices from customers with the same Tax ID, allowing you to allocate the payment across multiple branches/entities with the same Tax ID."
- Displays selected customer's Tax ID for confirmation
- Prevents quick creation of partners (requires proper setup with Tax ID)

#### Step 2: Select & Allocate Invoices
- Added clear header showing which Tax ID is being filtered:
  > "Below are all unpaid and partially paid invoices from customers with Tax ID: [DISPLAY_TAX_ID]"
- Shows Tax ID for each invoice's customer
- Visual indication of selected vs. unselected invoices

#### Step 3: Review & Confirm
- Displays complete allocation summary
- Shows Tax ID for each invoice customer
- Allows verification of all allocations before posting

## Validation & Error Handling

### New Validations
- **No Tax ID**: Raises error if paying customer has no Tax ID:
  ```
  "Paying customer must have a Tax ID (VAT) to proceed with clearing payment."
  ```
- **Auto-Fill Requirement**: Same validation for auto-fill feature

### On-Change Logic
- When user changes paying customer in Step 1, allocation lines are automatically cleared
- Prevents confusion from stale invoice selections

## Database Schema Changes
None - all improvements use existing fields (`vat`/Tax ID field on res.partner)

## Business Logic Summary

### Before Enhancement
- Loaded ALL unpaid invoices system-wide
- No Tax ID filtering or grouping
- Difficult to identify related entities

### After Enhancement
- Loads ONLY invoices from customers with same Tax ID as paying customer
- Automatic Tax ID-based filtering for branch/entity grouping
- Clear visual representation of Tax ID throughout wizard
- Simplified allocation across multiple branches under same parent entity

## Fields Added to Line Items
- `partner_tax_id`: Displays Tax ID of invoice customer (related field from partner)

## Compatibility
- Works with existing Odoo 17 features
- No breaking changes to existing functionality
- Fully backward compatible with existing payment entries

## Example Use Case

**Scenario**: Company ABC Ltd has three branches:
- ABC Ltd - Bangkok (Tax ID: 0105000000001)
- ABC Ltd - Chiang Mai (Tax ID: 0105000000001)  
- ABC Ltd - Phuket (Tax ID: 0105000000001)

Each branch is a separate customer record in Odoo for P/O and invoice separation.

**Process**:
1. Bangkok branch sends 100,000 THB payment
2. User selects "ABC Ltd - Bangkok" as paying customer
3. Wizard auto-loads invoices ONLY from:
   - ABC Ltd - Bangkok
   - ABC Ltd - Chiang Mai
   - ABC Ltd - Phuket
4. User allocates payment across invoices from any of these branches
5. Creates accounting entries properly attributing payment to correct customer

## Testing Checklist
- [ ] Customer without Tax ID cannot be selected
- [ ] Tax ID displays correctly in Step 1
- [ ] Only invoices from customers with matching Tax ID appear in Step 2
- [ ] Tax ID shows correctly for each invoice in Step 2
- [ ] Auto-fill FIFO uses Tax ID filter
- [ ] Step 3 displays all Tax IDs correctly
- [ ] Allocation works across multiple customers with same Tax ID
- [ ] Clearing entries post with correct partner references
