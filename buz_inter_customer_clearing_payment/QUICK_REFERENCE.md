# Quick Reference Guide - Wizard Tax ID Filtering

## Feature Overview
Automatic filtering of customers and invoices by Tax ID (VAT) in the Inter-Customer Clearing Payment Wizard.

---

## How It Works in 3 Steps

### STEP 1: Select Paying Customer
1. Open: **Accounting → Customers → Receive Clearing Payment**
2. Select a **Company customer WITH a Tax ID (VAT)**
3. System displays the selected customer's Tax ID automatically
4. Enter payment details: Journal, Amount, Date, Reference
5. Click **Next**

### STEP 2: Select & Allocate Invoices
1. System shows **only invoices from customers with the SAME Tax ID**
2. Review invoice list:
   - **Invoice Number** & **Date** (identify invoice)
   - **Customer Name** (which branch)
   - **Tax ID** (confirms filtering)
   - **Branch** (optional, from analytic account)
   - **Residual Amount** (amount still unpaid)
   - **Allocation Amount** (how much to apply)

3. Select invoices and enter allocation amounts:
   - ✓ Check the "Selected" checkbox
   - ✓ Enter amount to allocate (auto-fills with full residual)
   - ✓ Can use **Auto-fill FIFO** button to auto-allocate from oldest

4. Click **Next** to proceed to review

### STEP 3: Review & Confirm
1. Review payment summary and allocations
2. Verify all Tax IDs match (they should)
3. Click **Confirm & Post** to create payment and clearing entries

---

## Key Features

### Automatic Tax ID Grouping
```
Scenario: Customer ABC Ltd has 3 branches, all with Tax ID: 0105000000001
├─ ABC Ltd - Bangkok       (Tax ID: 0105000000001)
├─ ABC Ltd - Chiang Mai    (Tax ID: 0105000000001)
└─ ABC Ltd - Phuket        (Tax ID: 0105000000001)

When you select "ABC Ltd - Bangkok":
  ↓
All invoices from Bangkok, Chiang Mai, AND Phuket appear
  ↓
You can allocate one payment across all branches
```

### Visual Cues
- **Green rows**: Selected invoices (will be allocated)
- **Blue rows**: Unselected invoices (will not be allocated)
- **Tax ID column**: Shows which customer each invoice belongs to

### Smart Features
- **Auto-clear**: If you change the paying customer, allocation list clears (prevents mix-ups)
- **Auto-fill FIFO**: Automatically allocates to oldest unpaid invoices first
- **Clear Allocation**: Button to reset all selections if needed

---

## Important Rules

### ✓ MUST HAVE
- Paying customer **MUST** have a Tax ID (VAT)
- If not, error: "Paying customer must have a Tax ID (VAT)"

### ✓ ALLOWED
- Multiple invoices from same customer
- Invoices from different customers (if same Tax ID)
- Partial allocations (allocate less than full residual)
- Zero allocation (don't select invoice, allocate = 0)

### ✗ NOT ALLOWED
- Customers without Tax ID
- Allocating more than remaining amount
- Allocating to invoices from customers with different Tax ID

---

## Field Descriptions

| Field | Step | Purpose |
|-------|------|---------|
| **Paying Customer** | 1 | Which customer is sending the payment |
| **Tax ID** | 1, 2, 3 | Identifies the customer group (auto-filtered) |
| **Journal** | 1 | Bank or cash account receiving payment |
| **Amount** | 1 | Total payment amount |
| **Date** | 1 | Payment date |
| **Reference** | 1 | Optional note/reference number |
| **Invoice Number** | 2 | Which invoice (from which branch) |
| **Customer** | 2 | Which branch/entity the invoice belongs to |
| **Tax ID** | 2 | Confirms it matches paying customer's Tax ID |
| **Residual Amount** | 2 | Amount still owed on invoice |
| **Allocate Amount** | 2 | How much of payment to apply to this invoice |

---

## Common Tasks

### Task 1: Allocate Payment to Oldest Invoices First
```
1. Go to Step 2
2. Click "Auto-fill FIFO" button
3. System auto-selects invoices in date order
4. Review allocations
5. Click Next → Confirm & Post
```

### Task 2: Manually Select Specific Invoices
```
1. Go to Step 2
2. Check "Selected" box for each invoice you want
3. Enter allocation amount (or leave for auto-fill)
4. Repeat for all desired invoices
5. Click Next → Confirm & Post
```

### Task 3: Change Allocation Amount
```
1. Go to Step 2
2. Click on "Allocate Amount" field for that invoice
3. Type new amount
4. Click outside field (auto-saves)
5. Total Allocated updates automatically
```

### Task 4: Clear and Start Over
```
1. Go to Step 2
2. Click "Clear Allocation" button
3. All selections reset
4. Start fresh with manual selection
```

---

## Error Messages & Solutions

### Error: "Paying customer must have a Tax ID (VAT)"
**Cause**: Selected customer doesn't have a Tax ID
**Solution**: 
1. Go back to Step 1
2. Select a different customer
3. Verify that customer has Tax ID filled in (Check: Contacts/Companies, Tax ID field)
4. If no Tax ID exists, create one or choose different customer

### Error: "Allocation amount cannot exceed residual amount"
**Cause**: You entered more than the invoice balance
**Solution**:
1. Go back to Step 2
2. Reduce allocation amount to ≤ residual amount
3. Residual amount shown in "Residual Amount" column

### Error: "Please select at least one invoice to allocate"
**Cause**: You clicked Next without selecting any invoices
**Solution**:
1. Go back to Step 2
2. Check "Selected" box for at least one invoice
3. Enter allocation amount
4. Click Next again

---

## Tips & Tricks

### TIP 1: Use Tab to Navigate
- Press **Tab** to move between cells in invoice table
- **Shift+Tab** to go backward
- **Enter** to confirm and move down

### TIP 2: Quick Selection
- Click **Selected** column header to toggle all at once
- Then uncheck specific ones you want to exclude

### TIP 3: Use Auto-fill Then Edit
1. Click "Auto-fill FIFO" to auto-select
2. Manually adjust amounts as needed
3. Often faster than manual selection

### TIP 4: Check Remaining Amount
- **Remaining Amount** shows unallocated portion
- If > 0, you have payment left unallocated
- This is OK - you can leave it as advance

---

## Approval Process (if configured)

Some Odoo installations require approval for payments:
1. After clicking "Confirm & Post", payment may be created in draft
2. Manager/Approver must review and approve
3. Once approved, payment posts and clearing entries created
4. Invoices then show as partially/fully paid

---

## Audit Trail

The system creates an audit trail automatically:
- **Payment record**: Shows paying customer and total amount
- **Clearing entries**: Shows which customer got credit for each invoice
- **Invoice status**: Changes from "Unpaid" to "Paid" or "Partial"
- **General Ledger**: Shows debit/credit to correct customers

---

## Testing Checklist

Before deploying to production:
- [ ] Test with customer that has Tax ID
- [ ] Test with customer without Tax ID (should error)
- [ ] Test with 3+ branches having same Tax ID
- [ ] Test auto-fill FIFO
- [ ] Test manual selection
- [ ] Test partial allocation
- [ ] Test clear allocation
- [ ] Verify clearing entries post correctly
- [ ] Check GL shows correct customer credits
- [ ] Verify invoices show as paid/partial

---

## Frequently Asked Questions

**Q: Can I allocate to invoices from different customers?**
A: Yes, as long as they ALL have the same Tax ID. System automatically filters.

**Q: What if branches have DIFFERENT Tax IDs?**
A: You must run separate clearing payments - one for each Tax ID.

**Q: Can I change Tax ID of a customer?**
A: Yes, but existing invoices will no longer be filtered together. Create new customers for new Tax IDs.

**Q: What happens to remaining amount?**
A: It stays in the paying customer's account as an advance/credit.

**Q: Can I reverse/cancel a clearing payment?**
A: Yes - use Payment → Cancel or reverse transaction. Contact accounting for guidance.

**Q: How many invoices can I allocate in one payment?**
A: No limit - allocate to as many as needed.

**Q: Can I allocate 0 amount to an invoice?**
A: Yes - don't select it or select and enter 0. Same effect.

---

## Support & Troubleshooting

### Contact Information
- **For module issues**: Check IMPROVEMENTS.md and CHANGELOG.md
- **For accounting questions**: Contact your Finance/Accounting Manager
- **For system access**: Contact IT/Odoo Administrator

### Common Troubleshooting
1. **Invoices not showing?**
   - Check Tax ID matches paying customer
   - Verify invoices are posted (not draft)
   - Verify invoices not fully paid already

2. **Auto-fill not working?**
   - Ensure paying customer has Tax ID
   - Ensure invoices exist with same Tax ID
   - Check amount is not zero

3. **Payment not posting?**
   - Check journal is valid (bank or cash)
   - Check amount is positive
   - Check company has GL accounts configured

---

**Last Updated**: January 8, 2026
**Module Version**: 17.0.1.1.0
**Odoo Version**: 17
