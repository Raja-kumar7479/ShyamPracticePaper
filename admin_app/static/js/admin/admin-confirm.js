(function () {
    var ICONS = { danger: 'fa-trash', primary: 'fa-pen', blocked: 'fa-ban', info: 'fa-circle-info' };
    var root = null;
    var pending = null;

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = String(text);
        return node;
    }

    function build() {
        root = el('div', 'acf');
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-modal', 'true');
        root.setAttribute('aria-labelledby', 'acfTitle');
        root.hidden = true;
        root.innerHTML =
            '<div class="acf-box">' +
                '<div class="acf-head"><span class="acf-icon"><i class="fas"></i></span><h3 class="acf-title" id="acfTitle"></h3></div>' +
                '<div class="acf-body"></div>' +
                '<div class="acf-foot">' +
                    '<button type="button" class="acf-btn acf-btn--ghost" data-acf="cancel"></button>' +
                    '<button type="button" class="acf-btn acf-btn--alt" data-acf="alt" hidden></button>' +
                    '<button type="button" class="acf-btn" data-acf="confirm"></button>' +
                '</div>' +
            '</div>';
        document.body.appendChild(root);
        root.addEventListener('click', function (e) {
            if (e.target === root) return finish(false);
            var btn = e.target.closest('[data-acf]');
            if (btn) finish(btn.dataset.acf === 'confirm' ? true : (btn.dataset.acf === 'alt' ? 'alt' : false));
        });
        root.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(false); return; }
            if (e.key !== 'Tab') return;
            var buttons = Array.prototype.filter.call(root.querySelectorAll('.acf-btn'), function (b) { return !b.hidden; });
            if (!buttons.length) return;
            var first = buttons[0], last = buttons[buttons.length - 1];
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        });
    }

    function finish(answer) {
        if (!pending) return;
        var done = pending;
        pending = null;
        root.hidden = true;
        document.body.classList.remove('acf-open');
        if (done.returnFocus && document.body.contains(done.returnFocus)) {
            try { done.returnFocus.focus(); } catch (err) {}
        }
        done.resolve(answer);
    }

    function renderItems(body, items, heading) {
        if (!items || !items.length) return;
        if (heading) body.appendChild(el('p', 'acf-list-title', heading));
        var list = el('ul', 'acf-list');
        items.forEach(function (item) {
            var li = el('li', 'acf-item');
            if (item && typeof item === 'object' && 'label' in item) {
                li.appendChild(el('span', 'acf-item__label', item.label));
                if ('from' in item || 'to' in item) {
                    var change = el('span', 'acf-item__change');
                    change.appendChild(el('span', 'acf-from', item.from === '' || item.from == null ? '(empty)' : item.from));
                    change.appendChild(el('i', 'fas fa-arrow-right acf-arrow'));
                    change.appendChild(el('span', 'acf-to', item.to === '' || item.to == null ? '(empty)' : item.to));
                    li.appendChild(change);
                } else if ('value' in item) {
                    li.appendChild(el('span', 'acf-item__value', item.value));
                }
            } else {
                li.textContent = String(item);
            }
            list.appendChild(li);
        });
        body.appendChild(list);
    }

    window.adminConfirm = function (opts) {
        opts = opts || {};
        if (!root) build();
        if (pending) finish(false);
        var tone = ['danger', 'primary', 'blocked', 'info'].indexOf(opts.tone) >= 0 ? opts.tone : 'primary';
        root.className = 'acf acf--' + tone;
        root.querySelector('.acf-icon i').className = 'fas ' + (opts.icon || ICONS[tone]);
        root.querySelector('.acf-title').textContent = opts.title || 'Are you sure?';

        var body = root.querySelector('.acf-body');
        body.innerHTML = '';
        if (opts.message) body.appendChild(el('p', 'acf-msg', opts.message));
        renderItems(body, opts.items, opts.itemsTitle);
        if (opts.note) body.appendChild(el('p', 'acf-note', opts.note));

        var ok = root.querySelector('[data-acf="confirm"]');
        var cancel = root.querySelector('[data-acf="cancel"]');
        var blocked = tone === 'blocked' || tone === 'info';
        ok.className = 'acf-btn ' + (tone === 'danger' ? 'acf-btn--danger' : 'acf-btn--primary');
        ok.textContent = opts.confirmText || (tone === 'danger' ? 'Delete' : 'Confirm');
        ok.hidden = blocked;
        cancel.textContent = blocked ? (opts.cancelText || 'OK, got it') : (opts.cancelText || 'Cancel');
        var alt = root.querySelector('[data-acf="alt"]');
        alt.textContent = opts.altText || '';
        alt.hidden = blocked || !opts.altText;

        return new Promise(function (resolve) {
            pending = { resolve: resolve, returnFocus: document.activeElement };
            root.hidden = false;
            document.body.classList.add('acf-open');
            (tone === 'primary' ? ok : cancel).focus();
        });
    };
})();
