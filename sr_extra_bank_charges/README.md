# Extra Bank Charges in Thai Baht (THB)

## Overview
This Odoo 17 module allows you to add extra bank charges specifically in Thai Baht (THB) currency during payment registration or manual payment creation, regardless of the invoice or bill currency. This is perfect for businesses that need to accurately record local bank charges in THB even when dealing with foreign currency transactions.

## Features
- **THB-Only Bank Charges**: Bank charge amounts are strictly entered and recorded in Thai Baht.
- **Multi-Currency Support**: Works flawlessly with invoices/bills and payments in any currency (USD, EUR, etc.).
- **Automatic Conversion**: Automatically handles currency conversion for accounting entries. Converts THB charges to both the payment currency and company currency when generating journal entries.
- **Separate Accounting**: Instantiates a separate debit move line specifically for the bank charge amount within the payment's journal entry.
- **Proper Exchange Rates**: Utilizes the system's exchange rates at the payment date for accurate accounting.
- **Informative THB Note**: Displays a convenient read-only note (`bank_charge_thb_note`) displaying the exact THB amount charged directly on the payment form.

## Use Case Example
- Invoice: $1,000 USD
- Bank Charge: 50 THB (local bank fee)
- Result: Payment recorded with proper currency handling. Vendor Payable is debited $1,000 USD, Bank Account is credited $1,000 USD + (50 THB converted to USD), and the designated Bank Charges Account is debited 50 THB (converted to company currency).

## Configuration

### 1. Journal Setup
1. Navigate to **Invoicing / Accounting → Configuration → Journals**.
2. Select your Bank journal.
3. Locate the **Extra Bank Charge Account** field.
4. Choose an appropriate expense account to record these bank charges.

### 2. Currency Setup
- Ensure the **Thai Baht (THB)** currency is active in your system (`base.THB`).
- Set up proper and up-to-date exchange rates for accurate conversion.

## Usage

### In Payment Register Wizard
1. Open a Vendor Bill or Customer Invoice and click **Register Payment**.
2. Select a Bank Journal.
3. Enter the **Bank Charges (THB)** amount.
4. Validate the payment. The system automatically structures the journal items including the converted bank charges.

### In Manual Payments
1. Navigate to **Invoicing / Accounting → Vendors → Payments** or **Customers → Payments**.
2. Create a new payment and select a Bank Journal.
3. Enter the **Bank Charges (THB)** amount in the dedicated field.
4. An informative note will display the THB amount.
5. Confirm the payment.

## Technical Details

### Currency Handling
- Bank charges (`bank_charge_amount`) and its currency (`bank_charge_currency_id`) are persistently set to THB.
- The system logic smoothly converts these figures to the operational company currency for steadfast accounting records.
- Payment line (Credit/Debit side) adjusts to assimilate the bank charge converted into the target payment currency.

### Accounting Entries Structure
```text
Example for Outbound Payment ($1,000 USD Vendor Bill with 50 THB bank charge):
Dr. Vendor Payable Account             $1,000 USD
Cr. Bank Account                       $1,000 USD + (50 THB converted to USD)
Dr. Extra Bank Charge Account              50 THB (converted to company currency)

Example for Inbound Payment ($1,000 USD Customer Invoice with 50 THB fee):
Dr. Bank Account                       $1,000 USD - (50 THB converted to USD)
Dr. Extra Bank Charge Account              50 THB (converted to company currency)
Cr. Customer Receivable Account        $1,000 USD
```

## Installation
1. Copy the `sr_extra_bank_charges` module to your custom addons folder.
2. Update the app list.
3. Search and install the module.
4. Configure the Bank journals appropriately prior to making payments.

## Version History
- **17.0.1.0**: THB-specific bank charges implementation with automatic currency conversions.

## Support
For support and customization, contact Sitaram Solutions at info@sitaramsolutions.in

---
**Author**: Sitaram Solutions  
**Website**: [https://sitaramsolutions.in](https://sitaramsolutions.in)  
**License**: OPL-1