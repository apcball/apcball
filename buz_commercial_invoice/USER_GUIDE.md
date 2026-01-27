# User Guide: Commercial Invoice Module

## How to Generate a Commercial Invoice

### Step 1: Open Sale Order (Quotation)
1. Go to **Sales > Orders > Quotations** (or **Sales > Orders**)
2. Click on any quotation/sale order to open it
3. Or create a new quotation

### Step 2: Navigate to Commercial Invoice Tab
- You will see a new tab labeled **"Commercial Invoice"** on the form
- This tab appears after the main order details tab

### Step 3: Enable Commercial Invoice
```
Commercial Invoice Tab
├── □ Generate Commercial Invoice  [Click to enable]
├── Commercial Invoice No. _________ [Auto-filled when enabled]
├── Incoterms _____________________
├── Loading Date __________________
├── Shipping Mark __________________
├── Shipping By ____________________
└── Bank Information _______________
```

1. Check the box **"Generate Commercial Invoice"**
   - Automatically generates a unique CIV number (e.g., CIV-000001, CIV-000002, etc.)
   - The number appears in "Commercial Invoice No." field

### Step 4: Fill Optional Information
- **Incoterms**: Select freight terms (FOB, CIF, etc.)
- **Loading Date**: When goods will be shipped
- **Shipping Mark**: Identification mark on packages (default: MOGEN)
- **Shipping By**: Transportation method (By Air, By Sea, By Land)
- **Bank Information**: Bank details for payment

### Step 5: Print Commercial Invoice
Option A - From Sale Order:
1. Click the **"Print Commercial Invoice"** button in the Commercial Invoice tab
2. PDF will be generated and printed

Option B - From Report Menu:
1. Open the sale order
2. Click **Print** menu at top
3. Select **Commercial Invoice**

## Example CIV Number Generation

```
Sale Order 1 → Check "Generate Commercial Invoice" → CIV-000001
Sale Order 2 → Check "Generate Commercial Invoice" → CIV-000002
Sale Order 3 → Check "Generate Commercial Invoice" → CIV-000003
...
Sale Order N → Check "Generate Commercial Invoice" → CIV-00000N
```

Each time the checkbox is marked, the next sequence number is assigned.

## Commercial Invoice Report Contents

The generated report includes:

```
┌─────────────────────────────────────────────────────────┐
│  [LOGO]        MOGEN CO.,LTD. - COMMERCIAL INVOICE    │
│                         CIV-000001                      │
├─────────────────────────────────────────────────────────┤
│  Date & References:                                     │
│  - Document Date, Shipper, Consignee, Contact Info    │
│  - Tax ID, Incoterms, Bank Info                       │
│  - Shipping Details (Loading Date, Mark, Method)      │
├─────────────────────────────────────────────────────────┤
│  Item Details Table:                                    │
│  ┌──┬─────────────┬─────────┬──────┬────────────┐     │
│  │# │ Description │ Qty     │ Unit │ Amount     │     │
│  ├──┼─────────────┼─────────┼──────┼────────────┤     │
│  │1 │ Product A   │ 100 pcs │ $10  │ $1,000.00  │     │
│  │2 │ Product B   │ 50 pcs  │ $20  │ $1,000.00  │     │
│  │  │ TOTAL       │ 150 pcs │ -    │ $2,000.00  │     │
│  └──┴─────────────┴─────────┴──────┴────────────┘     │
├─────────────────────────────────────────────────────────┤
│  Totals & Bank Info:                                    │
│  Amount in Words: Two Thousand US Dollars              │
│  Bank: Kasikorn Bank (KBANK)                           │
│  Account: MOGEN CO.,LTD.                               │
│  Account Number: 464-1-00774-4                         │
│  Grand Total: $2,000.00                                │
├─────────────────────────────────────────────────────────┤
│  Approvals:                                             │
│  Processed By: ________________                        │
│  Approved By:  ________________                        │
└─────────────────────────────────────────────────────────┘
```

## Benefits

✓ **Independent from Invoices**: Can print commercial invoice even without creating an invoice
✓ **Sequential Numbering**: CIV- numbers automatically assigned
✓ **Professional Format**: Complete invoice details with signatures
✓ **Custom Fields**: Add shipping and payment terms specific to export
✓ **Automatic Computation**: Amount in words calculated automatically
✓ **Easy to Use**: Simple checkbox to enable, automatic number generation

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Print Commercial Invoice" button not visible | Make sure "Generate Commercial Invoice" checkbox is checked |
| CIV number not generated | Check "Generate Commercial Invoice" checkbox - it will trigger number generation |
| Report not printing | Ensure sale order has customer and products defined |
| Bank information not showing | Fill in bank information in the Bank Information field |

## Key Differences from Invoice

| Feature | Commercial Invoice | Sales Invoice |
|---------|-------------------|---------------|
| Created from | Sale Order | Sales Invoice |
| Number prefix | CIV- | INV- |
| Required fields | Only requires Sale Order | Requires Posted Invoice |
| Use case | Export/Shipping documents | Tax/Accounting records |
| Can print without invoice | Yes | No |
