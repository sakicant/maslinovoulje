/* Cart, order request form and waitlist. No framework, no third-party code.
   The cart only stores ids and quantities. Every amount shown in the cart
   summary comes from the server (api/quote.php); the browser never sends prices. */
(function () {
  'use strict';

  var CART_KEY = 'olive_cart_v1';
  var SRC_KEY = 'olive_src';
  var API = '/api/';

  var catalog = {};
  try { catalog = JSON.parse(document.getElementById('catalog').textContent); } catch (e) { catalog = { items: [], t: {}, ui: {} }; }
  var T = catalog.t || {};
  var UI = catalog.ui || {};
  var byId = {};
  (catalog.items || []).forEach(function (it) { byId[it.id] = it; });

  // ---------------------------------------------------------------- storage
  function load(key, fallback) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
  }
  function save(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* private mode: cart lives for this page only */ }
  }
  var memoryCart = null;
  function getCart() {
    var c = memoryCart || load(CART_KEY, null) || { items: {}, country: '', delivery: 'address' };
    Object.keys(c.items).forEach(function (id) { if (!byId[id] || !(c.items[id] > 0)) delete c.items[id]; });
    return c;
  }
  function setCart(c) { memoryCart = c; save(CART_KEY, c); updateBadges(); }
  function count(c) { return Object.keys(c.items).reduce(function (n, id) { return n + c.items[id]; }, 0); }

  // Tasting-card code from the QR link (?c=APT12). Saved with the order so the owner knows where people tasted.
  (function () {
    var m = /[?&]c=([A-Za-z0-9_-]{1,40})/.exec(location.search);
    if (m) save(SRC_KEY, m[1]);
  })();

  function money(cents) {
    var s = (Math.round(cents) / 100).toFixed(2).split('.');
    return s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ',' + s[1] + ' €';
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ---------------------------------------------------------------- header
  function updateBadges() {
    var n = count(getCart());
    document.querySelectorAll('[data-cart-count]').forEach(function (b) { b.textContent = n; b.hidden = n === 0; });
    var sticky = document.querySelector('[data-sticky-cart]');
    if (sticky) sticky.hidden = n === 0;
  }
  var menuBtn = document.querySelector('.menubtn');
  if (menuBtn) {
    menuBtn.addEventListener('click', function () {
      var open = menuBtn.getAttribute('aria-expanded') !== 'true';
      menuBtn.setAttribute('aria-expanded', String(open));
      document.getElementById('nav').classList.toggle('is-open', open);
    });
  }

  var dd = document.querySelector('.langdd');
  if (dd) {
    var ddBtn = dd.querySelector('.langdd__toggle');
    ddBtn.addEventListener('click', function (ev) {
      ev.stopPropagation();
      var open = !dd.classList.contains('open');
      dd.classList.toggle('open', open);
      ddBtn.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', function (ev) {
      if (!dd.contains(ev.target)) { dd.classList.remove('open'); ddBtn.setAttribute('aria-expanded', 'false'); }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && dd.classList.contains('open')) { dd.classList.remove('open'); ddBtn.setAttribute('aria-expanded', 'false'); ddBtn.focus(); }
    });
  }

  var toastTimer;
  function toast(text, link) {
    var t = document.querySelector('.toast');
    if (!t) return;
    t.textContent = text;
    if (link) { var a = el('a', '', link.label); a.href = link.href; t.appendChild(a); }
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 3500);
  }

  // ---------------------------------------------------------------- add to cart
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('[data-add]');
    if (!btn) return;
    var id = btn.getAttribute('data-add');
    var item = byId[id];
    if (!item) return;
    var c = getCart();
    var q = (c.items[id] || 0) + 1;
    if (q > item.stock) { toast(T.error_stock || ''); return; }
    c.items[id] = q;
    setCart(c);
    btn.classList.add('is-added');
    btn.textContent = UI.added;
    setTimeout(function () { btn.classList.remove('is-added'); btn.textContent = UI.add_to_cart; }, 1600);
    toast(item.name + ' × ' + q, { label: UI.view_cart, href: (catalog.urls && catalog.urls.cart) || cartUrl() });
  });
  function cartUrl() { var a = document.querySelector('.cartlink'); return a ? a.getAttribute('href') : '/cart/'; }

  // ---------------------------------------------------------------- api
  function post(path, body) {
    return fetch(API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(body),
      credentials: 'same-origin'
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: 'server' }; });
    });
  }

  // ---------------------------------------------------------------- cart page
  var page = document.querySelector('[data-cartpage]');
  if (page) cartPage(page);

  function cartPage(root) {
    var form = root.querySelector('[data-order]');
    var empty = root.querySelector('[data-empty]');
    var lines = root.querySelector('[data-lines]');
    var country = form.querySelector('#country');
    var deliveryBox = form.querySelector('[data-delivery]');
    var pickupNote = form.querySelector('[data-pickup-note]');
    var addressFields = form.querySelector('[data-address-fields]');
    var submit = form.querySelector('[data-submit]');
    var msg = form.querySelector('[data-form-msg]');
    var quoteMsg = form.querySelector('[data-quote-msg]');
    var out = {
      subtotal: form.querySelector('[data-subtotal]'),
      shipping: form.querySelector('[data-shipping]'),
      total: form.querySelector('[data-total]')
    };
    var token = '';
    var quoteOk = false;
    var seq = 0;
    var timer;

    if (!catalog.selling) {
      empty.hidden = false;
      empty.querySelector('p').textContent = T.not_available || '';
      return;
    }

    (catalog.countries || []).forEach(function (c) {
      var o = el('option', '', c.name); o.value = c.code; country.appendChild(o);
    });

    var c0 = getCart();
    if (c0.country) country.value = c0.country;
    var radio = form.querySelector('input[name=delivery][value="' + (c0.delivery === 'pickup' ? 'pickup' : 'address') + '"]');
    if (radio) radio.checked = true;

    function delivery() {
      var r = form.querySelector('input[name=delivery]:checked');
      var canPickup = (catalog.pickup || []).indexOf(country.value) !== -1;
      return canPickup && r && r.value === 'pickup' ? 'pickup' : 'address';
    }

    function renderLines() {
      var c = getCart();
      var ids = Object.keys(c.items);
      empty.hidden = ids.length > 0;
      form.hidden = ids.length === 0;
      lines.textContent = '';
      ids.forEach(function (id) {
        var it = byId[id], q = c.items[id];
        var li = el('li', 'line');
        var info = el('div');
        info.appendChild(el('div', 'line__name', it.name));
        info.appendChild(el('div', 'line__unit', money(it.price)));
        var sum = el('div', 'line__sum', money(it.price * q));
        var qty = el('div', 'qty');
        var minus = el('button', '', '−'); minus.type = 'button'; minus.setAttribute('aria-label', T.decrease);
        var o = el('output', '', String(q)); o.setAttribute('aria-label', T.qty);
        var plus = el('button', '', '+'); plus.type = 'button'; plus.setAttribute('aria-label', T.increase);
        plus.disabled = q >= it.stock;
        minus.onclick = function () { change(id, -1); };
        plus.onclick = function () { change(id, 1); };
        qty.appendChild(minus); qty.appendChild(o); qty.appendChild(plus);
        var rm = el('button', 'line__rm', T.remove); rm.type = 'button';
        rm.onclick = function () { change(id, -999); };
        li.appendChild(info); li.appendChild(sum); li.appendChild(qty); li.appendChild(rm);
        lines.appendChild(li);
      });
    }

    function change(id, d) {
      var c = getCart();
      var q = Math.min((c.items[id] || 0) + d, byId[id].stock);
      if (q <= 0) delete c.items[id]; else c.items[id] = q;
      setCart(c);
      renderLines();
      requestQuote();
    }

    function syncDelivery() {
      var canPickup = (catalog.pickup || []).indexOf(country.value) !== -1;
      deliveryBox.hidden = !canPickup;
      var pickup = delivery() === 'pickup';
      pickupNote.hidden = !pickup;
      addressFields.hidden = pickup;
      addressFields.querySelectorAll('input').forEach(function (i) {
        if (i.name !== 'address2') i.required = !pickup;
      });
      var c = getCart(); c.country = country.value; c.delivery = delivery(); setCart(c);
    }

    function show(q) {
      out.subtotal.textContent = q ? money(q.subtotal) : ' ';
      out.shipping.textContent = q ? money(q.shipping) : ' ';
      out.total.textContent = q ? money(q.total) : ' ';
    }

    function requestQuote() {
      clearTimeout(timer);
      quoteOk = false;
      submit.disabled = true;
      var c = getCart();
      if (!Object.keys(c.items).length) return;
      if (!country.value) { show(null); quoteMsg.textContent = T.need_country; return; }
      quoteMsg.textContent = T.calculating;
      timer = setTimeout(function () {
        var my = ++seq;
        post('quote.php', { items: itemsPayload(c), country: country.value, delivery: delivery(), lang: catalog.lang })
          .then(function (r) {
            if (my !== seq) return;
            if (!r.ok) {
              show(null);
              quoteMsg.textContent = r.error === 'stock' ? T.error_stock : T.quote_error;
              if (r.error === 'stock' && r.available) applyAvailable(r.available);
              return;
            }
            show(r);
            token = r.token || '';
            quoteMsg.textContent = '';
            quoteOk = true;
            submit.disabled = false;
          })
          .catch(function () { if (my === seq) { show(null); quoteMsg.textContent = T.quote_error; } });
      }, 250);
    }

    function applyAvailable(avail) {
      var c = getCart();
      Object.keys(avail).forEach(function (id) {
        if (avail[id] <= 0) delete c.items[id]; else c.items[id] = Math.min(c.items[id] || 0, avail[id]);
        if (byId[id]) byId[id].stock = avail[id];
      });
      setCart(c);
      renderLines();
      setTimeout(requestQuote, 50);
    }

    function itemsPayload(c) {
      return Object.keys(c.items).map(function (id) { return { id: id, qty: c.items[id] }; });
    }

    country.addEventListener('change', function () { syncDelivery(); requestQuote(); });
    form.querySelectorAll('input[name=delivery]').forEach(function (r) {
      r.addEventListener('change', function () { syncDelivery(); requestQuote(); });
    });

    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      msg.className = 'form__msg';
      msg.textContent = '';
      var bad = null;
      form.querySelectorAll('input, select, textarea').forEach(function (f) {
        if (f.closest('[hidden]') || f.closest('.hp')) { f.removeAttribute('aria-invalid'); return; }
        var ok = f.checkValidity();
        if (ok) f.removeAttribute('aria-invalid'); else { f.setAttribute('aria-invalid', 'true'); bad = bad || f; }
      });
      if (bad) { msg.className = 'form__msg is-error'; msg.textContent = T.error_fields; bad.focus(); return; }
      if (!quoteOk) return;

      var fd = new FormData(form);
      var c = getCart();
      var body = {
        items: itemsPayload(c), country: country.value, delivery: delivery(), lang: catalog.lang,
        name: fd.get('name'), email: fd.get('email'), phone: fd.get('phone'),
        address: fd.get('address'), address2: fd.get('address2'), postal: fd.get('postal'), city: fd.get('city'),
        note: fd.get('note'), consent: !!fd.get('consent'), website: fd.get('website'),
        token: token, src: load(SRC_KEY, '') || ''
      };
      submit.disabled = true;
      submit.textContent = T.sending;
      post('order.php', body).then(function (r) {
        if (r.ok && r.ref) {
          memoryCart = { items: {}, country: c.country, delivery: c.delivery };
          save(CART_KEY, memoryCart);
          location.href = catalog.urls.received + '?ref=' + encodeURIComponent(r.ref);
          return;
        }
        submit.disabled = false;
        submit.textContent = T.submit;
        msg.className = 'form__msg is-error';
        if (r.error === 'stock') { msg.textContent = T.error_stock; if (r.available) applyAvailable(r.available); }
        else if (r.error === 'rate') msg.textContent = T.error_rate;
        else if (r.error === 'fields') {
          msg.textContent = T.error_fields;
          (r.fields || []).forEach(function (n) { var f = form.elements[n]; if (f && f.setAttribute) f.setAttribute('aria-invalid', 'true'); });
        } else if (r.error === 'token') { msg.textContent = T.quote_error; requestQuote(); }
        else msg.textContent = T.error_generic;
      }).catch(function () {
        submit.disabled = false; submit.textContent = T.submit;
        msg.className = 'form__msg is-error'; msg.textContent = T.error_generic;
      });
    });

    renderLines();
    syncDelivery();
    requestQuote();
  }

  // ---------------------------------------------------------------- order received
  var refBox = document.querySelector('[data-ref-box]');
  if (refBox) {
    var m = /[?&]ref=([A-Za-z0-9-]{3,20})/.exec(location.search);
    if (m) { refBox.querySelector('[data-ref]').textContent = m[1]; refBox.hidden = false; }
  }

  // ---------------------------------------------------------------- waitlist
  var wl = document.querySelector('[data-waitlist]');
  if (wl) {
    var wlToken = '';
    fetch(API + 'token.php', { credentials: 'same-origin' }).then(function (r) { return r.json(); })
      .then(function (r) { wlToken = r.token || ''; }).catch(function () {});
    wl.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var out = wl.querySelector('.form__msg');
      var email = wl.elements.email, consent = wl.elements.consent;
      var ok = email.checkValidity() && consent.checked;
      email.setAttribute('aria-invalid', String(!email.checkValidity()));
      if (!ok) { out.className = 'form__msg is-error'; out.textContent = T.error_fields; return; }
      var btn = wl.querySelector('button');
      btn.disabled = true;
      post('waitlist.php', { email: email.value, consent: true, website: wl.elements.website.value, token: wlToken, lang: catalog.lang, src: load(SRC_KEY, '') || '' })
        .then(function (r) {
          if (r.ok) { out.className = 'form__msg is-ok'; out.textContent = r.message; wl.reset(); }
          else { out.className = 'form__msg is-error'; out.textContent = r.message || T.error_generic; btn.disabled = false; }
        })
        .catch(function () { out.className = 'form__msg is-error'; out.textContent = T.error_generic; btn.disabled = false; });
    });
  }

  updateBadges();
})();
