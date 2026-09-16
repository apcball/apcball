# Installation price + cost on a percentage pricelist (e.g. PROJECT)

## What it does

For a sale order line where **Include Installation** is ticked:

- **Revenue:** `price_unit = <normal pricelist price> + Installation Price`
  The normal pricelist price still comes from the pricelist's own rules — including
  quantity discount tiers on a percentage pricelist. The installation price is added
  **on top**, it does not replace the product price.
- **Cost:** `purchase_price = <standard cost> + Installation Cost`
  So the line margin reflects the installation service profit
  (`Installation Price − Installation Cost` per unit).

`Installation Price` (charged to the customer) and `Installation Cost` (internal) are
**per-product** values kept on the **STANDARD COST pricelist**.

## Setup

1. On the sale pricelist (PROJECT), check **Use Installation Price**
   (Sales → Configuration → Pricelists). Already set for PROJECT.
2. Sales → Products → **Pricelist Product Manager** (matrix).
   - In the left panel pick **STANDARD COST**.
   - Find the product. It must already have a **Fixed Price** row (its standard cost) —
     if it does not, set that first, otherwise the matrix refuses the edit.
   - Set **Installation Price** and **Installation Cost** on that row.
3. On a quotation using the PROJECT pricelist, add the product line, then tick
   **Include Installation** on the line. `price_unit` and the margin update automatically.

## Notes

- You do **not** enter a new selling price on PROJECT for these products — the percentage
  tiers keep working. Per-product **Fixed Price** rules on PROJECT are only for products
  that should ignore the tiers entirely.
- Lines created off-UI (Excel import, API, order duplication) get `price_unit` and
  `purchase_price` re-synced on create/write, not only via the form onchange.
- Price-change history (Sales → Products → History Price) logs Installation Price and
  Installation Cost changes for **fixed** rules only.
