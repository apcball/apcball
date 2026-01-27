# Marketplace Settlement - Manual Vendor Bill Configuration

## Overview
The marketplace settlement module now supports **manual vendor bill configuration**, allowing users to set up bills themselves instead of relying on predefined profile configurations.

## Key Features

### 1. Manual Configuration Mode
- **Toggle Option**: Users can switch between profile-based and manual configuration
- **Full Control**: Set your own VAT rates, WHT rates, and account mappings
- **Flexible Setup**: Create bills without requiring pre-configured profiles

### 2. User-Controlled Bill Setup

#### Creating Manual Bills
1. Go to **Accounting > Marketplace Bills > Manual Configuration Bills**
2. Click **Create** to start a new vendor bill
3. Check the **Manual Configuration** option
4. Set your preferred:
   - Trade channel
   - VAT rate (%)
   - WHT rate (%)
   - Vendor partner
   - Journal

#### Switching Configuration Modes
- Use the **Toggle Manual Config** button to switch between modes
- The system will ask if you want to keep existing lines or replace them
- Tax rates will be updated based on the new configuration

### 3. Smart Account Suggestions
The system provides intelligent account suggestions based on line descriptions:
- **Commission** keywords → Commission expense accounts
- **Advertising** keywords → Marketing expense accounts  
- **Logistics/Shipping** keywords → Logistics expense accounts
- **Service** keywords → Service expense accounts

### 4. Enhanced User Interface

#### Form View Features
- **Configuration Toggle**: Easy switching between manual and profile modes
- **Conditional Fields**: Manual rate fields only show when in manual mode
- **Profile Fields**: Profile selection hidden when in manual mode
- **Clear Indicators**: Visual indication of configuration mode

#### List View Features
- **Manual Config Column**: Shows configuration status
- **Advanced Filters**: Filter by manual vs profile configuration
- **Trade Channel Visibility**: Clear channel identification

### 5. Menu Structure
- **Marketplace Documents**: All vendor bill documents
- **Import Documents**: Bulk import functionality
- **Shopee Bills**: Shopee-specific bills
- **Lazada Bills**: Lazada-specific bills
- **TikTok Bills**: TikTok-specific bills
- **Noc Noc Bills**: Noc Noc-specific bills
- **Manual Configuration Bills**: User-configured bills

## Benefits

### For Users
1. **Freedom from Profiles**: No need to wait for profile configuration
2. **Immediate Setup**: Start creating bills right away
3. **Custom Rates**: Set rates specific to your business needs
4. **Learning Tool**: Understand the bill structure better

### For Administrators
1. **Reduced Configuration**: Less need to maintain complex profiles
2. **User Empowerment**: Users can solve their own configuration needs
3. **Flexibility**: Support different business models easily
4. **Gradual Migration**: Can phase out profiles gradually

## Best Practices

### When to Use Manual Configuration
- **New Channels**: When profile doesn't exist yet
- **Custom Requirements**: Special rates or account mappings
- **Testing**: Trying out different configurations
- **One-off Bills**: Unusual or exception cases

### When to Use Profiles
- **Standard Operations**: Regular, repeating bill patterns
- **Team Consistency**: Ensure all users follow same setup
- **Complex Configurations**: Multiple accounts and rules
- **Large Scale**: Many users creating similar bills

## Migration Strategy

### Phase 1: Optional Manual Config (Current)
- Manual configuration available as option
- Profiles remain fully functional
- Users can choose their preferred method

### Phase 2: Profile Deprecation (Future)
- Encourage manual configuration adoption
- Provide training and documentation
- Keep profiles for backwards compatibility

### Phase 3: Profile Removal (Optional Future)
- Remove profile dependency completely
- Simplify codebase and maintenance
- Focus on user-driven configuration

## Technical Implementation

### New Fields
- `use_manual_config`: Boolean flag for configuration mode
- `manual_vat_rate`: User-defined VAT rate
- `manual_wht_rate`: User-defined WHT rate
- `trade_channel`: Direct selection (not profile-dependent)

### Enhanced Logic
- Smart account suggestions based on description keywords
- Configuration switching with line preservation options
- Intelligent default rate setting based on trade channel

### User Interface Improvements
- Conditional field visibility
- Configuration change wizard
- Enhanced filters and search options
