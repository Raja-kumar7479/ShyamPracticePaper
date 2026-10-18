(function () {
    var host = null;
    var modal = null;
    var pending = null;

    function esc(v) {
        var d = document.createElement('div');
        d.appendChild(document.createTextNode(v == null ? '' : String(v)));
        return d.innerHTML;
    }

    function build() {
        host = document.createElement('div');
        host.className = 'modal fade';
        host.id = 'qmFormModal';
        host.tabIndex = -1;
        host.innerHTML =
            '<div class="modal-dialog modal-dialog-centered"><div class="modal-content">' +
                '<div class="modal-header"><h5 class="modal-title"></h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>' +
                '<div class="modal-body"><p class="qm-form__lead text-muted small"></p><form class="qm-form" novalidate></form></div>' +
                '<div class="modal-footer"><button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Cancel</button>' +
                '<button type="button" class="btn btn-primary" data-qm="submit"></button></div>' +
            '</div></div>';
        document.body.appendChild(host);
        modal = new bootstrap.Modal(host);
        host.addEventListener('hidden.bs.modal', function () {
            if (pending) { var p = pending; pending = null; p.resolve(null); }
        });
        host.querySelector('[data-qm="submit"]').addEventListener('click', submit);
        host.querySelector('form').addEventListener('submit', function (e) { e.preventDefault(); submit(); });
    }

    function submit() {
        if (!pending) return;
        var values = {};
        var bad = null;
        pending.fields.forEach(function (f) {
            var input = host.querySelector('[name="' + f.name + '"]');
            var v = input ? String(input.value == null ? '' : input.value).trim() : '';
            if (f.required && !v && !bad) bad = f.label + ' is required.';
            if (f.pattern && v && !f.pattern.test(v) && !bad) bad = f.hint || (f.label + ' is not valid.');
            values[f.name] = v;
        });
        if (!bad && pending.validate) bad = pending.validate(values);
        var note = host.querySelector('.qm-form__error');
        if (bad) {
            if (!note) {
                note = document.createElement('p');
                note.className = 'qm-form__error text-danger small mt-2 mb-0';
                host.querySelector('.modal-body').appendChild(note);
            }
            note.textContent = bad;
            return;
        }
        var p = pending;
        pending = null;
        modal.hide();
        p.resolve(values);
    }

    window.qmForm = function (opts) {
        if (!host) build();
        host.querySelector('.modal-title').textContent = opts.title || '';
        host.querySelector('.qm-form__lead').textContent = opts.lead || '';
        host.querySelector('[data-qm="submit"]').textContent = opts.submitText || 'Continue';
        var old = host.querySelector('.qm-form__error');
        if (old) old.remove();
        var form = host.querySelector('form');
        form.innerHTML = (opts.fields || []).map(function (f) {
            var control;
            if (f.type === 'select') {
                control = '<select class="form-select" name="' + esc(f.name) + '">' + (f.options || []).map(function (o) {
                    return '<option value="' + esc(o.value) + '"' + (String(o.value) === String(f.value) ? ' selected' : '') + '>' + esc(o.label) + '</option>';
                }).join('') + '</select>';
            } else {
                control = '<input class="form-control" type="' + esc(f.type || 'text') + '" name="' + esc(f.name) + '" value="' + esc(f.value == null ? '' : f.value) + '"' +
                    (f.placeholder ? ' placeholder="' + esc(f.placeholder) + '"' : '') + (f.step ? ' step="' + esc(f.step) + '"' : '') +
                    (f.maxlength ? ' maxlength="' + esc(f.maxlength) + '"' : '') + '>';
            }
            return '<div class="mb-3"><label class="form-label">' + esc(f.label) + (f.required ? ' <span class="text-danger">*</span>' : '') + '</label>' +
                control + (f.help ? '<small class="text-muted d-block mt-1">' + esc(f.help) + '</small>' : '') + '</div>';
        }).join('');
        return new Promise(function (resolve) {
            pending = { resolve: resolve, fields: opts.fields || [], validate: opts.validate };
            modal.show();
            setTimeout(function () {
                var first = form.querySelector('input, select');
                if (first) first.focus();
            }, 250);
            form.querySelectorAll('select[name]').forEach(function (sel) {
                sel.addEventListener('change', function () {
                    form.querySelectorAll('[data-show-when]').forEach(function (box) {
                        var rule = box.getAttribute('data-show-when').split('=');
                        box.classList.toggle('is-hidden', !(rule[0] === sel.name && sel.value === rule[1]));
                    });
                });
            });
            (opts.showWhen || []).forEach(function (rule) {
                var box = form.querySelector('[name="' + rule.field + '"]').closest('.mb-3');
                box.setAttribute('data-show-when', rule.when);
                var sel = form.querySelector('[name="' + rule.when.split('=')[0] + '"]');
                box.classList.toggle('is-hidden', !(sel && sel.value === rule.when.split('=')[1]));
            });
        });
    };
})();
