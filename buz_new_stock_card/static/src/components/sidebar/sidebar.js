/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { RecordAutocomplete } from "@web/core/record_selectors/record_autocomplete";
import { LocationTree } from "./location_tree";

export class Sidebar extends Component {
    static template = "buz_new_stock_card.Sidebar";
    static components = { RecordAutocomplete, LocationTree };
    static props = [
        "state", "onSelectProduct", "onSelectLocation",
        "onSetDateFrom", "onSetDateTo", "onSetCompany", "onSetWarehouse", "onSearch", "onReset",
    ];

    setup() {
        this.orm = useService("orm");
        this.companyService = useService("company");
        this.local = useState({ productAutoValue: "", warehouses: [] });

        onWillStart(async () => {
            await this.loadWarehouses();
        });
    }

    async loadWarehouses() {
        this.local.warehouses = await this.orm.call(
            "buz.stock.card.report", "get_warehouses",
            [[this.props.state.companyId]]
        );
    }

    onWarehouseChange(ev) {
        this.props.onSetWarehouse(ev.target.value ? parseInt(ev.target.value, 10) : false);
    }

    get companies() {
        return this.companyService.allowedCompanies
            ? Object.values(this.companyService.allowedCompanies)
            : [];
    }

    productGetIds() {
        return this.props.state.productId ? [this.props.state.productId] : [];
    }

    async onUpdateProduct(ids) {
        if (!ids.length) {
            this.props.onSelectProduct(false, "");
            return;
        }
        const [product] = await this.orm.read("product.product", [ids[0]], ["display_name"]);
        this.props.onSelectProduct(ids[0], product.display_name);
    }

    onDateFromChange(ev) {
        this.props.onSetDateFrom(ev.target.value);
    }

    onDateToChange(ev) {
        this.props.onSetDateTo(ev.target.value);
    }

    async onCompanyChange(ev) {
        this.props.onSetCompany(parseInt(ev.target.value, 10));
        await this.loadWarehouses();
    }
}
