/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { Warehouse3D } from "@buz_smart_warehouse/js/warehouse3d";
import { WarehouseMap2D } from "@buz_smart_warehouse/js/map2d";

const REFRESH_INTERVAL_MS = 60000;

export class SmartWarehouseDashboard extends Component {
    static template = "buz_smart_warehouse.Dashboard";
    static components = { WarehouseMap2D };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.searchInputRef = useRef("searchInput");
        this.pickingChartRef = useRef("pickingChart");
        this.map3dRef = useRef("map3d");
        this.pickingChart = null;
        this.warehouse3d = null;
        this.refreshTimer = null;

        this.state = useState({
            loading: true,
            view3d: true,
            company: "",
            is_manager: false,
            kpis: {},
            map: { racks: [], docks: [], utilization: {} },
            recommendations: [],
            tasks: [],
            picking_progress: { completed: 0, in_progress: 0, pending: 0 },
            pick_queue: [],
            pickQueueOpen: false,
            receiving_today: [],
            alerts: [],
            // filters
            filters: [],
            warehouseId: false,
            zoneId: false,
            // heatmap
            heatmap: false,
            // audit
            auditOpen: false,
            auditLoading: false,
            audit: null,
            // search
            searchTerm: "",
            searchResults: [],
            searchOpen: false,
            highlightIds: [],
            // layout edit
            editMode: false,
            layoutDirty: false,
            savingLayout: false,
        });
        this.searchTimer = null;

        onWillStart(async () => {
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch (e) {
                console.warn("Chart.js already loaded");
            }
            await loadJS("/buz_smart_warehouse/static/lib/three.min.js");
            await loadJS("/buz_smart_warehouse/static/lib/OrbitControls.js");
            await this.loadData();
        });

        onMounted(() => {
            this.renderPickingChart();
            this.render3d();
            this.refreshTimer = setInterval(async () => {
                if (this.state.editMode) {
                    return; // don't clobber an in-progress layout edit
                }
                const before = JSON.stringify(this.state.map.racks);
                await this.loadData();
                this.renderPickingChart();
                // keep the camera unless rack data actually changed
                if (JSON.stringify(this.state.map.racks) !== before) {
                    this.render3d();
                }
            }, REFRESH_INTERVAL_MS);
        });

        onWillUnmount(() => {
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
            }
            if (this.searchTimer) {
                clearTimeout(this.searchTimer);
            }
            if (this.pickingChart) {
                this.pickingChart.destroy();
            }
            this.destroy3d();
        });
    }

    // ------------------------------------------------------------------
    // 3D map lifecycle
    // ------------------------------------------------------------------
    render3d() {
        this.destroy3d();
        const container = this.map3dRef.el;
        if (!container || !this.state.view3d || !this.state.map.racks.length) {
            return;
        }
        this.warehouse3d = new Warehouse3D(
            container,
            this.state.map.racks,
            (location) => this.openLocation(location.id, location.name),
            {
                docks: this.state.map.docks || [],
                elements: this.state.map.elements || [],
                floor: this.state.map.floor || null,
                onLayoutChange: () => {
                    this.state.layoutDirty = true;
                },
            }
        );
        this.warehouse3d.setEditMode(this.state.editMode);
        this.warehouse3d.setHeatmap(this.state.heatmap);
        if (this.state.highlightIds.length) {
            this.warehouse3d.highlight(this.state.highlightIds);
        }
    }

    destroy3d() {
        if (this.warehouse3d) {
            this.warehouse3d.destroy();
            this.warehouse3d = null;
        }
    }

    reset3dView() {
        if (this.warehouse3d) {
            this.warehouse3d.resetView();
        }
    }

    zoomIn() {
        if (this.warehouse3d) {
            this.warehouse3d.zoom(0.8);
        }
    }

    zoomOut() {
        if (this.warehouse3d) {
            this.warehouse3d.zoom(1.25);
        }
    }

    // ------------------------------------------------------------------
    // Global search
    // ------------------------------------------------------------------
    onSearchInput(ev) {
        const term = ev.target.value;
        this.state.searchTerm = term;
        if (this.searchTimer) {
            clearTimeout(this.searchTimer);
        }
        if (term.trim().length < 2) {
            this.state.searchResults = [];
            this.state.searchOpen = false;
            this.clearSearchHighlight();
            return;
        }
        this.searchTimer = setTimeout(async () => {
            try {
                const results = await this.orm.call(
                    "buz.smart.warehouse.dashboard",
                    "search_stock",
                    [term]
                );
                this.state.searchResults = results;
                this.state.searchOpen = true;
            } catch (error) {
                console.error("SmartWarehouse search failed", error);
                this.notification.add(
                    "ค้นหาไม่สำเร็จ: " + (error.message || error),
                    { type: "danger" }
                );
            }
        }, 300);
    }

    onSearchBlur() {
        // let the click on a result fire before the dropdown closes
        setTimeout(() => {
            this.state.searchOpen = false;
        }, 200);
    }

    onSearchFocus() {
        if (this.state.searchResults.length) {
            this.state.searchOpen = true;
        }
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter" && this.state.searchResults.length) {
            this.selectSearchResult(this.state.searchResults[0]);
        } else if (ev.key === "Escape") {
            this.clearSearchHighlight();
        }
    }

    get hasPositionedLayout() {
        return (
            (this.state.map.racks || []).some(
                (rack) => rack.layout && rack.layout.positioned
            ) || (this.state.map.elements || []).length > 0
        );
    }

    visibleLocationIds() {
        const ids = new Set();
        for (const rack of this.state.map.racks) {
            for (const loc of rack.locations) {
                ids.add(loc.id);
            }
        }
        return ids;
    }

    selectSearchResult(result) {
        this.state.searchOpen = false;
        if (result.type === "picking") {
            this.openReceipt(result.id);
            return;
        }
        // highlight on the map when the stock is visible in the current view
        const visible = this.visibleLocationIds();
        const hits = (result.location_ids || []).filter((id) => visible.has(id));
        if (hits.length) {
            this.state.highlightIds = hits;
            if (this.warehouse3d) {
                this.warehouse3d.highlight(hits);
            }
            return;
        }
        // otherwise open the stock list directly
        if (result.type === "location") {
            this.openLocation(result.id, result.label);
        } else if (result.type === "lot") {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: result.label,
                res_model: "stock.quant",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: [["lot_id", "=", result.id]],
                target: "current",
            });
        } else if (result.type === "product" && result.location_ids.length) {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: result.label,
                res_model: "stock.quant",
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: [
                    ["product_id", "=", result.id],
                    ["location_id.usage", "=", "internal"],
                ],
                target: "current",
            });
        } else if (result.type === "product") {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: result.label,
                res_model: "product.product",
                res_id: result.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    clearSearchHighlight() {
        this.state.highlightIds = [];
        this.state.searchTerm = "";
        this.state.searchResults = [];
        this.state.searchOpen = false;
        if (this.searchInputRef.el) {
            this.searchInputRef.el.value = "";
        }
        if (this.warehouse3d) {
            this.warehouse3d.clearHighlight();
        }
    }

    isHighlighted(locId) {
        return this.state.highlightIds.includes(locId);
    }

    isDimmed(locId) {
        return (
            this.state.highlightIds.length && !this.state.highlightIds.includes(locId)
        );
    }

    // ------------------------------------------------------------------
    // Layout edit mode (Manager)
    // ------------------------------------------------------------------
    toggleEditMode() {
        this.state.editMode = !this.state.editMode;
        if (this.warehouse3d) {
            this.warehouse3d.setEditMode(this.state.editMode);
        }
        if (!this.state.editMode && this.state.layoutDirty) {
            // leaving edit mode without saving: restore server layout
            this.state.layoutDirty = false;
            this.refresh();
        }
    }

    async saveLayout() {
        if (!this.warehouse3d || this.state.savingLayout) {
            return;
        }
        this.state.savingLayout = true;
        try {
            await this.orm.call(
                "buz.smart.warehouse.dashboard",
                "save_layout",
                [this.warehouse3d.getLayout()]
            );
            this.state.layoutDirty = false;
            this.state.editMode = false;
            await this.refresh();
        } finally {
            this.state.savingLayout = false;
        }
    }

    async loadData() {
        const data = await this.orm.call(
            "buz.smart.warehouse.dashboard",
            "get_dashboard_data",
            [this.state.warehouseId || false, this.state.zoneId || false]
        );
        Object.assign(this.state, data, { loading: false });
    }

    // ------------------------------------------------------------------
    // Warehouse / zone filter
    // ------------------------------------------------------------------
    get zones() {
        const warehouse = this.state.filters.find(
            (w) => w.id === this.state.warehouseId
        );
        return warehouse ? warehouse.zones : [];
    }

    async onWarehouseChange(ev) {
        this.state.warehouseId = parseInt(ev.target.value) || false;
        this.state.zoneId = false;
        await this.refresh();
    }

    async onZoneChange(ev) {
        this.state.zoneId = parseInt(ev.target.value) || false;
        await this.refresh();
    }

    // ------------------------------------------------------------------
    // Heatmap
    // ------------------------------------------------------------------
    toggleHeatmap() {
        this.state.heatmap = !this.state.heatmap;
        if (this.warehouse3d) {
            this.warehouse3d.setHeatmap(this.state.heatmap);
        }
    }

    // ------------------------------------------------------------------
    // Audit
    // ------------------------------------------------------------------
    async openAudit() {
        this.state.auditOpen = true;
        this.state.auditLoading = true;
        try {
            this.state.audit = await this.orm.call(
                "buz.smart.warehouse.dashboard",
                "run_audit",
                [this.state.warehouseId || false]
            );
        } finally {
            this.state.auditLoading = false;
        }
    }

    closeAudit() {
        this.state.auditOpen = false;
    }

    auditSeverityClass(severity) {
        return {
            danger: "text-bg-danger",
            warning: "text-bg-warning",
            info: "text-bg-info",
        }[severity] || "text-bg-secondary";
    }

    async refresh() {
        await this.loadData();
        this.renderPickingChart();
        this.render3d();
    }

    toggleView(is3d) {
        this.state.view3d = is3d;
        // wait for OWL to patch the DOM (t-if swaps 2D/3D containers)
        window.requestAnimationFrame(() => this.render3d());
    }

    // ------------------------------------------------------------------
    // Helpers used by the template
    // ------------------------------------------------------------------
    occupancyClass(pct) {
        if (pct === null || pct === undefined) {
            return "swh-tile-unknown";
        }
        if (pct >= 85) {
            return "swh-tile-danger";
        }
        if (pct >= 60) {
            return "swh-tile-warning";
        }
        return "swh-tile-success";
    }

    taskPct(task) {
        return task.total ? Math.round((task.done / task.total) * 100) : 0;
    }

    pickingTotal() {
        const p = this.state.picking_progress;
        return p.completed + p.in_progress + p.pending;
    }

    pickingPct() {
        const total = this.pickingTotal();
        return total
            ? Math.round((this.state.picking_progress.completed / total) * 100)
            : 0;
    }

    statusClass(status) {
        return {
            Received: "text-bg-success",
            Arrived: "text-bg-success",
            "In Transit": "text-bg-info",
            Pending: "text-bg-warning",
            Upcoming: "text-bg-light",
        }[status] || "text-bg-light";
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    openLocation(locationId, locationName) {
        // child_of: parent locations (zones, WH/Stock) hold their stock in
        // child bins, a strict equality on location_id shows nothing there
        this.action.doAction({
            type: "ir.actions.act_window",
            name: locationName,
            res_model: "stock.quant",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["location_id", "child_of", locationId]],
            target: "current",
        });
    }

    togglePickQueue() {
        this.state.pickQueueOpen = !this.state.pickQueueOpen;
    }

    openReceipt(pickingId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "stock.picking",
            res_id: pickingId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    doRecommendation(rec) {
        this.openAction(rec.action);
    }

    openAction(actionDef) {
        if (!actionDef) {
            return;
        }
        if (actionDef.res_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: actionDef.model,
                res_id: actionDef.res_id,
                views: [[false, "form"]],
                target: "current",
            });
        } else {
            this.action.doAction({
                type: "ir.actions.act_window",
                name: actionDef.name || "Records",
                res_model: actionDef.model,
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                domain: actionDef.domain || [],
                context: actionDef.context || {},
                target: "current",
            });
        }
    }

    // ------------------------------------------------------------------
    // Charts
    // ------------------------------------------------------------------
    renderPickingChart() {
        const canvas = this.pickingChartRef.el;
        if (!canvas || typeof Chart === "undefined") {
            return;
        }
        if (this.pickingChart) {
            this.pickingChart.destroy();
        }
        const p = this.state.picking_progress;
        this.pickingChart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: ["Completed", "In Progress", "Pending"],
                datasets: [
                    {
                        data: [p.completed, p.in_progress, p.pending],
                        backgroundColor: ["#2b7fff", "#e8b931", "#d9c6b8"],
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                cutout: "70%",
                plugins: { legend: { display: false } },
                responsive: true,
                maintainAspectRatio: false,
            },
        });
    }
}

registry.category("actions").add("buz_smart_warehouse", SmartWarehouseDashboard);
