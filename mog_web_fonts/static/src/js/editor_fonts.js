/** @odoo-module **/

import { registry } from "@web/core/registry";

// ใน Odoo 17 จะมี service/registry สำหรับ web_editor อยู่
// เราจะเพิ่มรายการฟอนต์ให้เครื่องมือ font picker เห็นชื่อและค่า CSS
// NOTE: ชื่อ category อาจเปลี่ยนบ้างตามรุ่นย่อย ถ้าไม่เจอจะ fallback แบบ patch ด้านล่าง

const weRegistry = registry.category("web_editor");
const fontRegistry = weRegistry && weRegistry.category ? weRegistry.category("fonts") : null;

// รายชื่อฟอนต์ที่อยากแสดงใน dropdown
const CUSTOM_FONTS = [
    { label: "Prompt", css: `'Prompt', system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif` },
    { label: "DB Adman", css: `'DB Adman', sans-serif` },
    { label: "Gotham", css: `'Gotham', sans-serif` },
    // { label: "YourFont", css: `'YourFont', ...` },
];

function registerFonts() {
    // ทางเลือกที่ 1: ถ้า Odoo เปิด category('fonts') ให้ add ได้เลย
    if (fontRegistry && fontRegistry.add) {
        for (const f of CUSTOM_FONTS) {
            fontRegistry.add(f.label, { family: f.css });
        }
        return;
    }

    // ทางเลือกที่ 2: fallback — patch ตัวเลือกฟอนต์ตอนโหลด editor
    // กลไกนี้อาศัย data attribute ที่ตัวเลือกใช้ภายใน (ทำงานได้กับ build ส่วนมาก)
    const ensurePickerReady = () => {
        const select = document.querySelector('[data-oe-command="fontName"]');
        if (!(select && select.tagName === 'SELECT')) {
            requestAnimationFrame(ensurePickerReady);
            return;
        }
        // Add custom fonts as <option> elements to the fontName <select>
        CUSTOM_FONTS.forEach((f) => {
            const option = document.createElement('option');
            option.value = f.css;
            option.textContent = f.label;
            select.appendChild(option);
        });
    };
    ensurePickerReady();
}

registerFonts();