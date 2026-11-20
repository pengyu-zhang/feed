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
})();
