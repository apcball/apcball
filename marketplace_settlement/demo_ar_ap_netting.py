#!/usr/bin/env python3
"""
Demo Script: AR/AP Netting in Marketplace Settlement Module
===========================================================

This script demonstrates the complete AR/AP netting workflow for marketplace settlements.

AR/AP Netting Features:
1. Customer invoices (receivables) from marketplace sales
2. Vendor bills (payables) from marketplace partners (e.g., SPX delivery, Shopee fees)
3. Net-off process that reconciles AR against AP
4. Final net payout amount for bank reconciliation

Workflow:
1. Create settlement with customer invoices
2. Import or create vendor bills from marketplace partners
3. Run AR/AP netting to reconcile amounts
4. Bank reconcile only the net payout amount

Example Scenario:
- Customer sales: ฿10,000 (receivable from Shopee)
- SPX delivery fees: ฿800 (payable to SPX)
- Shopee commission: ฿500 (payable to Shopee)
- Net payout: ฿8,700 (amount received from Shopee to bank)

Benefits:
- Simplified bank reconciliation (one net amount vs. multiple transactions)
- Accurate accounting of all marketplace-related transactions
- Automated reconciliation of related AR/AP amounts
- Clear audit trail for marketplace operations
"""

class MarketplaceNettingDemo:
    """
    Demonstration of AR/AP netting functionality
    """
    
    def __init__(self):
        self.scenarios = [
            {
                'name': 'Shopee Settlement with SPX Delivery',
                'customer_invoices': 15000.00,
                'vendor_bills': [
                    {'partner': 'SPX', 'amount': 850.00, 'description': 'Delivery fees'},
                    {'partner': 'Shopee', 'amount': 750.00, 'description': 'Commission'},
                ],
                'expected_net_payout': 13400.00
            },
            {
                'name': 'Lazada Settlement with Multiple Vendors',
                'customer_invoices': 25000.00,
                'vendor_bills': [
                    {'partner': 'Lazada', 'amount': 1250.00, 'description': 'Commission'},
                    {'partner': 'Kerry Express', 'amount': 600.00, 'description': 'Delivery'},
                    {'partner': 'Lazada', 'amount': 200.00, 'description': 'Payment processing'},
                ],
                'expected_net_payout': 22950.00
            }
        ]
    
    def demonstrate_netting(self):
        """
        Show how AR/AP netting calculations work
        """
        print("AR/AP Netting Demonstration")
        print("=" * 50)
        
        for scenario in self.scenarios:
            print(f"\nScenario: {scenario['name']}")
            print("-" * 30)
            
            # Customer receivables
            customer_amount = scenario['customer_invoices']
            print(f"Customer Invoices (AR): ฿{customer_amount:,.2f}")
            
            # Vendor payables
            total_vendor_bills = sum(bill['amount'] for bill in scenario['vendor_bills'])
            print(f"Vendor Bills (AP): ฿{total_vendor_bills:,.2f}")
            
            for bill in scenario['vendor_bills']:
                print(f"  - {bill['partner']}: ฿{bill['amount']:,.2f} ({bill['description']})")
            
            # Net calculation
            net_amount = customer_amount - total_vendor_bills
            print(f"Net Payout: ฿{net_amount:,.2f}")
            
            # Validation
            expected = scenario['expected_net_payout']
            status = "✓ CORRECT" if abs(net_amount - expected) < 0.01 else "✗ ERROR"
            print(f"Expected: ฿{expected:,.2f} - {status}")
    
    def show_accounting_entries(self):
        """
        Show the journal entries created by netting process
        """
        print("\n\nAccounting Entries for AR/AP Netting")
        print("=" * 50)
        
        print("\nBefore Netting:")
        print("Account Receivable - Shopee     Dr ฿15,000")
        print("    Sales Revenue                   Cr ฿15,000")
        print()
        print("Delivery Expense               Dr ฿850")
        print("Commission Expense             Dr ฿750")
        print("    Account Payable - SPX           Cr ฿850")
        print("    Account Payable - Shopee        Cr ฿750")
        
        print("\nNetting Entry:")
        print("Account Payable - SPX          Dr ฿850")
        print("Account Payable - Shopee       Dr ฿750")
        print("    Account Receivable - Shopee     Cr ฿1,600")
        
        print("\nAfter Netting:")
        print("Net Account Receivable - Shopee: ฿13,400")
        print("(This is the amount to reconcile with bank statement)")

if __name__ == '__main__':
    demo = MarketplaceNettingDemo()
    demo.demonstrate_netting()
    demo.show_accounting_entries()
