(function () {
  var prefetched = new Set();

  function prefetchUrl(href) {
    if (!href || prefetched.has(href)) return;
    try {
      var u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) return;
      prefetched.add(u.href);
      var link = document.createElement('link');
      link.rel = 'prefetch';
      link.href = u.href;
      document.head.appendChild(link);
    } catch (e) {
      /* ignore */
    }
  }

  document.querySelectorAll('.site-nav a[href]').forEach(function (a) {
    a.addEventListener(
      'pointerenter',
      function () {
        prefetchUrl(a.href);
      },
      { passive: true, once: true }
    );
  });
})();
