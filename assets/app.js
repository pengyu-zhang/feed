/* Feed page behaviour: colour scheme, language, the Blogs / YouTube tabs and back-to-top. */
(function () {
  var root = document.documentElement;
  function save(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function drop(key) { try { localStorage.removeItem(key); } catch (e) {} }

  /* Colour scheme, the same rules as the homepage (same origin, same "theme" key). The page
     follows the OS unless a scheme is pinned in <meta name="color-scheme">. The toggle switches
     to the opposite of what is on screen; the choice is saved only when it differs from the OS,
     and toggling back to the OS scheme drops the pin, so neither site stays pinned for good. */
  var schemeMeta = document.querySelector('meta[name="color-scheme"]');
  var osDark = window.matchMedia('(prefers-color-scheme: dark)');
  function osScheme() { return osDark.matches ? 'dark' : 'light'; }
  function asScheme(v) { return v === 'light' || v === 'dark' ? v : null; }
  function pinned() { return schemeMeta ? asScheme(schemeMeta.content) : null; }
  function pin(scheme) {
    if (!schemeMeta || scheme === pinned()) return;
    schemeMeta.content = scheme || 'light dark';
    if (window.syncThemeColor) window.syncThemeColor(scheme);
  }
  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = (pinned() || osScheme()) === 'dark' ? 'light' : 'dark';
    var choice = next === osScheme() ? null : next;
    pin(choice);
    if (choice) save('theme', choice); else drop('theme');
  });
  window.addEventListener('storage', function (e) {
    if (e.key === 'theme' || e.key === null) pin(asScheme(e.newValue));
  });

  /* Language. Both languages are in the page and CSS shows one (html[data-lang]). */
  /* The summaries differ in length between the languages, so the text under the reader would
     jump: remember the item at the top of the window and put it back where it was. */
  /* the blocks of an item in the language on display: title, one line, then the paragraphs and
     points of the summary (the same number and order in both languages) */
  function blocksOf(item) {
    var list = [item.querySelector('.title')];
    var brief = item.querySelector('.brief');
    if (brief) list.push(brief);
    var body = item.querySelector('.detail > [data-l="' + (root.dataset.lang === 'en' ? 'en' : 'zh') + '"]');
    if (body) Array.prototype.push.apply(list, body.querySelectorAll('p, li'));
    return list;
  }
  /* the block at the top of the window, below the tab bar: which item, which block, where */
  function readingSpot() {
    var items = document.querySelectorAll('.item');
    for (var i = 0; i < items.length; i++) {
      var r = items[i].getBoundingClientRect();
      if (r.bottom <= 90) continue;
      if (r.top >= window.innerHeight) return null;
      var blocks = blocksOf(items[i]);
      for (var j = 0; j < blocks.length; j++) {
        var rb = blocks[j].getBoundingClientRect();
        if (rb.bottom > 90) return { item: items[i], block: j, top: rb.top };
      }
      /* only the item's bottom padding is in view: the reader is at the next item */
    }
    return null;
  }
  document.querySelectorAll('.lang-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var keep = window.scrollY > 0 ? readingSpot() : null;
      var next = root.dataset.lang === 'en' ? 'zh' : 'en';
      root.dataset.lang = next;
      root.lang = next === 'en' ? 'en' : 'zh-CN';
      save('feed-lang', next);
      if (!keep) return;
      /* the same block in the other language goes where the reader's block was: now, and once
         more after the browser's own scroll anchoring has had its turn */
      var blocks = blocksOf(keep.item);
      var same = blocks[Math.min(keep.block, blocks.length - 1)];
      var settle = function () {
        var d = same.getBoundingClientRect().top - keep.top;
        if (Math.abs(d) >= 1) window.scrollBy(0, d);
      };
      settle();
      requestAnimationFrame(function () { requestAnimationFrame(settle); });
    });
  });

  /* Blogs / YouTube tabs, on the day pages and on Sources (WAI-ARIA tabs, selection follows
     focus). The HTML renders the Blogs tab selected; without JS both lists show, each under its
     own heading. The panel that is not selected is hidden="until-found": where the browser
     supports it, find-in-page still reaches its text and the beforematch event selects its tab;
     elsewhere the attribute is a plain `hidden`. A panel with nothing to focus in it (an empty
     one) is focusable itself, so the keyboard can reach its message. The choice is remembered
     per kind of page (data-remember on the tab list: the day pages share one, Sources has its
     own), so picking YouTube on a day does not open Sources on YouTube. */
  var tablist = document.querySelector('.seg[role="tablist"]');
  var storeKey = tablist ? tablist.getAttribute('data-remember') : null;
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.seg [role="tab"]'));
  function panelOf(tab) { return document.getElementById(tab.getAttribute('data-panel')); }
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      var panel = panelOf(t);
      if (!panel) return;
      if (on) panel.hidden = false; else panel.setAttribute('hidden', 'until-found');
      if (on && !panel.querySelector('a[href], button')) panel.tabIndex = 0;
      else panel.removeAttribute('tabindex');
    });
    if (focus) tab.focus();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { select(t, false); if (storeKey) save(storeKey, t.dataset.tab); });
    t.addEventListener('keydown', function (e) {
      var j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabs.length - 1;
      if (j === null) return;
      e.preventDefault();
      select(tabs[j], true);
      if (storeKey) save(storeKey, tabs[j].dataset.tab);
    });
    var panel = panelOf(t);
    if (panel) panel.addEventListener('beforematch', function () { select(t, false); });
  });
  if (tabs.length) {
    var saved = storeKey ? load(storeKey) : null;
    var start = tabs.filter(function (t) { return t.dataset.tab === saved; })[0] || tabs[0];
    select(start, false);
    document.querySelectorAll('[data-js-hidden]').forEach(function (p) { p.removeAttribute('data-js-hidden'); });
  }

  /* The bar's height, for the page's top margin on one-column screens (style.css): at a large
     text size the tabs wrap onto a second row and the fixed bar would otherwise cover the top
     of the page. The same as the homepage's site.js. */
  var tabbar = document.querySelector('.tabbar');
  if (tabbar && window.ResizeObserver) {
    new ResizeObserver(function () {
      root.style.setProperty('--tabbar-block-size', tabbar.offsetHeight + 'px');
    }).observe(tabbar);
  }

  /* Back to top, as on the homepage: appears after a screen of scrolling. When it goes away
     while it has keyboard focus, focus moves to the skip link (the first stop of the page). */
  var topBtn = document.getElementById('back-to-top');
  if (topBtn) {
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    var toggleTop = function () {
      var show = window.scrollY > 400;
      if (!show && topBtn.matches(':focus-visible')) {
        var skip = document.querySelector('.skip-link');
        if (skip) skip.focus({ preventScroll: true });
      }
      topBtn.classList.toggle('is-visible', show);
    };
    window.addEventListener('scroll', toggleTop, { passive: true });
    toggleTop();
    topBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: reduced.matches ? 'auto' : 'smooth' });
    });
  }
})();
