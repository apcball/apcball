# Marketplace Settlement - Deductions Feature

## Overview
This module now supports marketplace settlement with automatic deductions for fees, VAT, and withholding tax (WHT). The system automatically creates additional journal entry lines for deductions.

## Features Added

### 1. Deduction Fields
- **Marketplace Fee** (ค่าธรรมเนียม): Fee charged by the marketplace platform
- **VAT on Fee** (ภาษีค่าธรรมเนียม): VAT applied to the marketplace fee
- **Withholding Tax (WHT)** (หัก ณ ที่จ่าย): Tax withheld at source

### 2. Automatic Journal Entry Creation
When creating a settlement, the system now automatically:
- Creates customer receivable lines (credit) for invoice amounts
- Creates deduction lines (debit) for fees, VAT, and WHT
- Creates marketplace receivable line (debit) for net settlement amount
- Net settlement = Total invoices - Total deductions

### 3. Enhanced Views
- **Settlement Wizard**: Added deductions section with account selection
- **Settlement Form**: Added summary showing gross amount, deductions, and net amount
- **Validation**: Ensures deduction accounts are specified when amounts are entered

## Usage

### Creating a Settlement with Deductions
1. Go to **Accounting > Marketplace > Create Settlement**
2. Select trade channel and marketplace partner
3. Add invoices to settle
4. In the **Deductions** section:
   - Enter **Marketplace Fee** amount and select appropriate expense account
   - Enter **VAT on Fee** amount and select appropriate tax account
   - Enter **WHT** amount and select appropriate tax payable account
5. Review the **Settlement Summary** showing net amount
6. Click **Create Settlement**

### Journal Entry Structure
The resulting journal entry will have:
```
Dr. Customer A/R (Customer 1)     XXX
Dr. Customer A/R (Customer 2)     XXX
Dr. Marketplace Fee Expense       XXX
Dr. VAT on Fee                    XXX  
Dr. WHT Payable                   XXX
    Cr. Marketplace A/R (Net)           XXX
```

## Configuration

### Account Setup
Configure the following accounts for deductions:
- **Fee Account**: Expense account for marketplace fees (e.g., 6xxx series)
- **VAT Account**: Tax account for VAT on fees (e.g., 1xxx or 2xxx series)
- **WHT Account**: Tax payable account for withholding tax (e.g., 2xxx series)

### Profile Setup (Optional)
Set up marketplace profiles with default deduction accounts for consistent processing.

## Notes
- Deduction validation ensures accounts are specified when amounts are entered
- Net settlement amount is automatically calculated: Total Invoices - Total Deductions
- All deduction lines are posted with the marketplace partner for proper reporting
- The feature supports both positive and negative settlement amounts
