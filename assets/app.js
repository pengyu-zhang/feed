/* Theme and language toggles. The theme key is the same one the homepage uses
   ("theme" in localStorage, same origin), so a choice made on either site carries over. */
(function () {
  var root = document.documentElement;
  function save(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }

  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    save('theme', next);
  });

  var langBtn = document.getElementById('lang-toggle');
  if (langBtn) langBtn.addEventListener('click', function () {
    var next = root.dataset.lang === 'en' ? 'zh' : 'en';
    root.dataset.lang = next;
    root.lang = next === 'en' ? 'en' : 'zh-CN';
    save('feed-lang', next);
  });

  // "All updates": Blogs / YouTube tabs. The last choice is remembered.
  var tabs = document.querySelectorAll('.seg [data-tab]');
  function show(name) {
    tabs.forEach(function (b) { b.setAttribute('aria-selected', b.dataset.tab === name ? 'true' : 'false'); });
    document.querySelectorAll('.panel[data-panel]').forEach(function (p) { p.hidden = p.dataset.panel !== name; });
  }
  tabs.forEach(function (b) {
    b.addEventListener('click', function () { show(b.dataset.tab); save('feed-tab', b.dataset.tab); });
  });
  if (tabs.length) {
    var saved = null;
    try { saved = localStorage.getItem('feed-tab'); } catch (e) {}
    if (saved === 'video' || saved === 'blog') show(saved);
  }
})();
