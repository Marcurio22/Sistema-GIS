document.addEventListener("DOMContentLoaded", () => {
  const links = document.querySelectorAll(".profile-link");
  if (!links.length) return;

  const go = (href) => {
    if (!href) return;
    window.location.href = href;
  };

  const handleClick = (el) => {
    const href = el.getAttribute("data-href");
    const shouldClose = el.getAttribute("data-close-offcanvas") === "1";

    if (!shouldClose) {
      go(href);
      return;
    }

    const sidebarEl = document.getElementById("sidebar");
    if (!sidebarEl || typeof bootstrap === "undefined") {
      go(href);
      return;
    }

    // Cerrar offcanvas y navegar al terminar la animación
    const offcanvas =
      bootstrap.Offcanvas.getInstance(sidebarEl) || new bootstrap.Offcanvas(sidebarEl);

    const onHidden = () => {
      sidebarEl.removeEventListener("hidden.bs.offcanvas", onHidden);
      go(href);
    };

    sidebarEl.addEventListener("hidden.bs.offcanvas", onHidden);
    offcanvas.hide();
  };

  links.forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      handleClick(el);
    });

    // Accesibilidad: Enter / Space
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleClick(el);
      }
    });
  });
});
