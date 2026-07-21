/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const SNAP = 0.5; // meters
const MIN_FLOOR_W = 70; // minimum canvas size in meters
const MIN_FLOOR_H = 45;
const MARGIN = 8;

export const RACK_TYPES = [
    { id: "selective", label: "Selective Rack", icon: "fa-th" },
    { id: "drive_in", label: "Drive-in Rack", icon: "fa-sign-in" },
    { id: "double_deep", label: "Double Deep", icon: "fa-align-justify" },
    { id: "push_back", label: "Push Back Rack", icon: "fa-arrow-left" },
    { id: "cantilever", label: "Cantilever Rack", icon: "fa-indent" },
    { id: "pallet_flow", label: "Pallet Flow Rack", icon: "fa-forward" },
];

export const ZONE_TYPES = [
    { id: "receiving", label: "รับสินค้า (Receiving)", color: "#3b82f6" },
    { id: "storage", label: "จัดเก็บ (Storage)", color: "#22c55e" },
    { id: "picking", label: "หยิบสินค้า (Picking)", color: "#f97316" },
    { id: "packing", label: "บรรจุ (Packing)", color: "#8b5cf6" },
    { id: "shipping", label: "ส่งสินค้า (Shipping)", color: "#94a3b8" },
    { id: "finished_goods", label: "สินค้าสำเร็จรูป (FG)", color: "#eab308" },
];

const ZONE_COLORS = Object.fromEntries(ZONE_TYPES.map((z) => [z.id, z.color]));

const TOOLS = [
    { id: "select", label: "Select / Move", icon: "fa-mouse-pointer" },
    { id: "add_rack", label: "Add Rack", icon: "fa-th-large" },
    { id: "add_shelf", label: "Add Shelf", icon: "fa-bars" },
    { id: "add_dock", label: "Add Dock", icon: "fa-truck" },
    { id: "add_zone", label: "Add Zone", icon: "fa-object-group" },
    { id: "add_aisle", label: "Add Aisle", icon: "fa-road" },
    { id: "add_obstacle", label: "Add Obstacle", icon: "fa-ban" },
    { id: "add_forklift", label: "Add Forklift", icon: "fa-truck" },
    { id: "add_text", label: "Add Text", icon: "fa-font" },
];

let tmpSeq = 1;

export class WarehouseLayoutDesigner extends Component {
    static template = "buz_smart_warehouse.LayoutDesigner";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.svgRef = useRef("svg");
        this.canvasRef = useRef("canvas");
        this.tools = TOOLS;
        this.rackTypes = RACK_TYPES;
        this.zoneTypes = ZONE_TYPES;
        this.state = useState({
            loading: true,
            warehouses: [],
            warehouseId: false,
            isManager: false,
            items: [],
            deletedLocationIds: [],
            deletedElementIds: [],
            floorW: MIN_FLOOR_W,
            floorH: MIN_FLOOR_H,
            tool: "select",
            activeRackType: "selective",
            activeZoneType: "storage",
            selectedKey: null,
            zoom: 1,
            panX: 0,
            panY: 0,
            dirty: false,
            saving: false,
        });
        this._drag = null;

        onWillStart(async () => {
            this.state.warehouses = await this.orm.call(
                "buz.smart.warehouse.dashboard",
                "get_filters",
                []
            );
            if (this.state.warehouses.length) {
                this.state.warehouseId = this.state.warehouses[0].id;
            }
            await this.load();
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async load() {
        this.state.loading = true;
        const data = await this.orm.call(
            "buz.smart.warehouse.dashboard",
            "get_designer_data",
            [this.state.warehouseId || false]
        );
        this.state.isManager = data.is_manager;
        const items = [];
        for (const element of data.elements) {
            items.push({
                key: "element_" + element.id,
                kind: element.element_type,
                id: element.id,
                tmpKey: null,
                name: element.name,
                zone_type: element.zone_type,
                x: element.x,
                y: element.y,
                width: element.width,
                depth: element.height,
                rotation: element.rotation,
                notes: element.notes,
                active: element.active !== false,
            });
        }
        let autoX = 4;
        let autoY = 4;
        for (const rack of [...data.racks, ...data.docks]) {
            let x = rack.x;
            let y = rack.y;
            if (!rack.positioned) {
                x = autoX;
                y = autoY;
                autoX += rack.width + 2;
                if (autoX > MIN_FLOOR_W - rack.width) {
                    autoX = 4;
                    autoY += rack.depth + 4;
                }
            }
            items.push({
                key: "loc_" + rack.id,
                kind: rack.kind,
                id: rack.id,
                tmpKey: null,
                name: rack.name,
                rack_code: rack.rack_code,
                rack_type: rack.rack_type,
                zone_element_id: rack.zone_element_id,
                x,
                y,
                width: rack.width,
                depth: rack.depth,
                heightM: rack.height,
                levels: rack.levels,
                bays: rack.bays,
                capacity_per_level: rack.capacity_per_level,
                capacity_uom: rack.capacity_uom,
                notes: rack.notes,
                rotation: rack.rotation,
                bins: rack.bins,
                pct: rack.pct,
                active: rack.active !== false,
            });
        }
        this.state.items = items;
        this.state.deletedLocationIds = [];
        this.state.deletedElementIds = [];
        this._fitFloor();
        this.state.selectedKey = null;
        this.state.zoom = 1;
        this.state.panX = 0;
        this.state.panY = 0;
        this.state.dirty = false;
        this.state.loading = false;
    }

    _fitFloor() {
        let w = MIN_FLOOR_W;
        let h = MIN_FLOOR_H;
        for (const item of this.state.items) {
            const size = Math.max(item.width || 0, item.depth || 0);
            w = Math.max(w, item.x + size + MARGIN);
            h = Math.max(h, item.y + size + MARGIN);
        }
        this.state.floorW = Math.ceil(w / 10) * 10;
        this.state.floorH = Math.ceil(h / 10) * 10;
    }

    expandFloor() {
        this.state.floorW += 20;
        this.state.floorH += 10;
    }

    async onWarehouseChange(ev) {
        this.state.warehouseId = parseInt(ev.target.value) || false;
        await this.load();
    }

    // ------------------------------------------------------------------
    // Derived data
    // ------------------------------------------------------------------
    get selectedItem() {
        return this.state.items.find((i) => i.key === this.state.selectedKey);
    }

    get zones() {
        return this.state.items.filter((i) => i.kind === "zone");
    }

    itemsOfKind(kind) {
        return this.state.items.filter((i) => i.kind === kind);
    }

    get viewBox() {
        const w = this.state.floorW / this.state.zoom;
        const h = this.state.floorH / this.state.zoom;
        return `${this.state.panX} ${this.state.panY} ${w} ${h}`;
    }

    get xTicks() {
        const ticks = [];
        for (let x = 0; x <= this.state.floorW; x += 5) {
            ticks.push(x);
        }
        return ticks;
    }

    get yTicks() {
        const ticks = [];
        for (let y = 0; y <= this.state.floorH; y += 5) {
            ticks.push(y);
        }
        return ticks;
    }

    zoneColor(item) {
        return ZONE_COLORS[item.zone_type] || "#94a3b8";
    }

    zoneName(zoneElementId) {
        const zone = this.state.items.find(
            (i) =>
                i.kind === "zone" &&
                (i.id === zoneElementId || i.tmpKey === zoneElementId)
        );
        return zone ? zone.name : "";
    }

    rackFill(item) {
        if (item.pct === null || item.pct === undefined) {
            return "#e8f5ec";
        }
        if (item.pct >= 85) {
            return "#fadcdc";
        }
        if (item.pct >= 60) {
            return "#faf0cf";
        }
        return "#dcf2e3";
    }

    rackStroke(item) {
        const zone = this.state.items.find(
            (i) =>
                i.kind === "zone" &&
                (i.id === item.zone_element_id ||
                    i.tmpKey === item.zone_element_id)
        );
        return zone ? this.zoneColor(zone) : "#475569";
    }

    bayLines(item) {
        const lines = [];
        const bays = Math.max(1, item.bays || 1);
        const cols = bays * 2;
        for (let i = 1; i < cols; i++) {
            lines.push((item.width / cols) * i);
        }
        return lines;
    }

    // ------------------------------------------------------------------
    // Tools
    // ------------------------------------------------------------------
    setTool(tool) {
        this.state.tool = tool;
        this.state.selectedKey = null;
    }

    setRackType(rackTypeId) {
        this.state.activeRackType = rackTypeId;
        const item = this.selectedItem;
        if (item && (item.kind === "rack" || item.kind === "dock")) {
            item.rack_type = rackTypeId;
            this.state.dirty = true;
        } else {
            this.state.tool = "add_rack";
        }
    }

    setZoneType(zoneTypeId) {
        this.state.activeZoneType = zoneTypeId;
        const item = this.selectedItem;
        if (item && item.kind === "zone") {
            item.zone_type = zoneTypeId;
            this.state.dirty = true;
        } else {
            this.state.tool = "add_zone";
        }
    }

    _newItem(point) {
        const snap = (v) => Math.round(v / SNAP) * SNAP;
        const x = snap(point.x);
        const y = snap(point.y);
        const tmpKey = "new_" + tmpSeq++;
        const base = {
            key: tmpKey,
            tmpKey,
            id: null,
            x,
            y,
            rotation: 0,
            notes: "",
            active: true,
        };
        const count = (kind) => this.itemsOfKind(kind).length + 1;
        switch (this.state.tool) {
            case "add_rack":
                return {
                    ...base,
                    kind: "rack",
                    name: "RACK " + count("rack"),
                    rack_code: "",
                    rack_type: this.state.activeRackType,
                    zone_element_id: false,
                    width: 4,
                    depth: 1.2,
                    heightM: 5.5,
                    levels: 5,
                    bays: 2,
                    capacity_per_level: 0,
                    capacity_uom: "pallet",
                    bins: 0,
                    pct: null,
                };
            case "add_shelf":
                return {
                    ...base,
                    kind: "rack",
                    name: "SHELF " + count("rack"),
                    rack_code: "",
                    rack_type: "shelf",
                    zone_element_id: false,
                    width: 2.4,
                    depth: 0.6,
                    heightM: 2,
                    levels: 4,
                    bays: 3,
                    capacity_per_level: 0,
                    capacity_uom: "box",
                    bins: 0,
                    pct: null,
                };
            case "add_dock":
                return {
                    ...base,
                    kind: "dock",
                    name: "DOCK " + count("dock"),
                    rack_code: "",
                    rack_type: "selective",
                    zone_element_id: false,
                    width: 4,
                    depth: 8,
                    heightM: 0,
                    levels: 1,
                    bays: 1,
                    capacity_per_level: 0,
                    capacity_uom: "pallet",
                    bins: 0,
                    pct: null,
                };
            case "add_zone":
                return {
                    ...base,
                    kind: "zone",
                    name: "ZONE " + count("zone"),
                    zone_type: this.state.activeZoneType,
                    width: 20,
                    depth: 10,
                };
            case "add_aisle":
                return {
                    ...base,
                    kind: "aisle",
                    name: "AISLE " + count("aisle"),
                    zone_type: false,
                    width: 15,
                    depth: 3,
                };
            case "add_obstacle":
                return {
                    ...base,
                    kind: "obstacle",
                    name: "OBSTACLE " + count("obstacle"),
                    zone_type: false,
                    width: 4,
                    depth: 4,
                };
            case "add_forklift":
                return {
                    ...base,
                    kind: "forklift",
                    name: "FORKLIFT " + count("forklift"),
                    zone_type: false,
                    width: 1.2,
                    depth: 1.6,
                };
            case "add_text":
                return {
                    ...base,
                    kind: "text",
                    name: "TEXT",
                    zone_type: false,
                    width: 8,
                    depth: 2,
                };
        }
        return null;
    }

    // ------------------------------------------------------------------
    // Pointer handling
    // ------------------------------------------------------------------
    _svgPoint(ev) {
        const svg = this.svgRef.el;
        const rect = svg.getBoundingClientRect();
        const viewW = this.state.floorW / this.state.zoom;
        const viewH = this.state.floorH / this.state.zoom;
        // preserveAspectRatio=meet: uniform scale, canvas centered
        const scale = Math.max(viewW / rect.width, viewH / rect.height);
        const offsetX = (rect.width - viewW / scale) / 2;
        const offsetY = (rect.height - viewH / scale) / 2;
        return {
            x: (ev.clientX - rect.left - offsetX) * scale + this.state.panX,
            y: (ev.clientY - rect.top - offsetY) * scale + this.state.panY,
        };
    }

    _capture(ev) {
        // capture on the svg root: it survives OWL re-patching the item nodes
        try {
            this.svgRef.el.setPointerCapture(ev.pointerId);
        } catch {
            // pointer capture is a nicety, dragging still works without it
        }
    }

    onItemPointerDown(item, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.tool !== "select") {
            this.onSvgPointerDown(ev);
            return;
        }
        this.state.selectedKey = item.key;
        const point = this._svgPoint(ev);
        this._drag = {
            mode: "move",
            item,
            offsetX: point.x - item.x,
            offsetY: point.y - item.y,
        };
        this._capture(ev);
    }

    onResizePointerDown(item, ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.selectedKey = item.key;
        this._drag = { mode: "resize", item };
        this._capture(ev);
    }

    onSvgPointerDown(ev) {
        if (this.state.tool !== "select") {
            const item = this._newItem(this._svgPoint(ev));
            if (item) {
                this.state.items.push(item);
                this.state.selectedKey = item.key;
                this.state.dirty = true;
                this.state.tool = "select";
            }
            return;
        }
        this.state.selectedKey = null;
        this._drag = {
            mode: "pan",
            startX: ev.clientX,
            startY: ev.clientY,
            panX: this.state.panX,
            panY: this.state.panY,
        };
        this._capture(ev);
    }

    onPointerMove(ev) {
        if (!this._drag) {
            return;
        }
        const snap = (v) => Math.round(v / SNAP) * SNAP;
        if (this._drag.mode === "pan") {
            const rect = this.svgRef.el.getBoundingClientRect();
            const scale = this.state.floorW / this.state.zoom / rect.width;
            this.state.panX = this._drag.panX - (ev.clientX - this._drag.startX) * scale;
            this.state.panY = this._drag.panY - (ev.clientY - this._drag.startY) * scale;
            return;
        }
        const point = this._svgPoint(ev);
        const item = this._drag.item;
        if (this._drag.mode === "resize") {
            item.width = Math.max(1, snap(point.x - item.x));
            item.depth = Math.max(1, snap(point.y - item.y));
        } else {
            item.x = snap(
                Math.min(
                    Math.max(point.x - this._drag.offsetX, 0),
                    this.state.floorW - 2
                )
            );
            item.y = snap(
                Math.min(
                    Math.max(point.y - this._drag.offsetY, 0),
                    this.state.floorH - 2
                )
            );
        }
        this.state.dirty = true;
    }

    onPointerUp() {
        this._drag = null;
    }

    rotateSelected() {
        const item = this.selectedItem;
        if (!item) {
            return;
        }
        item.rotation = (item.rotation + 90) % 360;
        this.state.dirty = true;
    }

    deleteSelected() {
        const item = this.selectedItem;
        if (!item) {
            return;
        }
        if (item.id) {
            if (item.kind === "rack" || item.kind === "dock") {
                if (
                    !confirm(
                        "เก็บถาวร (archive) Location '" +
                            item.name +
                            "' ออกจากคลัง?"
                    )
                ) {
                    return;
                }
                this.state.deletedLocationIds.push(item.id);
            } else {
                this.state.deletedElementIds.push(item.id);
            }
        }
        this.state.items = this.state.items.filter((i) => i.key !== item.key);
        this.state.selectedKey = null;
        this.state.dirty = true;
    }

    // ------------------------------------------------------------------
    // Properties panel
    // ------------------------------------------------------------------
    updateSelected(field, ev) {
        const item = this.selectedItem;
        if (!item) {
            return;
        }
        if (field === "active") {
            item.active = ev.target.checked;
            this.state.dirty = true;
            return;
        }
        let value = ev.target.value;
        if (
            [
                "x",
                "y",
                "width",
                "depth",
                "heightM",
                "capacity_per_level",
            ].includes(field)
        ) {
            value = parseFloat(value) || 0;
        } else if (["levels", "bays"].includes(field)) {
            value = Math.max(1, parseInt(value) || 1);
        } else if (field === "zone_element_id") {
            value = value
                ? isNaN(parseInt(value))
                    ? value // tmp key of a not-yet-saved zone
                    : parseInt(value)
                : false;
        }
        item[field] = value;
        this.state.dirty = true;
    }

    // ------------------------------------------------------------------
    // Zoom
    // ------------------------------------------------------------------
    zoomIn() {
        this.state.zoom = Math.min(4, this.state.zoom * 1.25);
    }

    zoomOut() {
        this.state.zoom = Math.max(0.25, this.state.zoom / 1.25);
        this._clampPan();
    }

    zoomReset() {
        this.state.zoom = 1;
        this.state.panX = 0;
        this.state.panY = 0;
    }

    _clampPan() {
        const maxX = this.state.floorW - this.state.floorW / this.state.zoom;
        const maxY = this.state.floorH - this.state.floorH / this.state.zoom;
        this.state.panX = Math.min(Math.max(0, this.state.panX), Math.max(0, maxX));
        this.state.panY = Math.min(Math.max(0, this.state.panY), Math.max(0, maxY));
    }

    toggleFullscreen() {
        const el = this.canvasRef.el;
        if (!document.fullscreenElement) {
            el.requestFullscreen && el.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    }

    // ------------------------------------------------------------------
    // Persistence
    // ------------------------------------------------------------------
    async save() {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const elements = this.state.items
                .filter((i) =>
                    ["zone", "aisle", "obstacle", "forklift", "text"].includes(
                        i.kind
                    )
                )
                .map((i) => ({
                    id: i.id || false,
                    tmp_key: i.tmpKey || false,
                    element_type: i.kind,
                    zone_type: i.kind === "zone" ? i.zone_type : false,
                    name: i.name,
                    x: i.x,
                    y: i.y,
                    width: i.width,
                    height: i.depth,
                    rotation: String(i.rotation),
                    notes: i.notes,
                    active: i.active !== false,
                }));
            const locations = this.state.items
                .filter((i) => i.kind === "rack" || i.kind === "dock")
                .map((i) => ({
                    id: i.id || false,
                    kind: i.kind,
                    name: i.name,
                    rack_code: i.rack_code,
                    rack_type: i.rack_type,
                    x: i.x,
                    y: i.y,
                    rotation: String(i.rotation),
                    width: i.width,
                    depth: i.depth,
                    height: i.heightM,
                    levels: i.levels,
                    bays: i.bays,
                    capacity_per_level: i.capacity_per_level,
                    capacity_uom: i.capacity_uom,
                    zone_element_id: i.zone_element_id || false,
                    notes: i.notes,
                    active: i.active !== false,
                }));
            await this.orm.call(
                "buz.smart.warehouse.dashboard",
                "save_designer_layout",
                [
                    this.state.warehouseId || false,
                    {
                        elements,
                        locations,
                        deleted_location_ids: this.state.deletedLocationIds,
                        deleted_element_ids: this.state.deletedElementIds,
                    },
                ]
            );
            this.notification.add("บันทึก Layout แล้ว", { type: "success" });
            await this.load();
        } catch (error) {
            console.error("SmartWarehouse layout save failed", error);
            this.notification.add(
                "บันทึกไม่สำเร็จ: " + (error.message || error),
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    async discard() {
        await this.load();
    }
}

registry
    .category("actions")
    .add("buz_smart_warehouse_layout_designer", WarehouseLayoutDesigner);
