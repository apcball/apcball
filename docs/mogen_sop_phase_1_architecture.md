# Mogen Smart S&OP Planning Workspace — Phase 1 Architecture

## Scope and boundaries

The workspace is a suite of five standard Odoo 17 addons. It reads operational sales, procurement, stock and manufacturing data through the ORM; it never changes Odoo core and never confirms a purchasing or manufacturing document. Calculations are deterministic, stored per plan/version, and can be reproduced from the retained snapshots.

## Dependency graph

```text
mogen_sop_core
├── mogen_sop_demand (sale_management)
├── mogen_sop_inventory (stock)
└── mogen_sop_supply (demand, stock, purchase, mrp)
    └── mogen_sop_dashboard (core, demand, supply, inventory, web)
```

All addons depend on `base`, `mail`, and `product` either directly or transitively. Every business record has a required `company_id`; warehouse-based records also have an explicit warehouse.

## Models and ownership

| Addon | Models |
| --- | --- |
| Core | `mogen.sop.plan`, `mogen.sop.plan.version`, `mogen.sop.scenario`, `mogen.sop.recommendation`, `mogen.sop.alert`, `res.config.settings` extension |
| Demand | `mogen.sop.demand.plan`, `mogen.sop.demand.line`, `mogen.sop.demand.import.wizard` |
| Inventory | `mogen.sop.inventory.policy`, `mogen.sop.inventory.snapshot`, `mogen.sop.inventory.health`, company S&OP configuration extension |
| Supply | `mogen.sop.supply.plan`, `mogen.sop.supply.line` |
| Dashboard | OWL client action plus a secured dashboard service model/methods |

### Core fields

`mogen.sop.plan`: name, code, company, warehouses, start/end, granularity, scenario, active version, snapshot date, workflow state, owner/manager/approval fields, HTML note, versions, recommendations, alerts. It inherits chatter and activities. SQL constrains `(company_id, code)` and valid dates.

`mogen.sop.plan.version`: name, plan, numeric version, draft/current/archived state, creator/date/note/current flag. A partial unique SQL index makes one current version per plan.

`mogen.sop.scenario`: name/code/company/description/type, four numeric scenario factors, active.

`mogen.sop.recommendation`: plan/company/type/product/warehouse/quantity/date/priority/state/reason/impact/source reference/linked draft PO or MO/approval audit.

`mogen.sop.alert`: name/plan/company/type/severity/product/warehouse/message/state/assignee/resolution date.

## Complete field inventory

| Model | Fields |
| --- | --- |
| `mogen.sop.plan` | `name`, `code`, `company_id`, `warehouse_ids`, `date_start`, `date_end`, `planning_granularity`, `scenario_id`, `active_version_id`, `snapshot_date`, `state`, `user_id`, `manager_id`, `approved_by_id`, `approved_date`, `note`, `version_ids`, `recommendation_ids`, `alert_ids` |
| `mogen.sop.plan.version` | `name`, `plan_id`, `version_number`, `state`, `created_by_id`, `created_date`, `note`, `is_current` |
| `mogen.sop.scenario` | `name`, `code`, `company_id`, `description`, `scenario_type`, `sales_factor`, `lead_time_factor`, `purchase_cost_factor`, `production_capacity_factor`, `active` |
| `mogen.sop.recommendation` | `name`, `plan_id`, `company_id`, `recommendation_type`, `product_id`, `warehouse_id`, `quantity`, `required_date`, `priority`, `state`, `reason`, `impact`, `source_model`, `source_res_id`, `purchase_order_id`, `manufacturing_order_id`, `approved_by_id`, `approved_date` |
| `mogen.sop.alert` | `name`, `plan_id`, `company_id`, `alert_type`, `severity`, `product_id`, `warehouse_id`, `message`, `state`, `assigned_user_id`, `resolved_date` |
| `mogen.sop.demand.plan` | `name`, `sop_plan_id`, `version_id`, `company_id`, `warehouse_ids`, `date_start`, `date_end`, `state`, `line_ids`, `total_forecast_qty`, `total_forecast_value`, `forecast_accuracy`, `forecast_bias` |
| `mogen.sop.demand.line` | `demand_plan_id`, `sop_plan_id`, `version_id`, `company_id`, `warehouse_id`, `product_id`, `product_tmpl_id`, `categ_id`, optional `brand_id`, `period_date`, `historical_qty`, `historical_value`, `system_forecast_qty`, `sales_forecast_qty`, `planner_forecast_qty`, `approved_forecast_qty`, `effective_forecast_qty`, `actual_qty`, `actual_value`, `forecast_variance_qty`, `forecast_accuracy`, `forecast_bias`, `unit_price`, `forecast_value`, `adjustment_note` |
| `mogen.sop.supply.plan` | `name`, `sop_plan_id`, `version_id`, `company_id`, `date_start`, `date_end`, `warehouse_ids`, `state`, `line_ids`, `total_shortage_qty`, `total_shortage_value`, `total_recommended_purchase`, `total_recommended_manufacture` |
| `mogen.sop.supply.line` | `supply_plan_id`, `sop_plan_id`, `version_id`, `company_id`, `warehouse_id`, `product_id`, `categ_id`, `period_date`, `forecast_qty`, `on_hand_qty`, `free_qty`, `reserved_qty`, `incoming_purchase_qty`, `incoming_manufacture_qty`, `outgoing_qty`, `safety_stock_qty`, `projected_qty`, `shortage_qty`, `excess_qty`, `coverage_days`, `procurement_route`, `recommended_qty`, `recommended_date`, `risk_level` |
| `mogen.sop.inventory.policy` | `company_id`, `warehouse_id`, `product_id`, `categ_id`, `safety_stock_qty`, `minimum_stock_qty`, `maximum_stock_qty`, `reorder_point_qty`, `reorder_qty`, `preferred_procurement_route`, `manufacturing_batch_size`, `active` |
| `mogen.sop.inventory.snapshot` | `sop_plan_id`, `version_id`, `company_id`, `warehouse_id`, `product_id`, `snapshot_date`, `on_hand_qty`, `free_qty`, `reserved_qty`, `incoming_qty`, `outgoing_qty`, `stock_value`, `standard_price` |
| `mogen.sop.inventory.health` | `sop_plan_id`, `version_id`, `company_id`, `warehouse_id`, `product_id`, `categ_id`, `average_daily_sales`, `average_monthly_sales`, `on_hand_qty`, `free_qty`, `stock_value`, `coverage_days`, `days_since_last_sale`, `days_since_last_purchase`, `health_status`, `risk_level`, `recommendation` |

### Demand fields

Demand headers retain plan/version/company, warehouse scope, dates, state, lines and stored aggregates/accuracy/bias. Lines retain all stated dimensional fields; brand is optional only when an installed model can be discovered safely. A stored `effective_forecast_qty` selects approved, planner, sales, then system forecast. Lines also retain sales history, actuals, variance, accuracy/bias, unit price/value, and adjustment note.

### Supply and inventory fields

Supply headers retain plan/version/company/date/warehouse/state/lines and stored totals. Supply lines retain all forecast, warehouse stock, incoming/outgoing, policy, projected, shortage/excess, coverage, route, recommendation, and risk fields listed in the requirements.

Inventory policies retain company/warehouse/product/category policy levels, quantities, preferred route, batch size, and active state. Snapshots retain exact quantities/value/cost at a timestamp. Health records retain demand rates, stock/value, coverage, sales/purchase recency, classification, risk, and recommendation. Company-level configuration stores all specified thresholds and defaults.

## Workflow and security

Plan transitions are `draft → data_prepared → review → consensus → approved → locked`; cancellation/reset are explicit controlled transitions. Only managers approve, only approved plans lock, and locked plans reject writes for everyone except administrators. New version atomically archives the current version and establishes a new draft/current version according to the transition action.

| Group | Plan visibility | Demand | Supply/inventory | Approval and documents | Configuration |
| --- | --- | --- | --- | --- | --- |
| Viewer | approved/locked read | read | read | none | none |
| Demand planner | own permitted company plans | create/write | read | none | none |
| Supply planner | permitted company plans | read | create/write + recommendations | none | none |
| Manager | all permitted company plans | write | write | plan/recommendation approval; draft PO/MO | none |
| Administrator | full | full | full | full, including explicit unlock | full |

Global groups imply lower functional roles. Record rules restrict every S&OP business model to `company_id in user.company_ids`; the viewer rule also restricts plan state. Service endpoints validate the selected company and warehouse against the current environment and permitted companies.

## Calculation flow

1. Preparing a plan creates/version-selects demand, supply and snapshot headers and snapshots operational source dates.
2. Demand import aggregates `sale.order.line` from `sale`/`done` orders by product, warehouse and period in default UOM; services and cancellations are excluded, negative return quantities remain negative.
3. A moving average (default 3 months) writes baseline forecast; optional same-period-last-year is an explicit deterministic input. Effective forecast follows the four-level precedence.
4. Inventory snapshot batches stock quants by internal warehouse locations, and batches open incoming/outgoing moves. It never uses global `qty_available` for a warehouse result.
5. Supply joins forecast, snapshot and policy. `projected = free + incoming_purchase + incoming_manufacture - outgoing - forecast`; `shortage = max(0, safety - projected)`; `excess = max(0, projected - maximum)` only with a configured maximum; `coverage = free / average_daily_demand` with safe zero-demand behavior.
6. Recommendations are generated from shortages, route/policy precedence and rounding rules; an open recommendation uniqueness check prevents duplicates. Approval can create only draft PO/MO documents after vendor/BOM validation.
7. Health is batch-classified from stored inventory and demand values using company thresholds. Dashboard methods consume aggregates only and return drill-down domains, not detailed records.

## Implementation sequence

1. Skeletons, manifests, navigation, security groups. **Current review gate.**
2. Core workflow, versioning, security rules, tests.
3. Demand history, forecasts, wizard/views/tests.
4. Policies and inventory snapshots.
5. Supply computations and recommendations.
6. Draft PO/MO actions.
7. Inventory health.
8. OWL dashboard and secured aggregate services.
9. Demo data, documentation, comprehensive tests and installation verification.
