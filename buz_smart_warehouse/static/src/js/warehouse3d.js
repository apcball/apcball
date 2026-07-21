/** @odoo-module **/

/* global THREE */

import { ZONE_TYPES } from "@buz_smart_warehouse/js/layout_designer";

const ZONE_COLORS_3D = Object.fromEntries(
    ZONE_TYPES.map((z) => [z.id, parseInt(z.color.slice(1), 16)])
);

const COLORS = {
    success: 0x35a854,
    warning: 0xe8b931,
    danger: 0xd64545,
    unknown: 0x9ca3af,
    floor: 0xe3e8f0,
    aisle: 0xc3ccd9,
    frame: 0x2b4a7f,
    wall: 0xbfc9d9,
    highlight: 0x2b7fff,
    cargo: 0xb08968,
    dock: 0x4b5563,
    dockStripe: 0xf5c518,
    truckCab: 0x2b7fff,
    truckBox: 0xe5e7eb,
    wheel: 0x1f2937,
};

const BIN = { w: 4, h: 2.4, d: 3, gap: 0.5 };
const LEVELS = 3;
const RACK_GAP = 7;
const ROW_GAP = 12;
const WALL_HEIGHT = 7;

function occupancyColor(pct) {
    if (pct === null || pct === undefined) {
        return COLORS.unknown;
    }
    if (pct >= 85) {
        return COLORS.danger;
    }
    if (pct >= 60) {
        return COLORS.warning;
    }
    return COLORS.success;
}

function heatColor(pct) {
    // smooth green -> amber -> red gradient for the capacity heatmap
    if (pct === null || pct === undefined) {
        return COLORS.unknown;
    }
    const clamped = Math.min(Math.max(pct, 0), 100) / 100;
    const from = new THREE.Color(COLORS.success);
    const mid = new THREE.Color(COLORS.warning);
    const to = new THREE.Color(COLORS.danger);
    const color =
        clamped < 0.6
            ? from.clone().lerp(mid, clamped / 0.6)
            : mid.clone().lerp(to, (clamped - 0.6) / 0.4);
    return color.getHex();
}

function makeLabelTexture(lines, options = {}) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = options.background || "rgba(31,41,55,0.92)";
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(0, 0, canvas.width, canvas.height, 18);
        ctx.fill();
    } else {
        ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    ctx.fillStyle = options.color || "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const fontSizes = options.fontSizes || [44, 34];
    lines.forEach((line, i) => {
        ctx.font = `bold ${fontSizes[i] || 30}px sans-serif`;
        const y = lines.length === 1 ? 64 : 40 + i * 48;
        ctx.fillText(String(line).slice(0, 12), 128, y);
    });
    const texture = new THREE.CanvasTexture(canvas);
    texture.anisotropy = 4;
    return texture;
}

export class Warehouse3D {
    /**
     * @param {HTMLElement} container
     * @param {Array} racks - [{id, name, layout, locations: [{id, name, pct, qty, capacity}]}]
     * @param {Function} onBinClick - (location) => void
     * @param {Object} options - {onLayoutChange: () => void}
     */
    constructor(container, racks, onBinClick, options = {}) {
        this.container = container;
        this.racks = racks;
        this.docks = options.docks || [];
        this.elements = options.elements || [];
        this.floor = options.floor || null; // {w, h} designed canvas in meters
        this.onBinClick = onBinClick;
        this.options = options;
        this.binMeshes = [];
        this.binExtras = new Map(); // bin mesh uuid -> [fill, label, edges]
        this.rackGroups = []; // [{group, rack}]
        this.heatmap = false;
        this.editMode = false;
        this.disposed = false;
        this._pointerDown = null;
        this._drag = null;
        this._build();
    }

    _build() {
        const width = this.container.clientWidth || 800;
        const height = this.container.clientHeight || 420;

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xdde7f3);
        this.scene.fog = new THREE.Fog(0xdde7f3, 260, 480);

        this.camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 700);

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.setSize(width, height);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.container.appendChild(this.renderer.domElement);

        // Lights
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.4));
        const hemi = new THREE.HemisphereLight(0xf3f7ff, 0x9aa5b5, 0.55);
        this.scene.add(hemi);
        const sun = new THREE.DirectionalLight(0xfff4e0, 0.75);
        sun.position.set(60, 90, 40);
        sun.castShadow = true;
        sun.shadow.mapSize.set(2048, 2048);
        sun.shadow.camera.left = -150;
        sun.shadow.camera.right = 150;
        sun.shadow.camera.top = 150;
        sun.shadow.camera.bottom = -150;
        this.scene.add(sun);

        this._buildRacks();
        this._buildDocks();
        this._buildElements();
        this._buildFloor();
        this._setupCamera();
        this._setupControls();
        this._setupPicking();

        this._resizeObserver = new ResizeObserver(() => this._onResize());
        this._resizeObserver.observe(this.container);

        this._animate = this._animate.bind(this);
        this._animate();
    }

    _buildRacks() {
        // Split racks into designed (positioned in the layout designer) and automatic
        const placed = [];
        const auto = [];
        this.racks.forEach((rack) => {
            const layout = rack.layout || {};
            const levels = Math.max(1, layout.levels || LEVELS);
            const positioned = !!layout.positioned;
            const perLevel =
                positioned && layout.bays
                    ? Math.max(1, layout.bays)
                    : Math.max(1, Math.ceil(rack.locations.length / levels));
            const width =
                positioned && layout.width
                    ? layout.width
                    : perLevel * (BIN.w + BIN.gap) + BIN.gap;
            const depth = positioned && layout.depth ? layout.depth : BIN.d;
            const height =
                positioned && layout.height
                    ? layout.height
                    : levels * (BIN.h + 0.3);
            const info = { rack, levels, perLevel, width, depth, height };
            if (positioned) {
                info.x = layout.x;
                info.z = layout.y;
                info.rotation = layout.rotation || 0;
                placed.push(info);
            } else {
                auto.push(info);
            }
        });

        let minX = Infinity;
        let maxX = -Infinity;
        let minZ = Infinity;
        let maxZ = -Infinity;
        placed.forEach((info) => {
            // rotated racks sweep up to max(width, depth) around their origin
            const span = Math.max(info.width, info.depth);
            minX = Math.min(minX, info.x - span);
            maxX = Math.max(maxX, info.x + span);
            minZ = Math.min(minZ, info.z - span);
            maxZ = Math.max(maxZ, info.z + span);
        });
        if (!placed.length) {
            minX = maxX = minZ = maxZ = 0;
        }

        // Automatic racks: grid rows below the designed area
        const cols = Math.max(1, Math.ceil(Math.sqrt(auto.length * 1.6)));
        let x = 0;
        let z = placed.length
            ? maxZ + ROW_GAP
            : this.floor
              ? this.floor.h + ROW_GAP
              : 0;
        auto.forEach((info, i) => {
            if (i > 0 && i % cols === 0) {
                maxX = Math.max(maxX, x);
                x = 0;
                z += BIN.d + ROW_GAP;
            }
            info.x = x;
            info.z = z;
            info.rotation = 0;
            x += info.width + RACK_GAP;
        });
        if (auto.length) {
            maxX = Math.max(maxX, x);
            maxZ = Math.max(maxZ, z + BIN.d);
            minX = Math.min(minX, 0);
            minZ = Math.min(minZ, 0);
        }

        if (this.floor) {
            // designed canvas rules the frame: floor centered on the designer
            // coordinate system so 2D and 3D agree
            this.extent = {
                w: Math.max(this.floor.w, maxX - minX),
                d: Math.max(this.floor.h, maxZ),
            };
            this.center = { x: this.floor.w / 2, z: this.floor.h / 2 };
        } else {
            this.extent = {
                w: Math.max(maxX - minX, 20),
                d: Math.max(maxZ - minZ, 20),
            };
            this.center = {
                x: (maxX + minX) / 2,
                z: (maxZ + minZ) / 2,
            };
        }

        const edgeMaterial = new THREE.LineBasicMaterial({
            color: 0x374151,
            transparent: true,
            opacity: 0.35,
        });
        const frameMaterial = new THREE.MeshLambertMaterial({ color: COLORS.frame });

        placed.concat(auto).forEach((info) => {
            const { rack, perLevel, width: rackWidth, depth: rackDepth } = info;
            const group = new THREE.Group();
            group.position.set(info.x - this.center.x, 0, info.z - this.center.z);
            group.rotation.y = -(info.rotation * Math.PI) / 180;
            group.userData.rack = rack;
            this.rackGroups.push({ group, rack });

            // bins sized to fill the designed footprint
            const levelsUsed = Math.max(
                1,
                Math.ceil(rack.locations.length / perLevel)
            );
            const colW = rackWidth / perLevel;
            const levelH = info.height / Math.max(info.levels, levelsUsed);
            const binW = colW * 0.92;
            const binH = levelH * 0.82;
            const binD = rackDepth;
            const binGeometry = new THREE.BoxGeometry(binW, binH, binD);
            const binEdgeGeometry = new THREE.EdgesGeometry(binGeometry);

            const pcts = rack.locations
                .map((loc) => loc.pct)
                .filter((pct) => pct !== null && pct !== undefined);
            const rackPct = pcts.length
                ? pcts.reduce((a, b) => a + b, 0) / pcts.length
                : null;

            rack.locations.forEach((loc, j) => {
                const level = Math.floor(j / perLevel);
                const slot = j % perLevel;
                const material = new THREE.MeshLambertMaterial({
                    color: occupancyColor(loc.pct),
                });
                const mesh = new THREE.Mesh(binGeometry, material);
                mesh.position.set(
                    colW * slot + colW / 2,
                    level * levelH + binH / 2,
                    binD / 2
                );
                mesh.castShadow = true;
                mesh.receiveShadow = true;
                mesh.userData.location = loc;
                mesh.userData.baseColor = occupancyColor(loc.pct);
                mesh.userData.rackPct = rackPct;
                this.binMeshes.push(mesh);
                group.add(mesh);

                const extras = [];

                // Crisp edge outline on every bin
                const edges = new THREE.LineSegments(binEdgeGeometry, edgeMaterial);
                edges.position.copy(mesh.position);
                group.add(edges);
                extras.push(edges);

                // Fill-level inner box (visual cue of how full)
                if (loc.pct !== null && loc.pct !== undefined && loc.pct > 0) {
                    const fillH =
                        (Math.min(loc.pct, 100) / 100) * Math.max(binH - 0.3, 0.2);
                    const fill = new THREE.Mesh(
                        new THREE.BoxGeometry(
                            Math.max(binW - 0.4, 0.3),
                            fillH,
                            Math.max(binD - 0.4, 0.3)
                        ),
                        new THREE.MeshLambertMaterial({ color: COLORS.cargo })
                    );
                    fill.position.copy(mesh.position);
                    fill.position.y = level * levelH + 0.15 + fillH / 2;
                    group.add(fill);
                    extras.push(fill);
                }

                // Bin label (name + %) floating on front face
                const pctText =
                    loc.pct === null || loc.pct === undefined
                        ? "—"
                        : `${Math.round(loc.pct)}%`;
                const label = new THREE.Sprite(
                    new THREE.SpriteMaterial({
                        map: makeLabelTexture([loc.name, pctText], {
                            background: "rgba(255,255,255,0.95)",
                            color: "#1f2937",
                        }),
                        depthTest: false,
                    })
                );
                const labelW = Math.min(3.4, Math.max(1.6, binW));
                label.scale.set(labelW, labelW / 2, 1);
                label.position.set(
                    mesh.position.x,
                    mesh.position.y + binH / 2 + 0.7,
                    mesh.position.z
                );
                group.add(label);
                extras.push(label);

                this.binExtras.set(mesh.uuid, extras);
            });

            // Rack frame posts
            const frameH = info.height;
            const postGeometry = new THREE.BoxGeometry(0.25, frameH, 0.25);
            [
                [0.1, 0.1],
                [rackWidth - 0.1, 0.1],
                [0.1, rackDepth - 0.1],
                [rackWidth - 0.1, rackDepth - 0.1],
            ].forEach(([px, pz]) => {
                const post = new THREE.Mesh(postGeometry, frameMaterial);
                post.position.set(px, frameH / 2, pz);
                group.add(post);
            });

            // Rack name sign
            const sign = new THREE.Sprite(
                new THREE.SpriteMaterial({
                    map: makeLabelTexture([rack.name], { fontSizes: [56] }),
                    depthTest: false,
                })
            );
            sign.scale.set(6, 3, 1);
            sign.position.set(rackWidth / 2, frameH + 2.4, rackDepth / 2);
            group.add(sign);

            this.scene.add(group);
        });
    }

    _buildDocks() {
        if (!this.docks.length) {
            return;
        }
        const DEFAULT_PAD = { w: 10, d: 14 };
        // auto-placed docks line up along the front edge of the racks
        let autoX = -this.extent.w / 2 + DEFAULT_PAD.w / 2;
        const frontZ = this.extent.d / 2 + DEFAULT_PAD.d / 2 + 4;
        this.docks.forEach((dock) => {
            const layout = dock.layout || {};
            const PAD =
                dock.positioned && layout.width
                    ? { w: layout.width, d: layout.depth || DEFAULT_PAD.d }
                    : DEFAULT_PAD;
            const group = new THREE.Group();
            if (dock.positioned) {
                // designer stores the top-left corner; the pad is centered
                group.position.set(
                    dock.x + PAD.w / 2 - this.center.x,
                    0,
                    dock.y + PAD.d / 2 - this.center.z
                );
                group.rotation.y = -((dock.rotation || 0) * Math.PI) / 180;
            } else {
                group.position.set(autoX, 0, frontZ);
                autoX += PAD.w + 4;
            }

            // Dock pad (asphalt) with a yellow stripe frame
            const pad = new THREE.Mesh(
                new THREE.PlaneGeometry(PAD.w, PAD.d),
                new THREE.MeshLambertMaterial({ color: COLORS.dock })
            );
            pad.rotation.x = -Math.PI / 2;
            pad.position.y = 0.03;
            pad.receiveShadow = true;
            group.add(pad);

            const stripeMaterial = new THREE.MeshBasicMaterial({
                color: COLORS.dockStripe,
            });
            [
                [0, -PAD.d / 2 + 0.2, PAD.w, 0.4],
                [0, PAD.d / 2 - 0.2, PAD.w, 0.4],
                [-PAD.w / 2 + 0.2, 0, 0.4, PAD.d],
                [PAD.w / 2 - 0.2, 0, 0.4, PAD.d],
            ].forEach(([sx, sz, sw, sd]) => {
                const stripe = new THREE.Mesh(
                    new THREE.PlaneGeometry(sw, sd),
                    stripeMaterial
                );
                stripe.rotation.x = -Math.PI / 2;
                stripe.position.set(sx, 0.04, sz);
                group.add(stripe);
            });

            // Dock label
            const label = new THREE.Sprite(
                new THREE.SpriteMaterial({
                    map: makeLabelTexture(
                        [dock.name, dock.kind === "in" ? "รับเข้า" : "ส่งออก"],
                        {
                            background:
                                dock.kind === "in"
                                    ? "rgba(43,127,255,0.92)"
                                    : "rgba(53,168,84,0.92)",
                        }
                    ),
                    depthTest: false,
                })
            );
            label.scale.set(5, 2.5, 1);
            label.position.set(0, 5.5, 0);
            group.add(label);

            // Trucks parked on the pad (one per active picking, max 3)
            for (let i = 0; i < (dock.active_trucks || 0); i++) {
                const truck = this._makeTruck();
                truck.position.set(0, 0, i * 1.5 - 1.5);
                truck.scale.setScalar(1 - i * 0.02); // tiny offset to avoid z-fight
                group.add(truck);
            }

            this.scene.add(group);
        });
        if (!this.floor) {
            // grow the floor extent so auto-placed pads sit inside the walls
            this.extent.d += DEFAULT_PAD.d + 8;
        }
    }

    // ------------------------------------------------------------------
    // Designed layout elements (zones, aisles, obstacles, forklifts, text)
    // ------------------------------------------------------------------
    _buildElements() {
        this.elements.forEach((element) => {
            const w = Math.max(element.width || 1, 0.5);
            const d = Math.max(element.height || 1, 0.5);
            const cx = element.x + w / 2 - this.center.x;
            const cz = element.y + d / 2 - this.center.z;
            const group = new THREE.Group();
            group.position.set(cx, 0, cz);
            group.rotation.y = -((element.rotation || 0) * Math.PI) / 180;

            if (element.element_type === "zone") {
                const color =
                    ZONE_COLORS_3D[element.zone_type] || COLORS.unknown;
                const tile = new THREE.Mesh(
                    new THREE.PlaneGeometry(w, d),
                    new THREE.MeshLambertMaterial({
                        color,
                        transparent: true,
                        opacity: 0.22,
                    })
                );
                tile.rotation.x = -Math.PI / 2;
                tile.position.y = 0.05;
                group.add(tile);
                const label = new THREE.Sprite(
                    new THREE.SpriteMaterial({
                        map: makeLabelTexture([element.name], {
                            background: "rgba(255,255,255,0.9)",
                            color: "#" + color.toString(16).padStart(6, "0"),
                            fontSizes: [48],
                        }),
                        depthTest: false,
                    })
                );
                label.scale.set(7, 3.5, 1);
                label.position.set(0, 0.6, -d / 2 + 1.5);
                group.add(label);
            } else if (element.element_type === "aisle") {
                const strip = new THREE.Mesh(
                    new THREE.PlaneGeometry(w, d),
                    new THREE.MeshLambertMaterial({
                        color: 0x94a3b8,
                        transparent: true,
                        opacity: 0.45,
                    })
                );
                strip.rotation.x = -Math.PI / 2;
                strip.position.y = 0.06;
                group.add(strip);
                // dashed center line + direction arrow along the long axis
                const horizontal = w >= d;
                const len = horizontal ? w : d;
                const dashMaterial = new THREE.MeshBasicMaterial({
                    color: 0xf8fafc,
                });
                for (let p = -len / 2 + 1; p < len / 2 - 1.6; p += 2.2) {
                    const dash = new THREE.Mesh(
                        new THREE.PlaneGeometry(
                            horizontal ? 1.2 : 0.25,
                            horizontal ? 0.25 : 1.2
                        ),
                        dashMaterial
                    );
                    dash.rotation.x = -Math.PI / 2;
                    dash.position.set(
                        horizontal ? p : 0,
                        0.07,
                        horizontal ? 0 : p
                    );
                    group.add(dash);
                }
                const arrow = new THREE.Mesh(
                    new THREE.ConeGeometry(0.5, 1.2, 8),
                    dashMaterial
                );
                arrow.rotation.x = Math.PI / 2;
                if (horizontal) {
                    arrow.rotation.z = -Math.PI / 2;
                    arrow.position.set(len / 2 - 1, 0.08, 0);
                } else {
                    arrow.position.set(0, 0.08, len / 2 - 1);
                }
                group.add(arrow);
            } else if (element.element_type === "obstacle") {
                const box = new THREE.Mesh(
                    new THREE.BoxGeometry(w, 1.5, d),
                    new THREE.MeshLambertMaterial({ color: 0x94a3b8 })
                );
                box.position.y = 0.75;
                box.castShadow = true;
                group.add(box);
            } else if (element.element_type === "forklift") {
                group.add(this._makeForklift(w, d));
            } else if (element.element_type === "text") {
                const label = new THREE.Sprite(
                    new THREE.SpriteMaterial({
                        map: makeLabelTexture([element.name], {
                            background: "rgba(51,65,85,0.9)",
                            fontSizes: [48],
                        }),
                        depthTest: false,
                    })
                );
                label.scale.set(6, 3, 1);
                label.position.set(0, 1.5, 0);
                group.add(label);
            }
            this.scene.add(group);
        });
    }

    _makeForklift(w = 1.2, d = 1.6) {
        const forklift = new THREE.Group();
        const body = new THREE.Mesh(
            new THREE.BoxGeometry(w, 1.1, d * 0.65),
            new THREE.MeshLambertMaterial({ color: 0xf59e0b })
        );
        body.position.set(0, 0.75, d * 0.1);
        body.castShadow = true;
        forklift.add(body);
        const mast = new THREE.Mesh(
            new THREE.BoxGeometry(w * 0.7, 1.8, 0.12),
            new THREE.MeshLambertMaterial({ color: 0x57534e })
        );
        mast.position.set(0, 0.9, -d * 0.35);
        forklift.add(mast);
        const forkMaterial = new THREE.MeshLambertMaterial({ color: 0x9ca3af });
        [-w * 0.22, w * 0.22].forEach((fx) => {
            const fork = new THREE.Mesh(
                new THREE.BoxGeometry(0.1, 0.06, d * 0.45),
                forkMaterial
            );
            fork.position.set(fx, 0.1, -d * 0.55);
            forklift.add(fork);
        });
        const wheelGeometry = new THREE.CylinderGeometry(0.22, 0.22, 0.18, 10);
        const wheelMaterial = new THREE.MeshLambertMaterial({ color: COLORS.wheel });
        [
            [-w / 2, d * 0.25],
            [w / 2, d * 0.25],
            [-w / 2, -d * 0.15],
            [w / 2, -d * 0.15],
        ].forEach(([wx, wz]) => {
            const wheel = new THREE.Mesh(wheelGeometry, wheelMaterial);
            wheel.rotation.z = Math.PI / 2;
            wheel.position.set(wx, 0.22, wz);
            forklift.add(wheel);
        });
        return forklift;
    }

    _makeTruck() {
        const truck = new THREE.Group();
        const box = new THREE.Mesh(
            new THREE.BoxGeometry(2.4, 2.6, 6),
            new THREE.MeshLambertMaterial({ color: COLORS.truckBox })
        );
        box.position.set(0, 1.9, -0.8);
        box.castShadow = true;
        truck.add(box);
        const cab = new THREE.Mesh(
            new THREE.BoxGeometry(2.2, 1.9, 1.8),
            new THREE.MeshLambertMaterial({ color: COLORS.truckCab })
        );
        cab.position.set(0, 1.4, 3.2);
        cab.castShadow = true;
        truck.add(cab);
        const wheelGeometry = new THREE.CylinderGeometry(0.45, 0.45, 0.4, 12);
        const wheelMaterial = new THREE.MeshLambertMaterial({ color: COLORS.wheel });
        [
            [-1.1, 2.9],
            [1.1, 2.9],
            [-1.1, -0.6],
            [1.1, -0.6],
            [-1.1, -2.4],
            [1.1, -2.4],
        ].forEach(([wx, wz]) => {
            const wheel = new THREE.Mesh(wheelGeometry, wheelMaterial);
            wheel.rotation.z = Math.PI / 2;
            wheel.position.set(wx, 0.45, wz);
            truck.add(wheel);
        });
        return truck;
    }

    // ------------------------------------------------------------------
    // Capacity heatmap
    // ------------------------------------------------------------------
    setHeatmap(enabled) {
        this.heatmap = enabled;
        this.binMeshes.forEach((mesh) => {
            const extras = this.binExtras.get(mesh.uuid) || [];
            if (enabled) {
                mesh.material.color.setHex(heatColor(mesh.userData.rackPct));
                extras.forEach((obj) => {
                    // keep edges, hide cargo fill and labels for a clean read
                    obj.visible = !!obj.isLineSegments;
                });
            } else {
                mesh.material.color.setHex(mesh.userData.baseColor);
                extras.forEach((obj) => {
                    obj.visible = true;
                });
            }
        });
    }

    _buildFloor() {
        const w = this.extent.w + 30;
        const d = this.extent.d + 30;
        const floor = new THREE.Mesh(
            new THREE.PlaneGeometry(w, d),
            new THREE.MeshLambertMaterial({ color: COLORS.floor })
        );
        floor.rotation.x = -Math.PI / 2;
        floor.receiveShadow = true;
        this.scene.add(floor);

        const grid = new THREE.GridHelper(Math.max(w, d), 30, COLORS.aisle, COLORS.aisle);
        grid.position.y = 0.02;
        this.scene.add(grid);

        // Perimeter walls (open front for depth perception)
        const wallMaterial = new THREE.MeshLambertMaterial({
            color: COLORS.wall,
            transparent: true,
            opacity: 0.55,
        });
        const back = new THREE.Mesh(
            new THREE.BoxGeometry(w, WALL_HEIGHT, 0.6),
            wallMaterial
        );
        back.position.set(0, WALL_HEIGHT / 2, -d / 2);
        this.scene.add(back);
        const left = new THREE.Mesh(
            new THREE.BoxGeometry(0.6, WALL_HEIGHT, d),
            wallMaterial
        );
        left.position.set(-w / 2, WALL_HEIGHT / 2, 0);
        this.scene.add(left);
        const right = left.clone();
        right.position.x = w / 2;
        this.scene.add(right);
    }

    _setupCamera() {
        const radius = Math.max(this.extent.w, this.extent.d);
        this.camera.position.set(radius * 0.75, radius * 0.65, radius * 0.9);
        this.camera.lookAt(0, 0, 0);
    }

    _setupControls() {
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableZoom = false; // zoom via +/- buttons only
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.maxPolarAngle = Math.PI / 2 - 0.05; // stay above floor
        this.controls.minDistance = 8;
        this.controls.maxDistance = Math.max(this.extent.w, this.extent.d) * 2.5;
        this.controls.target.set(0, 2, 0);
    }

    // ------------------------------------------------------------------
    // Zoom buttons
    // ------------------------------------------------------------------
    zoom(factor) {
        const offset = this.camera.position.clone().sub(this.controls.target);
        const distance = Math.min(
            Math.max(offset.length() * factor, this.controls.minDistance),
            this.controls.maxDistance
        );
        offset.setLength(distance);
        this.camera.position.copy(this.controls.target).add(offset);
    }

    // ------------------------------------------------------------------
    // Search highlight
    // ------------------------------------------------------------------
    highlight(locationIds) {
        const ids = new Set(locationIds || []);
        this.binMeshes.forEach((mesh) => {
            const material = mesh.material;
            const extras = this.binExtras.get(mesh.uuid) || [];
            if (!ids.size) {
                material.emissive.setHex(0x000000);
                material.transparent = false;
                material.opacity = 1;
                extras.forEach((obj) => {
                    obj.material.opacity = obj.isSprite ? 1 : obj.isLineSegments ? 0.35 : 1;
                    obj.material.transparent = obj.isLineSegments;
                    obj.visible = true;
                });
                return;
            }
            if (ids.has(mesh.userData.location.id)) {
                material.emissive.setHex(COLORS.highlight);
                material.transparent = false;
                material.opacity = 1;
                extras.forEach((obj) => {
                    obj.visible = true;
                });
            } else {
                material.emissive.setHex(0x000000);
                material.transparent = true;
                material.opacity = 0.12;
                extras.forEach((obj) => {
                    obj.visible = false;
                });
            }
        });
    }

    clearHighlight() {
        this.highlight([]);
    }

    // ------------------------------------------------------------------
    // Layout edit mode (drag racks on the floor)
    // ------------------------------------------------------------------
    setEditMode(enabled) {
        this.editMode = enabled;
        this.container.style.cursor = enabled ? "move" : "";
        if (!enabled) {
            this._drag = null;
            this.controls.enabled = true;
        }
    }

    getLayout() {
        return this.rackGroups
            .filter(({ rack }) => rack.id)
            .map(({ group, rack }) => ({
                id: rack.id,
                x: group.position.x + this.center.x,
                y: group.position.z + this.center.z,
            }));
    }

    _rackGroupFromMesh(mesh) {
        let node = mesh;
        while (node && !node.userData.rack) {
            node = node.parent;
        }
        return node;
    }

    _floorPoint(ev) {
        const rect = this.renderer.domElement.getBoundingClientRect();
        const pointer = new THREE.Vector2(
            ((ev.clientX - rect.left) / rect.width) * 2 - 1,
            -((ev.clientY - rect.top) / rect.height) * 2 + 1
        );
        this.raycaster.setFromCamera(pointer, this.camera);
        const point = new THREE.Vector3();
        return this.raycaster.ray.intersectPlane(this._floorPlane, point)
            ? point
            : null;
    }

    _setupPicking() {
        this.raycaster = new THREE.Raycaster();
        this._floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

        this._onPointerDown = (ev) => {
            this._pointerDown = { x: ev.clientX, y: ev.clientY };
            if (!this.editMode) {
                return;
            }
            const rect = this.renderer.domElement.getBoundingClientRect();
            const pointer = new THREE.Vector2(
                ((ev.clientX - rect.left) / rect.width) * 2 - 1,
                -((ev.clientY - rect.top) / rect.height) * 2 + 1
            );
            this.raycaster.setFromCamera(pointer, this.camera);
            const hits = this.raycaster.intersectObjects(this.binMeshes, false);
            if (!hits.length) {
                return;
            }
            const group = this._rackGroupFromMesh(hits[0].object);
            if (!group || !group.userData.rack.id) {
                return; // auto-grouped racks (no backing location) cannot move
            }
            const point = this._floorPoint(ev);
            if (!point) {
                return;
            }
            this._drag = {
                group,
                offset: point.clone().sub(group.position),
            };
            this.controls.enabled = false;
            this.renderer.domElement.setPointerCapture(ev.pointerId);
        };

        this._onPointerMove = (ev) => {
            if (!this._drag) {
                return;
            }
            const point = this._floorPoint(ev);
            if (!point) {
                return;
            }
            this._drag.group.position.set(
                point.x - this._drag.offset.x,
                0,
                point.z - this._drag.offset.z
            );
        };

        this._onPointerUp = (ev) => {
            if (this._drag) {
                this._drag = null;
                this.controls.enabled = true;
                this._pointerDown = null;
                if (this.options.onLayoutChange) {
                    this.options.onLayoutChange();
                }
                return;
            }
            if (!this._pointerDown) {
                return;
            }
            const moved =
                Math.abs(ev.clientX - this._pointerDown.x) +
                Math.abs(ev.clientY - this._pointerDown.y);
            this._pointerDown = null;
            if (moved > 6) {
                return; // was a drag, not a click
            }
            const rect = this.renderer.domElement.getBoundingClientRect();
            const pointer = new THREE.Vector2(
                ((ev.clientX - rect.left) / rect.width) * 2 - 1,
                -((ev.clientY - rect.top) / rect.height) * 2 + 1
            );
            this.raycaster.setFromCamera(pointer, this.camera);
            const hits = this.raycaster.intersectObjects(this.binMeshes, false);
            if (hits.length && this.onBinClick) {
                this.onBinClick(hits[0].object.userData.location);
            }
        };

        this.renderer.domElement.addEventListener("pointerdown", this._onPointerDown);
        this.renderer.domElement.addEventListener("pointermove", this._onPointerMove);
        this.renderer.domElement.addEventListener("pointerup", this._onPointerUp);
    }

    _onResize() {
        if (this.disposed) {
            return;
        }
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        if (!width || !height) {
            return;
        }
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    _animate() {
        if (this.disposed) {
            return;
        }
        this._frame = requestAnimationFrame(this._animate);
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    resetView() {
        this._setupCamera();
        this.controls.target.set(0, 2, 0);
    }

    destroy() {
        this.disposed = true;
        cancelAnimationFrame(this._frame);
        this._resizeObserver.disconnect();
        this.renderer.domElement.removeEventListener("pointerdown", this._onPointerDown);
        this.renderer.domElement.removeEventListener("pointermove", this._onPointerMove);
        this.renderer.domElement.removeEventListener("pointerup", this._onPointerUp);
        this.controls.dispose();
        this.scene.traverse((obj) => {
            if (obj.geometry) {
                obj.geometry.dispose();
            }
            if (obj.material) {
                (Array.isArray(obj.material) ? obj.material : [obj.material]).forEach(
                    (m) => {
                        if (m.map) {
                            m.map.dispose();
                        }
                        m.dispose();
                    }
                );
            }
        });
        this.renderer.dispose();
        if (this.renderer.domElement.parentNode) {
            this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
        }
    }
}
