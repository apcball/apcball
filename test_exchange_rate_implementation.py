# -*- coding: utf-8 -*-
"""
Test exchange rate implementation for THB per Unit format

Exchange Rate Format Explanation:
- auto_exchange_rate: Odoo's internal decimal format
  Example: 0.030861 (means 1 USD = 0.030861 THB, which is incorrect for real-world scenarios)
  
- auto_exchange_rate_thb: THB per Unit format (inverted)
  Example: 32.45 (means 32.45 THB = 1 USD)
  Calculation: 1 / auto_exchange_rate = 1 / 0.030861 = 32.45
  
- manual_exchange_rate: User input in THB per Unit format
  Example: 32.10 (means 32.10 THB = 1 USD)
  This is what the user enters in the wizard

Conversion Logic:
- From USD 386.13 with manual_exchange_rate 32.10:
  - Amount in THB = 386.13 / 32.10 ≈ 12,026.65 THB
"""

def test_exchange_rate_conversion():
    """Test exchange rate conversion calculations"""
    
    # Example values from the screenshot
    amount_usd = 386.13
    manual_exchange_rate_thb_per_unit = 32.10
    
    # Convert USD to THB using the manual exchange rate
    # Format: manual_exchange_rate is "THB per Unit"
    # So to convert from USD to THB, we divide USD by the rate
    amount_thb = amount_usd / manual_exchange_rate_thb_per_unit
    
    print(f"Amount (USD): {amount_usd}")
    print(f"Manual Exchange Rate: {manual_exchange_rate_thb_per_unit} THB per 1 USD")
    print(f"Amount (THB): {amount_thb:.2f}")
    
    # Exchange rate difference calculation
    # Assume auto rate is 0.030861 (decimal format)
    auto_exchange_rate_decimal = 0.030861
    auto_exchange_rate_thb = 1.0 / auto_exchange_rate_decimal
    
    amount_thb_auto = amount_usd / auto_exchange_rate_thb
    difference = amount_thb - amount_thb_auto
    
    print(f"\nAuto Exchange Rate (decimal): {auto_exchange_rate_decimal}")
    print(f"Auto Exchange Rate (THB per Unit): {auto_exchange_rate_thb:.6f}")
    print(f"Amount (THB) using auto rate: {amount_thb_auto:.2f}")
    print(f"Difference: {difference:.2f} THB")
    
    # Test preview lines calculation
    print("\n--- Journal Entry Preview ---")
    
    po_amount_total = 12511.91  # From screenshot (in USD)
    tax_rate = 0.07  # Assuming 7% tax
    
    total_amount_usd = po_amount_total
    amount_untaxed_usd = total_amount_usd / (1 + tax_rate)
    amount_tax_usd = total_amount_usd - amount_untaxed_usd
    
    # Convert to THB
    total_amount_thb = total_amount_usd / manual_exchange_rate_thb_per_unit
    amount_untaxed_thb = amount_untaxed_usd / manual_exchange_rate_thb_per_unit
    amount_tax_thb = amount_tax_usd / manual_exchange_rate_thb_per_unit
    
    print(f"Total Amount (USD): {total_amount_usd:.2f}")
    print(f"Untaxed Amount (USD): {amount_untaxed_usd:.2f}")
    print(f"Tax Amount (USD): {amount_tax_usd:.2f}")
    print(f"\nTotal Amount (THB): {total_amount_thb:.2f}")
    print(f"Untaxed Amount (THB): {amount_untaxed_thb:.2f}")
    print(f"Tax Amount (THB): {amount_tax_thb:.2f}")

if __name__ == '__main__':
    test_exchange_rate_conversion()
