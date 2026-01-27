# Extra Bank Charges in Thai Baht (THB)

## Overview
This Odoo module allows you to add bank charges specifically in Thai Baht (THB) currency, regardless of the invoice or bill currency. Perfect for businesses that need to record local bank charges in THB even when dealing with foreign currency transactions.

## Features
- **THB-Only Bank Charges**: Bank charges are always entered and recorded in Thai Baht
- **Multi-Currency Support**: Works with invoices/bills in any currency (USD, EUR, etc.)
- **Automatic Conversion**: Handles currency conversion for accounting entries
- **Separate Accounting**: Creates separate journal entries for bank charges
- **Proper Exchange Rates**: Uses system exchange rates for accurate accounting

## Use Case Example
- Invoice: $1,000 USD
- Bank Charge: 50 THB (local bank fee)
- Result: Payment recorded with proper currency handling

## Configuration

### 1. Journal Setup
1. Go to **Invoicing → Configuration → Journals**
2. Select your Bank journal
3. Set the **Extra Bank Charge Account** field
4. Choose an appropriate expense account for bank charges

### 2. Currency Setup
- Ensure Thai Baht (THB) currency is active in your system
- Set up proper exchange rates for accurate conversion

## Usage

### In Payment Register Wizard
1. Create a payment from vendor bill or customer invoice
2. Enter the **Bank Charges (THB)** amount
3. The system automatically handles currency conversion

### In Manual Payments
1. Go to **Invoicing → Vendors → Payments** or **Invoicing → Customers → Payments**
2. Create a new payment
3. Enter the **Bank Charges (THB)** amount in the dedicated field

## Technical Details

### Currency Handling
- Bank charges are stored in THB currency
- System converts to company currency for accounting entries
- Payment amount is adjusted accordingly in the payment currency

### Accounting Entries
```
Example for $1,000 USD payment with 50 THB bank charge:

Dr. Vendor Payable Account    $1,000 USD
Cr. Bank Account             $1,000 USD + (50 THB converted to USD)
Dr. Bank Charges Account      50 THB (converted to company currency)
```

## Installation
1. Copy the module to your custom addons folder
2. Update the app list
3. Install the module
4. Configure the bank journals

## Version History
- **17.0.1.0**: THB-specific bank charges implementation
- **17.0.0.0**: Original version

## Support
For support and customization, contact Sitaram Solutions at info@sitaramsolutions.in

---
**Author**: Sitaram Solutions  
**Website**: https://sitaramsolutions.in  
**License**: OPL-1