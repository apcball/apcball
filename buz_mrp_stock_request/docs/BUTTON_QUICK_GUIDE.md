# Quick Reference: Stock Request Button on MO

## Visual Guide

### Where to Find It

```
Manufacturing Order Form (WH/MO/00009)
┌─────────────────────────────────────────────────────────┐
│ Manufacturing Orders                                     │
│ WH/MO/00009                                             │
├─────────────────────────────────────────────────────────┤
│ [Produce All] [Plan] [Start] [Check availability]      │
│ [Unreserve] [Cancel] [Stock Request] ← HERE!           │
│                                                          │
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ │
│ ┃ ⚠️ Component Status: Not Available                ┃ │
│ ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ │
│                                                          │
│ Components Tab:                                          │
│ ┌──────────────────────────────────────────────────┐   │
│ │ Product         │ To Consume │ Consumed │ Status │   │
│ ├──────────────────────────────────────────────────┤   │
│ │ Stool Top       │ 30.00      │ 20.00    │ ⚠️     │   │
│ │ Stool Foot      │ 4.00       │ 4.00     │ ✅     │   │
│ └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## What Happens When You Click

### Step 1: Click "Stock Request" Button
```
[Stock Request] ← Click here
```

### Step 2: System Creates Request Automatically
```
Stock Request SR/2025/0001
┌─────────────────────────────────────────────────────────┐
│ Manufacturing Orders: [WH/MO/00009]                      │
│ Source Location: WH/Stock                                │
│ Destination Location: WH/Production                      │
│                                                          │
│ Request Lines: ← Auto-calculated!                       │
│ ┌──────────────────────────────────────────────────┐   │
│ │ Product    │ Requested │ Issued │ Remaining      │   │
│ ├──────────────────────────────────────────────────┤   │
│ │ Stool Top  │ 10.00     │ 0.00   │ 10.00         │   │
│ │            │           │        │ ↑              │   │
│ │            │           │        │ Shortage!      │   │
│ └──────────────────────────────────────────────────┘   │
│                                                          │
│ [Confirm] [Cancel]                                      │
└─────────────────────────────────────────────────────────┘
```

**Note**: System calculated 10.00 because:
- To Consume: 30.00
- Already Consumed: 20.00
- **Shortage: 10.00** ← This is what gets requested

### Step 3: Confirm and Process
```
1. Click [Confirm] → Creates Internal Transfer
2. Process Transfer → Issue 10 units
3. Click [Allocate to MO] → Assign to WH/MO/00009
4. Production continues! ✅
```

## Smart Button

After creating stock requests, a smart button appears:

```
┌─────────────────────────────────┐
│  ┌─────────────────┐            │
│  │  📦 Stock       │            │
│  │  Requests       │            │
│  │  2              │ ← Count    │
│  └─────────────────┘            │
│                                  │
│  Manufacturing Order Details    │
│  ...                            │
└─────────────────────────────────┘
```

Click the smart button to see all stock requests for this MO.

## Button Visibility Rules

| MO State | Button Visible? | Reason |
|----------|----------------|--------|
| Draft | ❌ No | Not confirmed yet |
| Confirmed | ✅ Yes | Can request materials |
| In Progress | ✅ Yes | Production ongoing |
| To Close | ✅ Yes | Finishing up |
| Done | ❌ No | Already complete |
| Cancelled | ❌ No | Not applicable |

## Common Use Cases

### Use Case 1: Running Out During Production
```
Scenario: MO in progress, just realized missing materials

1. Open MO → Click [Stock Request]
2. System shows current shortage
3. Confirm → Warehouse fulfills
4. Allocate → Continue production
```

### Use Case 2: Planning Ahead
```
Scenario: MO confirmed, check what's needed before starting

1. Open MO → Review components
2. Click [Stock Request] if shortages exist
3. Warehouse team processes in advance
4. Start production with materials ready
```

### Use Case 3: Partial Consumption
```
Scenario: Consumed some, need more

Before:
- To Consume: 30
- Consumed: 15
- Need: 15 more

1. Click [Stock Request]
2. System calculates: 30 - 15 = 15
3. Request created for 15 units
4. Process and allocate
```

## Tips

💡 **Tip 1**: The button only appears for confirmed MOs, so confirm your MO first.

💡 **Tip 2**: System automatically calculates shortages based on real-time data, so it's always accurate.

💡 **Tip 3**: You can edit the auto-calculated quantities if needed before confirming.

💡 **Tip 4**: Use the smart button to track all historical stock requests for an MO.

💡 **Tip 5**: If you need materials for multiple MOs, create one request and add more MOs to it.

## Troubleshooting

**Q: Button doesn't appear?**
- Check if MO is confirmed (state must be Confirmed/In Progress/To Close)

**Q: No lines created?**
- All components are already available
- System shows message: "No shortages found"

**Q: Wrong quantities calculated?**
- Check "To Consume" vs "Consumed" on MO components
- Verify UoM conversions are correct
- Check system parameter: `mrp_stock_request.shortage_policy`

**Q: Can't find the button?**
- Module must be installed: `buz_mrp_stock_request`
- Upgrade module if recently installed
- Check user has access rights

---

**Quick Access**: Manufacturing → Manufacturing Orders → Open any MO → [Stock Request]
