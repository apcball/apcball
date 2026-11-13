/** @odoo-module **/

import { registry } from '@web/core/registry';

registry.category('actions').add('buz_share_certificate.pdf', async (env, action) => {
    const { mode, url } = action.params;
    if (mode === 'open') {
        window.open(url, '_blank', 'noopener');
        return;
    }
    if (mode === 'print') {
        const frame = document.createElement('iframe');
        frame.style.display = 'none';
        frame.onload = () => {
            try {
                frame.contentWindow.addEventListener('afterprint', () => {
                    frame.remove();
                    env.services.action.doAction({
                        type: 'ir.actions.act_window',
                        res_model: 'buz.share.certificate',
                        res_id: action.params.certificate_id,
                        views: [[false, 'form']],
                        target: 'current',
                    });
                }, { once: true });
                frame.contentWindow.focus();
                frame.contentWindow.print();
            } catch {
                frame.remove();
                env.services.notification.add('ไม่สามารถเปิดหน้าพิมพ์ได้ กรุณาใช้ Open เพื่อพิมพ์จาก PDF', { type: 'warning' });
            }
        };
        frame.src = url;
        document.body.appendChild(frame);
        return;
    }
    try {
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok || !response.headers.get('content-type')?.includes('application/pdf')) {
            throw new Error('PDF unavailable');
        }
        const objectUrl = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = 'share_certificate.pdf';
        link.click();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch {
        env.services.notification.add('ไม่สามารถดาวน์โหลด PDF ได้', { type: 'danger' });
    }
});
