/* @odoo-module */

import { registry } from "@web/core/registry";
import { jsonrpc } from "@web/core/network/rpc_service";

registry.category("actions").add("cheque.configure.popup", async (env, action) => {
    const chequeId = action.params.cheque_id;

//    const response = await fetch(`/cheque/configure_attributes?cheque_id=${chequeId}`);
    const html = await response.text();

    const existingModal = document.querySelector('#cheque-configure-modal');
    if (existingModal) existingModal.remove();

    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    document.body.appendChild(wrapper);

    const modalElement = document.querySelector('#cheque-configure-modal');
    const modal = new bootstrap.Modal(modalElement);
    modal.show();

    // Attach event listeners manually after modal is added
    setupChequeConfiguration();
});

function setupChequeConfiguration() {
    const draggableBoxes = {};

    const dropdown = document.querySelector('#cheque-attribute-dropdown');
    const updateBtn = document.querySelector('#update-positions');

    dropdown?.addEventListener('change', (ev) => {
        const selected = ev.currentTarget.options[ev.currentTarget.selectedIndex];
        const attributeId = selected.value;
        const fieldName = selected.text;
        const base64Image = selected.getAttribute('data-image');
        console.log("Selected image:", base64Image);
        if (base64Image && base64Image.length > 50) {
            const img = document.querySelector('.cheque-background');
            if (img) {
                img.src = base64Image;
            }
        }

        if (draggableBoxes[attributeId]) {
            alert("Field already placed. Select another.");
            return;
        }

        const container = document.querySelector('.cheque-background-container');
        if (!container) {
            alert("Container not found.");
            return;
        }

        const box = document.createElement('input');
        box.type = 'text';
        box.className = 'draggable-text-box';
        box.value = fieldName;
        box.setAttribute('data-attribute-id', attributeId);
        Object.assign(box.style, {
            position: 'absolute',
            top: '100px',
            left: '100px',
            width: '180px',
            padding: '4px',
            zIndex: 20,
            border: '2px solid #28a745',
            borderRadius: '6px',
            backgroundColor: '#ffffff',
            fontWeight: 'bold',
            cursor: 'move',
        });

        makeDraggable(box);
        container.appendChild(box);
        draggableBoxes[attributeId] = box;

        const attrInput = document.querySelector('#attribute_id');
        if (attrInput) attrInput.value = attributeId;
    });

    updateBtn?.addEventListener('click', (ev) => {
        ev.preventDefault();

        const attrInput = document.querySelector('#attribute_id');
        if (!attrInput || !attrInput.value) {
            alert("Missing attribute_id input.");
            return;
        }

        const attributeId = attrInput.value;
        const box = draggableBoxes[attributeId];
        if (!box) {
            alert("Drag a field first.");
            return;
        }

        const rect = box.getBoundingClientRect();
        const containerRect = box.parentElement.getBoundingClientRect();

        const x1 = Math.round(rect.left - containerRect.left);
        const y1 = Math.round(rect.top - containerRect.top);
        const x2 = x1 + box.offsetWidth;
        const y2 = y1 + box.offsetHeight;

        document.querySelector('#x1').value = x1;
        document.querySelector('#y1').value = y1;
        document.querySelector('#x2').value = x2;
        document.querySelector('#y2').value = y2;

        jsonrpc('/update_cheque_attribute', {
            attribute_id: attributeId,
            x1, y1, x2, y2
        }).then((response) => {
            if (response.status === "success") {
                alert("Coordinates updated successfully!");
                ['#x1', '#y1', '#x2', '#y2'].forEach(id => document.querySelector(id).value = '');
            } else {
                alert("Error updating coordinates.");
            }
        }).catch(console.error);
    });

    function makeDraggable(el) {
        let offsetX = 0, offsetY = 0, isDragging = false;

        el.addEventListener('mousedown', (e) => {
            isDragging = true;
            offsetX = e.offsetX;
            offsetY = e.offsetY;
            el.style.zIndex = 100;
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            const parentRect = el.parentElement.getBoundingClientRect();
            let left = e.clientX - parentRect.left - offsetX;
            let top = e.clientY - parentRect.top - offsetY;

            left = Math.max(0, Math.min(left, parentRect.width - el.offsetWidth));
            top = Math.max(0, Math.min(top, parentRect.height - el.offsetHeight));

            el.style.left = `${left}px`;
            el.style.top = `${top}px`;

        });

        document.addEventListener('mouseup', () => {
            isDragging = false;
            el.style.zIndex = 20;
        });
    }
}
