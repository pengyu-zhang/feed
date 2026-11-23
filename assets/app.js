/* Feed page behaviour: colour scheme, language, and the Blogs / YouTube tabs. */
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

  var langBtn = document.getElementById('lang-toggle');
  if (langBtn) langBtn.addEventListener('click', function () {
    var next = root.dataset.lang === 'en' ? 'zh' : 'en';
    root.dataset.lang = next;
    root.lang = next === 'en' ? 'en' : 'zh-CN';
    save('feed-lang', next);
  });

  /* "All updates": Blogs / YouTube tabs (WAI-ARIA tabs, selection follows focus). The HTML
     renders the Blogs tab selected; without JS both panels show, each under its own heading. */
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.seg [role="tab"]'));
  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute('data-panel'));
      if (panel) panel.hidden = !on;
    });
    if (focus) tab.focus();
  }
  tabs.forEach(function (t, i) {
    t.addEventListener('click', function () { select(t, false); save('feed-tab', t.dataset.tab); });
    t.addEventListener('keydown', function (e) {
      var j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
      else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
      else if (e.key === 'Home') j = 0;
      else if (e.key === 'End') j = tabs.length - 1;
      if (j === null) return;
      e.preventDefault();
      select(tabs[j], true);
      save('feed-tab', tabs[j].dataset.tab);
    });
  });
  if (tabs.length) {
    var saved = load('feed-tab');
    var start = tabs.filter(function (t) { return t.dataset.tab === saved; })[0] || tabs[0];
    select(start, false);
    document.querySelectorAll('[data-js-hidden]').forEach(function (p) { p.removeAttribute('data-js-hidden'); });
  }
})();
