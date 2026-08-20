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

    // The margin extends the trigger area a fifth of a screen below the
    // fold, so content is already fading in as it arrives rather than
    // appearing late — a fast flick or an anchor jump would otherwise land
    // on a blank section waiting for its animation.
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.05, rootMargin: '0px 0px 20% 0px' }
    );

    items.forEach(function (el) {
      // Anything the page loads already scrolled past — landing on an
      // anchor, or a restored scroll position — has had its entrance;
      // animating it if the visitor scrolls back up would look broken.
      if (el.getBoundingClientRect().bottom < 0) {
        el.classList.add('is-visible');
        return;
      }
      observer.observe(el);
    });
  }

  /* ---------------------------------------------------------------------
     Mobile navigation
     --------------------------------------------------------------------- */
  function initMobileNav() {
    var nav = document.getElementById('MobileNav');
    if (!nav) return;

    // The toggle announces the drawer's state to screen readers; without
    // this, "Menu, button" gives no clue that pressing it again closes it.
    function setExpanded(value) {
      document.querySelectorAll('[data-mobile-nav-open]').forEach(function (btn) {
        btn.setAttribute('aria-expanded', value ? 'true' : 'false');
      });
    }

    function open() {
      nav.classList.add('is-open');
      document.body.style.overflow = 'hidden';
      setExpanded(true);
      var first = nav.querySelector('a, button');
      if (first) first.focus();
    }

    function close() {
      nav.classList.remove('is-open');
      document.body.style.overflow = '';
      setExpanded(false);
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

    // Declining swaps in an apology and then leaves, rather than jumping away
    // the instant the visitor clicks.
    on(
      '[data-age-gate-decline]',
      'click',
      function (e, link) {
        var ask = gate.querySelector('[data-age-gate-ask]');
        var farewell = gate.querySelector('[data-age-gate-farewell]');
        if (!farewell) return; // no panel rendered — let the link do its job

        e.preventDefault();

        if (ask) ask.hidden = true;
        farewell.hidden = false;

        var remaining = parseInt(farewell.getAttribute('data-delay'), 10);
        if (isNaN(remaining) || remaining < 1) remaining = 5;

        var note = farewell.querySelector('[data-age-gate-countdown]');

        function paint() {
          if (!note) return;
          var template =
            remaining === 1
              ? note.getAttribute('data-singular')
              : note.getAttribute('data-plural');
          if (template) note.textContent = template.replace('__COUNT__', remaining);
        }

        paint();

        var timer = setInterval(function () {
          remaining -= 1;
          if (remaining > 0) {
            paint();
            return;
          }
          clearInterval(timer);
          window.location.href = link.href;
        }, 1000);
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

        // If the cart page could not render its lines — a Liquid error in the
        // items snippet, say — grafting only the footer would leave the drawer
        // claiming the bag is empty above a non-zero subtotal. Treat a missing
        // list as a failed refresh so the catch below takes over.
        if (!newItems) throw new Error('cart markup missing');

        if (body) {
          // The markup arrives dressed for the cart page. Strip the page-only
          // parts so the drawer keeps its own compact layout.
          newItems.classList.remove('cart-items--page');
          var heading = newItems.querySelector('.cart-items__header');
          if (heading) heading.remove();

          body.innerHTML = '';
          body.appendChild(newItems);
        }

        if (footer) {
          footer.innerHTML = '';
          if (newFooter) {
            // The page submits straight to checkout behind its age checkbox.
            // The drawer has no checkbox, so it sends the shopper to the cart
            // page to tick it rather than inheriting that button.
            newFooter.querySelectorAll('button[name="checkout"]').forEach(function (b) {
              var link = document.createElement('a');
              link.className = b.className;
              link.href = routes.cart_url || '/cart';
              link.textContent = b.textContent.trim();
              b.replaceWith(link);
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
      // Adding is always done in the background, drawer or no drawer. Letting
      // the form post natively would send the visitor off to the cart page.
      if (!form) return;

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
          return fetch('/cart.js')
            .then(function (r) {
              return r.json();
            })
            .then(function (cart) {
              updateCartCount(cart.item_count);
              return refreshCartDrawer();
            })
            .then(function () {
              if (openCart()) return;
              // No drawer to confirm with, so the button says so instead and
              // settles back to its own label.
              if (!label) return;
              label.textContent = label.getAttribute('data-added-label') || 'Added';
              setTimeout(function () {
                label.textContent = original;
              }, 2000);
            });
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

  /* ---------------------------------------------------------------------
     Product gallery — thumbnails swap the large preview
     --------------------------------------------------------------------- */
  function initGallery() {
    on('[data-gallery-thumb]', 'click', function (e, thumb) {
      e.preventDefault();

      var gallery = thumb.closest('product-gallery');
      if (!gallery) return;

      var id = thumb.dataset.galleryThumb;

      gallery.querySelectorAll('[data-gallery-slide]').forEach(function (slide) {
        slide.hidden = slide.dataset.gallerySlide !== id;
      });

      gallery.querySelectorAll('[data-gallery-thumb]').forEach(function (el) {
        var active = el === thumb;
        el.classList.toggle('is-active', active);
        el.setAttribute('aria-current', active ? 'true' : 'false');
      });
    });
  }

  function init() {
    initReveal();
    initGallery();
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
