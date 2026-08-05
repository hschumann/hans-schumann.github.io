(function () {
  function closeMenus(except) {
    document.querySelectorAll("details.nav-menu[open]").forEach(function (menu) {
      if (menu !== except) {
        menu.removeAttribute("open");
      }
    });
  }

  document.addEventListener("click", function (event) {
    var menu = event.target.closest && event.target.closest("details.nav-menu");
    if (!menu) {
      closeMenus(null);
      return;
    }
    closeMenus(menu);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMenus(null);
    }
  });
})();
