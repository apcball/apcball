Marketplace Settlement Module
=============================

This module provides functionality to create settlement entries for marketplace transactions (Shopee, Lazada, TikTok, etc.). It groups multiple customer invoices from a specific trade channel into a single receivable to the marketplace platform.

Features
--------

1. Trade Channel Management: Track sale orders and invoices by trade channel
2. Automatic Invoice Filtering: When selecting a trade channel, the wizard automatically filters relevant invoices
3. Settlement Wizard: Easy-to-use wizard to create marketplace settlements
4. Accounting Integration: Creates proper journal entries for settlement accounting

Installation
------------

1. Place the module in your Odoo addons directory
2. Update the app list in Odoo
3. Install the "Marketplace Settlement (Shopee/Lazada)" module

Usage
-----

Setting Trade Channels on Sale Orders
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Go to Sales > Orders > Quotations
2. Create or edit a sale order
3. Set the Trade Channel field to the appropriate marketplace
4. When invoicing the sale order, the trade channel will automatically be copied to the invoice

Creating a Marketplace Settlement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Go to Accounting > Marketplace > Create Settlement
2. Fill in the settlement details:
   - Settlement Reference: A unique reference for this settlement
   - Trade Channel: Select the marketplace (e.g., Shopee) - this will auto-filter invoices
   - Marketplace Partner: Select the marketplace partner
   - Journal: Select the accounting journal to use
   - Date: Settlement date
3. The wizard will automatically populate invoices matching the selected trade channel
4. Review the filtered invoices in the Invoices tab
5. Click Create Settlement to generate the accounting entries

Example Workflow: Shopee Settlement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Create Sale Orders: Create sale orders with trade channel = "Shopee"
2. Generate Invoices: Create and post invoices from these sale orders
3. Run Settlement: Use the settlement wizard to create settlement entries

What the Settlement Does
~~~~~~~~~~~~~~~~~~~~~~~~

The settlement creates journal entries that:

- Credits each customer's receivable account (reducing what they owe)
- Debits the marketplace partner's receivable account (showing what the marketplace owes you)

This reflects the real-world scenario where customers pay the marketplace and the marketplace pays you in bulk periodically.

Configuration
-------------

Setting Up Marketplace Partners
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Go to Contacts
2. Create partners for each marketplace:
   - Name: "Shopee Marketplace", "Lazada Marketplace", etc.
   - Mark as Customer
   - Set up appropriate Receivable Account

Default Trade Channels
~~~~~~~~~~~~~~~~~~~~~~

The module includes these predefined trade channels:

- Shopee
- Lazada
- Noc Noc
- TikTok
- Other

Technical Details
-----------------

Models Extended
~~~~~~~~~~~~~~~

- sale.order: Added trade_channel field
- account.move: Added trade_channel field

New Models
~~~~~~~~~~

- marketplace.settlement: Stores settlement records
- marketplace.settlement.wizard: Transient model for the settlement wizard

Automatic Features
~~~~~~~~~~~~~~~~~~

- Auto-filtering: When you select a trade channel, invoices are automatically filtered
- Auto-naming: Settlement references are auto-generated based on trade channel and date
- Invoice inheritance: Trade channel is automatically copied from sale order to invoice

Menu Structure
~~~~~~~~~~~~~~

Accounting > Marketplace > Create Settlement (Wizard)
Accounting > Marketplace > Settlement Records (List of created settlements)

Demo Data
---------

The module includes demo data with sample marketplace partners:

- Shopee Marketplace
- Lazada Marketplace  
- TikTok Shop
- Sample customers for each marketplace

Troubleshooting
---------------

No Invoices Found
~~~~~~~~~~~~~~~~~

- Ensure invoices are posted (not draft)
- Verify the trade channel is set on the invoices
- Check that invoices have amount due > 0

Settlement Not Created
~~~~~~~~~~~~~~~~~~~~~~

- Verify all required fields are filled
- Ensure the marketplace partner has a receivable account configured
- Check that customer partners have receivable accounts configured

Support
-------

For technical support or customization requests, contact the module authors.
