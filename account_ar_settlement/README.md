# AR Settlement Engine

## Overview
Advanced Accounts Receivable Settlement Engine for Odoo 17.
This module enhances Odoo's default payment allocation by introducing a comprehensive AR Settlement interface that allows users to manage complex payment scenarios, such as settling invoices across different branches sharing the same VAT ID, handling e-commerce trade channel payouts, applying credit notes, and automatically handling bank fees and payment differences.

## Key Features
- **Customer Payment Allocation**: Allocate received amounts to specific invoices manually or using the FIFO Auto-Allocate feature.
- **Credit Note Allocation**: Automatically load and apply open customer credit notes against due invoices to reduce the required payment amount.
- **VAT Group Settlement**: Settle invoices across different partner branches (contacts) that share the same VAT ID. The module automatically handles the inter-customer clearing journal entries.
- **Trade Channel Filtering**: Filter and load invoices based on predefined trade channels (e.g., Shopee, Lazada, Noc Noc, Tiktok, SPX, Line, Facebook, Offline Outlet).
- **Bank Fee Support**: Record bank or gateway fees directly during settlement. The system will create the appropriate expense journal items (Dr Bank Fee).
- **Payment Difference Handling**: Automatically handle overpayments and underpayments. Choose between treating differences as Customer Credit, Write-Off, or Partial Payment.
- **Posting Preview**: View a dynamic HTML preview of the resulting journal entry lines (Debit/Credit) before confirming the settlement.

## Configuration
1. Go to **Accounting → Configuration → Settings**.
2. Scroll to the **AR Settlement** section.
3. Set the **Payment Difference Account** (default is usually set to `214100 Accrued Expenses`). This account will be used to post any write-offs arising from payment differences.

## Usage
1. Navigate to **Accounting → Customers → AR Settlement**.
2. Create a new settlement record.
3. Select the **Customer**, **Payment Date**, **Payment Journal**, and **Trade Channel** (optional).
4. Enter the total **Amount Received** in the bank and any applicable **Bank Fee**.
5. Click **Load Invoices**. The system will fetch open invoices and open credit notes matching the customer's VAT group and the selected trade channel (if any).
6. Check the lines you wish to pay, or click the **Auto Allocate** button to automatically distribute the available amount (Amount Received + Credit Notes) to the oldest invoices first.
7. Select the **Difference Handling** method if the allocated amount does not exactly match the received amount plus applied credits.
8. Review the **Posting Preview** at the bottom of the form.
9. Click **Confirm**.

The system will automatically:
- Create and post an Inbound Payment.
- Adjust the payment's journal entry to account for bank fees and payment differences.
- Reconcile the payment with the selected invoices.
- Create inter-customer clearing journal entries if settling invoices belonging to different branches under the same VAT group.

## Dependencies
This module strictly depends on:
- `account`
- `mail`
- `sale`

## Technical Details
- **Menus**: Accounting → Customers → AR Settlement (`view_ar_settlement_form`, `view_ar_settlement_tree`).
- **Models**:
  - `ar.settlement`: The main settlement document.
  - `ar.settlement.line`: Invoice allocation lines.
  - `ar.settlement.credit.line`: Credit note allocation lines.
- **Inter-Customer Clearing**: When a payment from Customer A is applied to an invoice for Customer B (same VAT group), the module generates a clearing journal entry (`Dr AR [Customer A] / Cr AR [Customer B]`) to balance specific partner ledgers while correctly completing the reconciliation.

## Author 
Custom

## License 
LGPL-3
