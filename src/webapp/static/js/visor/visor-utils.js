// ============================================================
// visor-utils.js
// Utilidades globales del visor: notificaciones, confirmación
// y modal de motivo de eliminación.
// Sin dependencias de Jinja2 → archivo estático puro.
// ============================================================

// -----------------------------------------
// NotificationSystem
// -----------------------------------------
const NotificationSystem = {
  container: null,
  initialized: false,

  init() {
    if (this.initialized) return;

    this.container = document.getElementById('notification-container');

    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'notification-container';
      document.body.appendChild(this.container);
    }
    this.initialized = true;
  },

  show({ type = 'info', title, message, duration = 5000 }) {
    if (!this.initialized) {
      this.init();
    }

    if (!this.container) {
      alert(`${title}\n${message}`);
      return;
    }

    const notification = document.createElement('div');
    notification.className = `notification ${type}`;

    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'i'
    };

    notification.innerHTML = `
      <div class="notification-icon">${icons[type]}</div>
      <div class="notification-content">
        <div class="notification-title">${this.escapeHtml(title)}</div>
        <div class="notification-message">${this.escapeHtml(message)}</div>
      </div>
      <button class="notification-close" aria-label="Cerrar">×</button>
      <div class="notification-progress"></div>
    `;

    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => this.close(closeBtn));

    this.container.appendChild(notification);

    if (duration > 0) {
      setTimeout(() => {
        this.close(closeBtn);
      }, duration);
    }
  },

  close(button) {
    const notification = button.closest('.notification');
    if (!notification) return;

    notification.classList.add('removing');
    setTimeout(() => {
      if (notification.parentNode) {
        notification.remove();
      }
    }, 300);
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};

// -----------------------------------------
// setNavbarHeightVar
// -----------------------------------------
function setNavbarHeightVar() {
  const candidates = [
    'nav.navbar.fixed-top',
    'nav.navbar.sticky-top',
    '.navbar.fixed-top',
    '.navbar.sticky-top',
    'header.fixed-top',
    'header.sticky-top',
    'nav'
  ];

  let el = null;
  for (const sel of candidates) {
    const found = document.querySelector(sel);
    if (!found) continue;

    const cs = window.getComputedStyle(found);
    const pos = cs.position;
    if (pos === 'fixed' || pos === 'sticky') {
      el = found;
      break;
    }
  }

  let h = 65;
  if (el) {
    const rect = el.getBoundingClientRect();
    h = Math.round(rect.bottom);
  }

  if (h < 40 || h > 120) h = 65;
  document.documentElement.style.setProperty('--navbar-h', `${h}px`);
}

// Calcular al cargar y recalcular en resize
setNavbarHeightVar();
window.addEventListener("resize", setNavbarHeightVar);

// -----------------------------------------
// AppConfirm
// -----------------------------------------
const AppConfirm = (() => {
  let backdrop, titleEl, textEl, btnOk, btnCancel;
  let resolveFn = null;
  let escHandler = null;

  function ensure() {
    if (backdrop) return;
    backdrop = document.getElementById("app-confirm-backdrop");
    titleEl = document.getElementById("app-confirm-title");
    textEl = document.getElementById("app-confirm-text");
    btnOk = document.getElementById("app-confirm-ok");
    btnCancel = document.getElementById("app-confirm-cancel");

    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) {
        e.preventDefault();
        e.stopPropagation();
      }
    });

    btnCancel.addEventListener("click", () => close(false));
    btnOk.addEventListener("click", () => close(true));
  }

  function open({ title, message, okText = "Aceptar", cancelText = "Cancelar", okClass = "btn-danger" }) {
    ensure();

    titleEl.textContent = title || "Confirmación";
    textEl.textContent = message || "";
    btnOk.textContent = okText;
    btnCancel.textContent = cancelText;

    btnOk.className = `btn ${okClass}`;

    backdrop.classList.remove("d-none");
    backdrop.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";

    escHandler = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    document.addEventListener("keydown", escHandler, true);

    return new Promise((resolve) => {
      resolveFn = resolve;
      setTimeout(() => btnOk.focus(), 0);
    });
  }

  function close(result) {
    if (!backdrop) return;

    backdrop.classList.add("d-none");
    backdrop.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";

    if (escHandler) {
      document.removeEventListener("keydown", escHandler, true);
      escHandler = null;
    }

    const r = resolveFn;
    resolveFn = null;
    r?.(!!result);
  }

  return { open };
})();

// -----------------------------------------
// openMotivoEliminacionModal
// -----------------------------------------
function openMotivoEliminacionModal() {
  return new Promise((resolve) => {
    const modalEl = document.getElementById("motivoEliminacionModal");
    const inputEl = document.getElementById("motivoEliminacionInput");
    const btnOk = document.getElementById("btnConfirmarMotivoEliminacion");

    if (!modalEl || !inputEl || !btnOk) {
      console.error("Faltan elementos del modal de motivo de eliminación");
      resolve(null);
      return;
    }

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl, {
      backdrop: "static",
      keyboard: false
    });

    inputEl.value = "";
    inputEl.classList.remove("is-invalid");

    let settled = false;

    const cleanup = () => {
      btnOk.removeEventListener("click", onOk);
      modalEl.removeEventListener("hidden.bs.modal", onHidden);
      inputEl.removeEventListener("keydown", onKeyDown);
    };

    const finish = (val) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(val);
    };

    const onOk = () => {
      const motivo = (inputEl.value || "").trim();

      if (!motivo) {
        inputEl.classList.add("is-invalid");
        inputEl.focus();
        return;
      }

      modal.hide();
      finish(motivo);
    };

    const onHidden = () => {
      if (!settled) finish(null);
    };

    const onKeyDown = (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        btnOk.click();
      }
    };

    btnOk.addEventListener("click", onOk);
    modalEl.addEventListener("hidden.bs.modal", onHidden);
    inputEl.addEventListener("keydown", onKeyDown);

    modal.show();
    setTimeout(() => inputEl.focus(), 150);
  });
}