---
category: pos
created: 2026-05-19
sources: "[\"session-pos-ecosystem-dev\"]"
tags: [Odoo17, POS, Retail, Delivery, OWL, frontend]
title: Buz POS Ecosystem Architecture
topic: Full-featured Retail POS system for Odoo 17 with delivery, promotions, loyalty, retail UI, reports, and integrations
updated: 2026-05-19
---

# Buz POS Ecosystem Architecture
Description: Full-featured Retail POS system for Odoo 17 with delivery, promotions, loyalty, retail UI, reports, and integrations
---

## Overview

Buz POS เป็นระบบ Point-of-Sale แบบ full-featured สำหรับธุรกิจ Retail บน Odoo 17 ออกแบบเป็น modular ecosystem 7 modules:

## Module Dependency Graph

```
point_of_sale (Odoo Core)
    └── buz_pos_core (base + OWL components)
        ├── buz_pos_delivery (delivery management)
        ├── buz_pos_promotion (discount rules + coupons)
        ├── buz_pos_loyalty (points + tiers)
        ├── buz_pos_retail_ui (retail-optimized UI)
        ├── buz_pos_reports (X/Z report + analytics)
        └── buz_pos_integration (hardware + LINE + PromptPay)
```

## Modules

### 1. buz_pos_core
**Base POS enhancement**
- Extend `pos.config` with settings: multi-payment, order notes, line discount, QR receipt, delivery toggle, stock display
- Extend `pos.order` with: order note, delivery info, source tracking, delivery status
- Extend `pos.order.line` with: line note, discount reason
- OWL frontend: ProductScreen patch, PaymentScreen patch, ReceiptScreen patch, OrderWidget patch, models.js patch
- CSS: Touchscreen-optimized retail UI
- Report: Session Summary PDF

### 2. buz_pos_delivery
**Delivery management**
- Models: `buz.delivery.zone` (zone + fee), `buz.delivery.driver` (driver + vehicle + status), `buz.delivery.order` (full delivery workflow)
- Workflow: pending → assigned → picking → delivering → delivered
- Driver status tracking (available/busy/offline)
- OWL: DeliveryPopup (address, phone, zone, fee calc), DeliveryScreen button
- Auto-create delivery order when POS order confirmed
- Kanban board for delivery dashboard

### 3. buz_pos_promotion
**Promotion engine**
- Models: `buz.promotion.rule` (discount %, fixed, buy X get Y, time-based), `buz.promotion.coupon` (code + usage tracking)
- Time-based promotions (happy hour, specific day)
- Auto-apply or coupon-based
- OWL: PromotionPopup (coupon code input), PromotionEngine (auto-apply logic)

### 4. buz_pos_loyalty
**Loyalty & points**
- Models: `buz.loyalty.tier` (Bronze/Silver/Gold/Platinum), `buz.loyalty.card` (points tracking), `buz.loyalty.transaction` (earn/redeem/adjust)
- Auto tier upgrade based on accumulated points
- Default tiers: Bronze (0), Silver (500), Gold (2000), Platinum (5000)
- Points earn/redeem on POS order completion
- OWL: LoyaltyWidget (points display), RedeemPopup (redeem points as discount)

### 5. buz_pos_retail_ui
**Retail-optimized frontend**
- Category Tiles: Touch-friendly category navigation (small/medium/large)
- QuickSearchBar: Instant product search with barcode support
- ProductVariantGrid: Variant selector popup
- CustomerPanel: Customer-facing display (dark theme)
- Config: tile size, show images, show price, show stock badge, customer display toggle

### 6. buz_pos_reports
**Analytics & reports**
- X-Report: Mid-session summary (orders, revenue, payment breakdown, hourly, source)
- Z-Report: End-of-session final (revenue, discounts, refunds, delivery, top products)
- Product Ranking: By revenue and by quantity
- All reports as QWeb PDF
- Buttons on POS Session form

### 7. buz_pos_integration
**Hardware & external**
- ESC/POS: Network thermal printer connection (IP + port), receipt command builder (58mm/80mm)
- Barcode Scanner: Keyboard event listener (auto-detect rapid keystrokes), product lookup
- PromptPay QR: EMVCo format QR payload generation with CRC16
- LINE Notify: Order notification via LINE OA, delivery status notification

## Key Technical Decisions

- **OWL `patch` mechanism**: All frontend extensions use `patch()` instead of class inheritance
- **`_inherit` for models**: Extend existing Odoo models with `_inherit`
- **`export_as_JSON` / `init_from_JSON`**: Sync custom fields between frontend and backend
- **Multi-company**: All models have `company_id` + record rules
- **Security**: ACL per user/manager group, record rules for company isolation
- **Touch-friendly**: All buttons min 44px, large touch targets, responsive grid

## Data Models Summary

| Model | Module | Purpose |
|-------|--------|---------|
| pos.config (+) | core | POS settings |
| pos.order (+) | core/delivery/promotion/loyalty | Order with delivery, promo, loyalty |
| pos.order.line (+) | core | Line notes, discount reasons |
| res.partner (+) | core | Driver info, loyalty points |
| product.product (+) | core | POS sequence, best seller, color |
| buz.delivery.zone | delivery | Zone + fee |
| buz.delivery.driver | delivery | Driver + vehicle + status |
| buz.delivery.order | delivery | Full delivery tracking |
| buz.promotion.rule | promotion | Promotion rules |
| buz.promotion.coupon | promotion | Coupon codes |
| buz.loyalty.tier | loyalty | Tier levels |
| buz.loyalty.card | loyalty | Customer loyalty card |
| buz.loyalty.transaction | loyalty | Point transactions |

## File Statistics

- 7 modules created
- ~60+ files total
- Backend: Python models, views, security, reports
- Frontend: OWL JS components, QWeb XML templates, CSS
