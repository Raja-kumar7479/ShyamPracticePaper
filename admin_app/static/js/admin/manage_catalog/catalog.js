(function () {
    'use strict';

    function el(id) { return document.getElementById(id); }

    function toast(message, ok) {
        if (window.adminToast) window.adminToast(message, ok ? 'success' : 'error');
        else alert(message);
    }

    function send(url, method, body) {
        return fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: body ? JSON.stringify(body) : undefined
        }).then(function (res) {
            return res.json().catch(function () { return {}; })
                .then(function (data) { return { ok: res.ok, data: data }; });
        });
    }

    function handle(promise, okMessage, after) {
        return promise.then(function (r) {
            if (r.ok && r.data.success) {
                toast(okMessage, true);
                if (after) after();
                else setTimeout(function () { window.location.reload(); }, 400);
                return true;
            }
            toast(r.data.message || 'That change could not be saved.', false);
            return false;
        }).catch(function () {
            toast('Network error. Please try again.', false);
            return false;
        });
    }

    var modal = null;
    function openModal() {
        if (!modal) modal = new bootstrap.Modal(el('ctSectionModal'));
        modal.show();
    }

    var editingKey = null;

    function resetModal() {
        editingKey = null;
        el('ctModalTitle').textContent = 'New section';
        el('ctSecKey').value = '';
        el('ctSecKey').disabled = false;
        el('ctSecLabel').value = '';
        el('ctSecHelp').value = '';
        el('ctSecPortal').value = '';
        el('ctSecEditor').value = '';
        el('ctSecPosition').value = 0;
        el('ctSecAvailable').checked = false;
        document.querySelectorAll('#ctSecGroupsWrap input').forEach(function (b) { b.checked = false; });
        el('ctSecGroupsWrap').classList.remove('is-hidden');
    }

    if (el('ctNewSection')) {
        el('ctNewSection').addEventListener('click', function () { resetModal(); openModal(); });
    }

    document.querySelectorAll('.ct-edit-section').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var s = JSON.parse(btn.getAttribute('data-section'));
            resetModal();
            editingKey = s.section_key;
            el('ctModalTitle').textContent = 'Edit ' + s.section_key;
            el('ctSecKey').value = s.section_key;
            el('ctSecKey').disabled = true;
            el('ctSecLabel').value = s.label || '';
            el('ctSecHelp').value = s.help_text || '';
            el('ctSecPortal').value = s.portal || '';
            el('ctSecEditor').value = s.editor || '';
            el('ctSecPosition').value = s.position || 0;
            el('ctSecAvailable').checked = !!s.is_available;
            el('ctSecGroupsWrap').classList.add('is-hidden');
            openModal();
        });
    });

    function syncAvailable() {
        var portal = el('ctSecPortal').value;
        var box = el('ctSecAvailable');
        if (!portal) {
            box.checked = false;
            box.disabled = true;
            box.title = 'Pick a portal first - a section with nowhere to go cannot be available.';
        } else {
            box.disabled = false;
            box.title = '';
        }
    }
    if (el('ctSecPortal')) {
        el('ctSecPortal').addEventListener('change', syncAvailable);
        syncAvailable();
    }

    if (el('ctSaveSection')) {
        el('ctSaveSection').addEventListener('click', function () {
            var payload = {
                section_key: el('ctSecKey').value,
                label: el('ctSecLabel').value,
                help_text: el('ctSecHelp').value,
                portal: el('ctSecPortal').value,
                editor: el('ctSecEditor').value,
                position: el('ctSecPosition').value,
                is_available: el('ctSecAvailable').checked,
                groups: Array.prototype.map.call(
                    document.querySelectorAll('#ctSecGroupsWrap input:checked'),
                    function (b) { return b.value; })
            };
            var url = editingKey ? '/api/catalog/sections/' + encodeURIComponent(editingKey)
                                 : '/api/catalog/sections';
            el('ctSaveSection').disabled = true;
            handle(send(url, editingKey ? 'PUT' : 'POST', payload),
                   editingKey ? 'Section updated.' : 'Section added.')
                .finally(function () { el('ctSaveSection').disabled = false; });
        });
    }

    document.querySelectorAll('.ct-del-section').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var key = btn.getAttribute('data-key');
            var used = parseInt(btn.getAttribute('data-used') || '0', 10);
            if (used > 0) {
                toast('"' + key + '" is used by ' + used + ' content item(s). Move or delete them first.', false);
                return;
            }
            if (!confirm('Delete the section "' + key + '"?')) return;
            handle(send('/api/catalog/sections/' + encodeURIComponent(key), 'DELETE'), 'Section deleted.');
        });
    });

    document.querySelectorAll('.ct-link').forEach(function (box) {
        box.addEventListener('change', function () {
            var wanted = box.checked;
            send('/api/catalog/group-sections', 'POST', {
                group_name: box.getAttribute('data-group'),
                section_key: box.getAttribute('data-section'),
                enabled: wanted
            }).then(function (r) {
                if (r.ok && r.data.success) {
                    toast('Saved.', true);
                } else {
                    box.checked = !wanted;
                    toast(r.data.message || 'That change could not be saved.', false);
                }
            }).catch(function () {
                box.checked = !wanted;
                toast('Network error. Please try again.', false);
            });
        });
    });
}());
