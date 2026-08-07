/* Dunrobin Highland Distillery — theme behaviour */
(function () {
  'use strict';

  var routes = window.routes || {};

  function on(selector, event, handler, root) {
    (root || document).addEventListener(event, function (e) {
      var target = e.target.closest(selector);
      if (target) handler(e, target);
    });
  }

  function money(cents) {
    return (cents / 100).toLocaleString(undefined, { style: 'currency', currency: window.Shopify?.currency?.active || 'GBP' });
  }

  /* ---------------------------------------------------------------------
     Scroll reveal
     --------------------------------------------------------------------- */
  function initReveal() {
    var items = document.querySelectorAll('.reveal:not(.is-visible)');
    if (!items.length) return;

    if (!('IntersectionObserver' in window)) {
      items.forEach(function (el) {
        el.classList.add('is-visible');
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -60px 0px' }
    );

    items.forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ---------------------------------------------------------------------
     Mobile navigation
     --------------------------------------------------------------------- */
  function initMobileNav() {
    var nav = document.getElementById('MobileNav');
    if (!nav) return;

    function open() {
      nav.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      var first = nav.querySelector('a, button');
      if (first) first.focus();
    }

    function close() {
      nav.classList.remove('is-open');
      document.body.style.overflow = '';
    }

    on('[data-mobile-nav-open]', 'click', open);
    on('[data-mobile-nav-close]', 'click', close);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && nav.classList.contains('is-open')) close();
    });
  }

  /* ---------------------------------------------------------------------
     Announcement bar rotation
     --------------------------------------------------------------------- */
  class AnnouncementBar extends HTMLElement {
    connectedCallback() {
      this.items = Array.from(this.querySelectorAll('[data-announcement]'));
      if (this.dataset.autorotate !== 'true' || this.items.length < 2) return;

      var speed = (parseInt(this.dataset.speed, 10) || 6) * 1000;
      var index = 0;
      var self = this;

      this.timer = setInterval(function () {
        self.items[index].hidden = true;
        index = (index + 1) % self.items.length;
        self.items[index].hidden = false;
      }, speed);
    }

    disconnectedCallback() {
      clearInterval(this.timer);
    }
  }

  if (!customElements.get('announcement-bar')) {
    customElements.define('announcement-bar', AnnouncementBar);
  }

  /* ---------------------------------------------------------------------
     Age gate
     --------------------------------------------------------------------- */
  function initAgeGate() {
    var gate = document.getElementById('AgeGate');
    if (!gate) return;

    // Never block the theme editor preview.
    if (window.Shopify && window.Shopify.designMode) return;

    var KEY = 'dunrobin:age-verified';
    // Per session by default: sessionStorage is cleared when the browsing
    // session ends, so a returning visitor is asked again.
    var perSession = gate.getAttribute('data-frequency') !== 'device';

    function store() {
      try {
        return perSession ? window.sessionStorage : window.localStorage;
      } catch (e) {
        return null;
      }
    }

    if (perSession) {
      // Drop any device-wide flag left by a previous configuration, otherwise
      // visitors who confirmed once would never be asked again.
      try {
        window.localStorage.removeItem(KEY);
      } catch (e) {
        /* storage unavailable */
      }
    }

    var verified = null;
    try {
      var s = store();
      verified = s && s.getItem(KEY);
    } catch (e) {
      verified = null;
    }

    if (verified === 'true') return;

    gate.hidden = false;
    gate.classList.add('is-open');
    document.body.style.overflow = 'hidden';

    on(
      '[data-age-gate-accept]',
      'click',
      function () {
        try {
          var s = store();
          if (s) s.setItem(KEY, 'true');
        } catch (e) {
          /* private browsing — the gate simply shows again */
        }
        gate.classList.remove('is-open');
        gate.hidden = true;
        document.body.style.overflow = '';
      },
      gate
    );
  }

  /* ---------------------------------------------------------------------
     Cart
     --------------------------------------------------------------------- */
  var cartDrawer = document.getElementById('CartDrawer');

  function openCart() {
    if (!cartDrawer) return false;
    cartDrawer.classList.add('is-open');
    document.body.style.overflow = 'hidden';
    return true;
  }

  function closeCart() {
    if (!cartDrawer) return;
    cartDrawer.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  function updateCartCount(count) {
    document.querySelectorAll('[data-cart-count]').forEach(function (el) {
      el.textContent = count;
      el.hidden = count === 0;
    });
  }

  function refreshCartDrawer() {
    if (!cartDrawer) return Promise.resolve();

    // Re-render from the cart page, which is the single source of truth for
    // both the line items and the checkout form.
    return fetch(routes.cart_url || '/cart', { headers: { Accept: 'text/html' } })
      .then(function (r) {
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var body = document.getElementById('CartDrawerBody');
        var footer = document.getElementById('CartDrawerFooter');
        var newItems = doc.querySelector('.cart-items') || doc.querySelector('.cart-empty');
        var newFooter = doc.getElementById('CartFooterForm');

        if (body && newItems) {
          body.innerHTML = '';
          body.appendChild(newItems);
        }

        if (footer) {
          footer.innerHTML = '';
          if (newFooter) {
            // The cart page gates checkout behind its age checkbox; the drawer
            // has no such checkbox, so never inherit a disabled button.
            newFooter.querySelectorAll('button[name="checkout"]').forEach(function (b) {
              b.disabled = false;
            });
            footer.appendChild(newFooter);
            footer.hidden = false;
          } else {
            footer.hidden = true;
          }
        }
      })
      .catch(function () {
        // If the refresh fails, send the shopper to the cart page rather than
        // leaving them stuck in a drawer with no way to pay.
        window.location.href = routes.cart_url || '/cart';
      });
  }

  function changeLine(line, quantity) {
    return fetch(routes.cart_change_url || '/cart/change.js', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ line: line, quantity: quantity })
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (cart) {
        updateCartCount(cart.item_count);
        if (cartDrawer && cartDrawer.classList.contains('is-open')) {
          return refreshCartDrawer();
        }
        window.location.reload();
      });
  }

  function initCart() {
    on('[data-cart-open]', 'click', function (e) {
      if (openCart()) e.preventDefault();
    });
    on('[data-cart-close]', 'click', closeCart);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeCart();
    });

    on('[data-cart-remove]', 'click', function (e, el) {
      e.preventDefault();
      changeLine(parseInt(el.dataset.cartRemove, 10), 0);
    });

    on('[data-quantity-change]', 'click', function (e, el) {
      e.preventDefault();
      var line = parseInt(el.dataset.quantityChange, 10);
      var delta = parseInt(el.dataset.quantityDelta, 10);
      var input = document.querySelector('[data-quantity-input="' + line + '"]');
      if (!input) return;
      var next = Math.max(0, parseInt(input.value, 10) + delta);
      input.value = next;
      changeLine(line, next);
    });

    on('[data-quantity-input]', 'change', function (e, el) {
      changeLine(parseInt(el.dataset.quantityInput, 10), Math.max(0, parseInt(el.value, 10) || 0));
    });
  }

  /* ---------------------------------------------------------------------
     Product form — add to cart without a page reload
     --------------------------------------------------------------------- */
  function initProductForm() {
    on('[data-product-quantity-delta]', 'click', function (e, el) {
      e.preventDefault();
      var input = document.querySelector('[data-product-quantity]');
      if (!input) return;
      var delta = parseInt(el.dataset.productQuantityDelta, 10);
      input.value = Math.max(1, (parseInt(input.value, 10) || 1) + delta);
    });

    document.addEventListener('submit', function (e) {
      var form = e.target.closest('[data-product-form]');
      if (!form || !cartDrawer) return;

      e.preventDefault();

      var button = form.querySelector('[data-add-to-cart]');
      var label = form.querySelector('[data-add-to-cart-text]');
      var original = label ? label.textContent : '';

      if (button) button.setAttribute('aria-disabled', 'true');
      if (label) label.textContent = '…';

      fetch(routes.cart_add_url || '/cart/add.js', {
        method: 'POST',
        headers: { Accept: 'application/json' },
        body: new FormData(form)
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          if (data.status) {
            if (label) label.textContent = data.description || data.message;
            return;
          }
          if (label) label.textContent = original;
          return fetch(routes.cart_url || '/cart.js')
            .then(function (r) {
              return r.json();
            })
            .then(function (cart) {
              updateCartCount(cart.item_count);
              return refreshCartDrawer();
            })
            .then(openCart);
        })
        .catch(function () {
          form.submit();
        })
        .finally(function () {
          if (button) button.removeAttribute('aria-disabled');
          if (label && label.textContent === '…') label.textContent = original;
        });
    });
  }

  /* ---------------------------------------------------------------------
     Variant picker
     --------------------------------------------------------------------- */
  function initVariantPicker() {
    var picker = document.querySelector('[data-variant-picker]');
    if (!picker) return;

    var dataEl = picker.querySelector('[data-variant-data]');
    if (!dataEl) return;

    var variants;
    try {
      variants = JSON.parse(dataEl.textContent);
    } catch (e) {
      return;
    }

    picker.addEventListener('change', function () {
      var selected = Array.from(picker.querySelectorAll('.variant-picker__input:checked')).map(function (input) {
        return input.value;
      });

      var match = variants.find(function (variant) {
        return variant.options.every(function (option, i) {
          return option === selected[i];
        });
      });

      var idInput = document.querySelector('[data-variant-id]');
      var button = document.querySelector('[data-add-to-cart]');
      var label = document.querySelector('[data-add-to-cart-text]');
      var priceEl = document.getElementById('ProductPrice');

      if (!match) {
        if (button) button.disabled = true;
        if (label) label.textContent = window.themeStrings.unavailable;
        return;
      }

      if (idInput) {
        idInput.value = match.id;
        idInput.disabled = false;
      }

      if (button) button.disabled = !match.available;
      if (label) label.textContent = match.available ? window.themeStrings.addToCart : window.themeStrings.soldOut;

      if (priceEl) {
        var html = '<div class="price' + (match.compare_at_price > match.price ? ' price--on-sale' : '') + '">';
        if (match.compare_at_price > match.price) {
          html += '<s class="price__regular">' + money(match.compare_at_price) + '</s>';
          html += '<span class="price__sale">' + money(match.price) + '</span>';
        } else {
          html += '<span class="price__regular">' + money(match.price) + '</span>';
        }
        priceEl.innerHTML = html + '</div>';
      }

      if (window.history.replaceState) {
        var url = new URL(window.location.href);
        url.searchParams.set('variant', match.id);
        window.history.replaceState({}, '', url);
      }
    });
  }

  /* ---------------------------------------------------------------------
     Cart page age confirmation — blocks checkout until ticked
     --------------------------------------------------------------------- */
  function initAgeConfirm() {
    var box = document.querySelector('[data-age-confirm]');
    if (!box) return;

    var panel = document.getElementById('AgeConfirm');
    // Gate only the cart page's own button, never the drawer's.
    var scope = panel.closest('.cart-page') || document;
    var checkout = scope.querySelector('button[name="checkout"]');
    if (!checkout) return;

    function sync() {
      checkout.disabled = !box.checked;
      if (box.checked && panel) panel.classList.remove('is-invalid');
    }

    sync();
    box.addEventListener('change', sync);

    // If the button is reached without ticking, draw attention to the panel.
    checkout.addEventListener('click', function (e) {
      if (box.checked) return;
      e.preventDefault();
      if (panel) {
        panel.classList.add('is-invalid');
        panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      box.focus();
    });
  }

  /* ---------------------------------------------------------------------
     Misc
     --------------------------------------------------------------------- */
  function initAutoSubmit() {
    on('[data-auto-submit] select', 'change', function (e, el) {
      el.closest('form').submit();
    });
  }

  function initShare() {
    on('[data-share-link]', 'click', function (e, el) {
      if (!navigator.share) return;
      e.preventDefault();
      navigator.share({ title: document.title, url: el.href }).catch(function () {});
    });
  }

  function init() {
    initReveal();
    initMobileNav();
    initAgeGate();
    initCart();
    initProductForm();
    initVariantPicker();
    initAgeConfirm();
    initAutoSubmit();
    initShare();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // The theme editor re-renders sections in place.
  document.addEventListener('shopify:section:load', function () {
    initReveal();
    initVariantPicker();
  });
})();
