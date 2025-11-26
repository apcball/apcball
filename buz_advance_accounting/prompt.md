Prompt: Implement JE Logic for Foreign Purchase Goods-in-Transit with FX Difference

Implement only the journal entry (JE) posting logic for the following scenario in Odoo:

Scenario

Company currency: THB

Vendor currency: USD

Purchase is made from a foreign vendor, goods are shipped by sea.

There are 2 main accounting events:

1) Prepayment / Vendor Bill Posting (Goods-in-Transit Recognition)

Business event

On Document Date 1 (e.g. 2025-01-01), the company:

Creates a Vendor Bill in USD.

Pays / recognizes liability to the foreign vendor.

Goods are not yet received (goods are still on the ship).

Accounting logic

When the Vendor Bill is posted:

Get:

usd_amount = total amount in USD.

rate_bill = FX rate on bill date (date 1).

thb_amount_bill = usd_amount * rate_bill.

Post JE:

Debit: Goods in Transit (asset) = thb_amount_bill

Credit: Foreign AP Trade (liability) = thb_amount_bill

Store on the bill (or related model):

usd_amount

rate_bill

thb_amount_bill

You do not need to handle taxes here; focus on the core FX / GIT logic.

2) Goods Arrival Reclassification JE (From Goods in Transit to Inventory / Purchases + FX Difference)

Business event

On Arrival Date (e.g. 2025-01-15), goods actually arrive and are received into stock.

Company wants to:

Remove value from Goods in Transit using the old FX rate (date 1).

Recognize Inventory / Purchases using the new FX rate (arrival date).

Automatically book any exchange difference between these two THB amounts.

Accounting logic

When the goods arrival action is triggered (e.g. on stock.picking validation or a dedicated button):

Retrieve from the linked Vendor Bill (or purchase data):

usd_amount (same USD value as original bill).

rate_bill (FX rate on date 1, stored earlier).

Compute thb_credit_git = usd_amount * rate_bill

This is the THB amount to credit from Goods in Transit.

Determine FX rate on arrival date:

rate_arrival = FX rate on arrival date (date 15).

Compute thb_debit_inventory = usd_amount * rate_arrival

This is the THB amount to debit to Inventory / Purchases.

Compute FX difference:

fx_diff = thb_debit_inventory - thb_credit_git

Logic:

If fx_diff > 0: this is an FX loss (debit Exchange Difference).

If fx_diff < 0: this is an FX gain (credit Exchange Difference, amount = abs(fx_diff)).

If fx_diff == 0: no FX entry is needed.

Build JE lines:

Line 1 (Inventory / Purchases):

Debit: Inventory or Purchase account

Amount = thb_debit_inventory in THB

Line 2 (Goods in Transit):

Credit: Goods in Transit account

Amount = thb_credit_git in THB

Line 3 (FX Difference – optional, only if fx_diff != 0):

If fx_diff > 0 (loss):

Debit: Exchange Difference account = fx_diff

If fx_diff < 0 (gain):

Credit: Exchange Difference account = abs(fx_diff)

Post the JE and link it to:

Vendor Bill

PO

Incoming Shipment

Example Numbers (for testing the logic)

usd_amount = 10,000 USD

At bill date (1 Jan)

rate_bill = 35 THB

thb_credit_git = 10,000 * 35 = 350,000 THB

Bill posting JE:

DR Goods in Transit 350,000

CR Foreign AP Trade 350,000

At arrival date (15 Jan)

rate_arrival = 36 THB

thb_debit_inventory = 10,000 * 36 = 360,000 THB

Reclassification JE:

DR Inventory 360,000

CR Goods in Transit 350,000

CR Exchange Gain 10,000 (because debit > credit, gain is credit)

Deliverable

Implement methods (e.g. in Odoo models) that encapsulate exactly this JE logic:

One method for posting the prepayment / bill JE (GIT vs Foreign AP).

One method for posting the goods arrival JE (GIT vs Inventory + FX difference).

The code must:

Use the stored usd_amount and rate_bill from the Vendor Bill.

Fetch FX rate for the arrival date from currency rates.

Correctly decide whether FX difference is gain or loss and post to the correct side.