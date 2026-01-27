# Product Installation Cost

## Overview
This module adds optional installation costs to products in sale orders. The installation cost is added AFTER pricelist calculation, ensuring discounts and pricing rules don't affect the installation fee.

## Features
- Add installation cost fields to products (Retail and Project pricing)
- Configure pricelist to use Retail or Project installation pricing
- Installation cost is calculated: `(Product Price after Pricelist Discount) + Installation Cost`

## Example Calculation
- Product price: 100 THB
- Pricelist discount: 5% (for qty >= 5)
- Installation cost: 10 THB
- **Final price**: (100 - 5%) + 10 = 95 + 10 = 105 THB

The installation cost is NOT affected by the 5% discount.

## Configuration
1. Go to Products and set Installation Cost (Retail) and Installation Cost (Project)
2. Go to Pricelists and check either "Is Retail Installation Cost" or "Is Project Installation Cost"
3. In Sale Orders, check "Include Installation" on order lines where needed

## Technical Notes
- Installation cost is added in `_compute_price_unit()` AFTER standard pricelist calculation
- The cost is added directly to `price_unit` after all pricelist rules are applied
- Supports both Retail and Project installation pricing modes
