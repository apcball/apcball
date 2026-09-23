/** @odoo-module **/

/** ห้ามใช้ toISOString() — มันเลื่อนวันตาม UTC แล้ววันที่จะคลาดไปหนึ่งวัน */
export function isoDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export const BUCKET_CAPTION = "อายุสินค้าคงเหลือ (วัน)";

/**
 * หัวตาราง 3 ชั้นจากสเปกคอลัมน์ของเซิร์ฟเวอร์
 *
 * ชั้น 1: คอลัมน์เดี่ยว (rowspan 3), กลุ่ม "คงเหลือ" (rowspan 2), และช่วงอายุทั้งหมดรวมเป็น
 *         หัวเดียว "อายุสินค้าคงเหลือ (วัน)"; ชั้น 2: ป้ายช่วง (0-30 วัน …); ชั้น 3: จำนวน/มูลค่า
 * PDF/Excel ใช้แค่ 2 ชั้น (สเปกเดียวกัน) — ชั้นกลางเป็นของหน้าจอเท่านั้น
 */
export function headerTiers(columns) {
    const tier1 = [];
    const tier2 = [];
    const tier3 = [];
    let bucketCell = null;
    let index = 0;
    while (index < columns.length) {
        const col = columns[index];
        if (!col.group) {
            tier1.push({ label: col.label, colspan: 1, rowspan: 3, key: col.key });
            index += 1;
            continue;
        }
        let span = 1;
        while (index + span < columns.length && columns[index + span].group === col.group) {
            span += 1;
        }
        if (col.bucket) {
            if (!bucketCell) {
                bucketCell = { label: BUCKET_CAPTION, colspan: 0, rowspan: 1, key: "buckets", caption: true };
                tier1.push(bucketCell);
            }
            bucketCell.colspan += span;
            tier2.push({ label: col.group, colspan: span, rowspan: 1, key: col.group, bucket: col.bucket });
        } else {
            tier1.push({ label: col.group, colspan: span, rowspan: 2, key: col.group });
        }
        for (let offset = 0; offset < span; offset += 1) {
            const sub = columns[index + offset];
            tier3.push({ label: sub.label, key: sub.key, bucket: sub.bucket });
        }
        index += span;
    }
    return { tier1, tier2, tier3 };
}
