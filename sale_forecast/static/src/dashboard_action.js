/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SaleForecastDashboard } from "./dashboard/dashboard";

registry.category("actions").add("sale_forecast_dashboard_action", SaleForecastDashboard);
