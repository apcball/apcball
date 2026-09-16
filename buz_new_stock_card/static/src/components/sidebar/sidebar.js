/** @odoo-module **/

import { Component, useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { RecordAutocomplete } from "@web/core/record_selectors/record_autocomplete";
import { LocationTree } from "./location_tree";

export class Sidebar extends Component {
    static template = "buz_new_stock_card.Sidebar";
    static components = { RecordAutocomplete, LocationTree };
    static props = [
        "state", "onSelectProduct", "onSelectLocation",
        "onSetDateFrom", "onSetDateTo", "onSetCompany", "onSetWarehouse", "onSearch", "onReset",
        "onToggleShowMovementsOnly",
    ];

    setup() {
        this.orm = useService("orm");
        this.companyService = useService("company");
        this.notification = useService("notification");
        this.local = useState({ warehouses: [], loading: false, error: null });
        this.warehouseRequest = 0;
        this.productRequest = 0;
        onWillUnmount(() => { this.warehouseRequest++; this.productRequest++; });

        onWillStart(async () => {
            await this.loadWarehouses();
        });
    }

    async loadWarehouses() {
        const request = ++this.warehouseRequest;
        this.local.loading = true;
        this.local.error = null;
        this.local.warehouses = [];
        try {
            const warehouses = await this.orm.call(
                "buz.stock.card.report", "get_warehouses", [[this.props.state.companyId]],
                { context: this.companyContext },
            );
            if (request === this.warehouseRequest) { this.local.warehouses = warehouses; }
        } catch (error) {
            if (request === this.warehouseRequest) { this.local.error = "ไม่สามารถโหลดคลังสินค้าได้"; }
        } finally {
            if (request === this.warehouseRequest) { this.local.loading = false; }
        }
    }

    get companyContext() { return { allowed_company_ids: [this.props.state.companyId] }; }
    get productDomain() { return [["company_id", "in", [false, this.props.state.companyId]]]; }

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

    onReset() {
        this.productRequest++;
        this.props.onReset();
    }

    async onUpdateProduct(ids) {
        const request = ++this.productRequest;
        const companyId = this.props.state.companyId;
        if (!ids.length) {
            this.props.onSelectProduct(false, "");
            return;
        }
        try {
            const [product] = await this.orm.read("product.product", [ids[0]], ["display_name"], { context: this.companyContext });
            if (request === this.productRequest && companyId === this.props.state.companyId && product) {
                this.props.onSelectProduct(ids[0], product.display_name);
            }
        } catch (error) {
            if (request === this.productRequest) {
                this.notification.add("ไม่สามารถโหลดข้อมูลสินค้าได้ กรุณาลองใหม่", { type: "danger" });
            }
        }
    }

    onDateFromChange(ev) {
        this.props.onSetDateFrom(ev.target.value);
    }

    onDateToChange(ev) {
        this.props.onSetDateTo(ev.target.value);
    }

    async onCompanyChange(ev) {
        this.productRequest++;
        this.props.onSetCompany(parseInt(ev.target.value, 10));
        await this.loadWarehouses();
    }
}
