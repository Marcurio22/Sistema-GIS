// ==========================================================
// OPERACIONES (UI + API)
// Endpoints esperados (a implementar backend):
//   GET    /api/mis-recinto/<id_recinto>/operaciones?limit=5
//   GET    /api/mis-recinto/<id_recinto>/operaciones?all=1
//   POST   /api/mis-recinto/<id_recinto>/operaciones
//   PATCH  /api/operaciones/<id_operacion>
//   DELETE /api/operaciones/<id_operacion>
// ==========================================================

function openOperacionesPanel() {
    const sp = document.getElementById("side-panel");
    const panel = document.getElementById("operaciones-historico-panel");
    if (!sp || !panel) return;

    // Cierra otros overlays por si acaso
    closeHistoricoPanel?.();
    closeGaleriaPanel?.();

    sp.classList.add("operaciones-open");
    panel.classList.remove("d-none");
    panel.setAttribute("aria-hidden", "false");
}

function closeOperacionesPanel() {
    const sp = document.getElementById("side-panel");
    const panel = document.getElementById("operaciones-historico-panel");
    if (!sp || !panel) return;

    sp.classList.remove("operaciones-open");
    panel.classList.add("d-none");
    panel.setAttribute("aria-hidden", "true");
}

document.getElementById("btn-volver-operaciones-historico")?.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    closeOperacionesPanel();
});

document.getElementById("btn-cerrar-operaciones-historico")?.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    document.getElementById("side-close")?.click();
});

document.getElementById("btn-historico-operaciones")?.addEventListener("click", async (e) => {
    e.preventDefault(); e.stopPropagation();
    if (!currentSideRecintoId) return;

    openOperacionesPanel();
    await renderOperacionesHistorico(currentSideRecintoId);
});

// ---------- Render INLINE (panel principal) ----------
async function renderOperacionesForRecinto(recintoId) {
    const container = document.getElementById("operaciones-container");
    if (!container) return;

    container.innerHTML = `<div class="text-muted">Cargando operaciones...</div>`;

    try {
        const ops = await fetchJson(`/api/mis-recinto/${recintoId}/operaciones?limit=5`);
        renderOperacionesInline(container, recintoId, Array.isArray(ops) ? ops : []);
    } catch (e) {
        console.warn(e);
        container.innerHTML = `
        <div class="text-danger">No se pudieron cargar las operaciones.</div>
        <div class="text-muted" style="font-size:12px">Revisa /api/mis-recinto/${recintoId}/operaciones</div>
      `;
    }
}

function opTipoLabel(tipo) {
    const t = String(tipo || "").toUpperCase();
    if (t === "RIEGO") return "Riego";
    if (t === "FERTILIZACION") return "Fertilización";
    if (t === "FITOSANITARIO") return "Fitosanitario";
    if (t === "OTRAS") return "Otras";
    return safeText(tipo, "Operación");
}

function opBadgeClass(tipo) {
    const t = String(tipo || "").toUpperCase();
    if (t === "RIEGO") return "bg-info";
    if (t === "FERTILIZACION") return "bg-success";
    if (t === "FITOSANITARIO") return "bg-warning text-dark";
    if (t === "OTRAS") return "bg-secondary";
    return "bg-secondary";
}


function normalizeProcedenciaAgua(v) {
    if (Array.isArray(v)) return v.filter(Boolean);
    if (v && typeof v === "object") return [v];
    return [];
}

function procedenciaAguaToText(v) {
    const arr = normalizeProcedenciaAgua(v);
    if (!arr.length) return "";
    return arr
        .map(x => (x?.label || x?.codigo || "").trim())
        .filter(Boolean)
        .join(", ");
}

function opResumen(op) {
    let d = op?.detalle;
    if (typeof d === "string") { try { d = JSON.parse(d); } catch (_) { } }
    d = d || {};
    const tipo = String(op?.tipo || "").toUpperCase();

    if (tipo === "RIEGO") {
        const v = d?.volumen_m3 ?? d?.volumen ?? null;
        const sis = d?.sistema_riego?.label || d?.sistema_riego?.codigo || "";
        const proc = procedenciaAguaToText(d?.procedencia_agua);
        const obs = d?.observaciones || "";
        const txtV = (v != null && v !== "") ? `${Number(v).toFixed(0)} m³` : "—";
        return `${txtV}${sis ? " · " + sis : ""}${proc ? " · " + proc : ""}${obs ? " — " + obs : ""}`;
    }

    if (tipo === "FERTILIZACION") {
        const prod = d?.producto?.label || d?.producto?.codigo || "";
        const cant = d?.cantidad;
        const uni = d?.unidad || "";
        const tipoF = d?.tipo_fertilizacion?.label || d?.tipo_fertilizacion?.codigo || "";
        const obs = d?.observaciones || "";
        const txtC = (cant != null && cant !== "") ? `${cant} ${uni}` : "—";
        return `${txtC}${prod ? " · " + prod : ""}${tipoF ? " · " + tipoF : ""}${obs ? " — " + obs : ""}`;
    }

    if (tipo === "OTRAS") {
        const cat = d?.catalogo || "";
        const lab = d?.label || d?.codigo || "";
        const obs = d?.observaciones || "";
        return `${cat}${lab ? " · " + lab : ""}${obs ? " — " + obs : ""}`.trim() || "—";
    }

    return safeText(op?.descripcion, "—");
}

function renderOperacionesInline(container, recintoId, ops) {
    const hasOps = ops.length > 0;

    container.innerHTML = `
      <div class="d-flex gap-2 flex-wrap mb-2">
        <button id="btn-add-op-inline" class="btn btn-success btn-sm">
          <i class="bi bi-plus-lg me-1"></i> Añadir operación
        </button>

      </div>

      <div id="op-inline-body"></div>
    `;

    const body = container.querySelector("#op-inline-body");

    if (!hasOps) {
        body.innerHTML = `
        <div class="text-muted" style="font-size:12px">
          No hay operaciones registradas en este recinto.
        </div>
      `;
    } else {
        body.innerHTML = `
        <div class="op-mini-list">
          ${ops.map(op => `
            <div class="op-mini-item d-flex justify-content-between align-items-start">
              <div>
                <div class="d-flex align-items-center gap-2">
                  <span class="badge ${opBadgeClass(op.tipo)} op-badge">${escapeHtml(opTipoLabel(op.tipo))}</span>
                  <span class="text-muted op-date">${escapeHtml(formatDateOnly(op.fecha))}</span>
                </div>
                <div class="op-resumen">${escapeHtml(opResumen(op))}</div>
              </div>

              <div class="d-flex gap-2">
                <button class="btn btn-outline-success btn-sm btn-edit-op-inline" data-id="${op.id_operacion}">
                  <i class="bi bi-pencil"></i>
                </button>
                <button class="btn btn-outline-danger btn-sm btn-del-op-inline" data-id="${op.id_operacion}">
                  <i class="bi bi-trash"></i>
                </button>
              </div>
            </div>
          `).join("")}
        </div>

        <div id="op-inline-form-slot" class="mt-2"></div>
      `;
    }

    // EDITAR (INLINE)
    body.querySelectorAll(".btn-edit-op-inline").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.dataset.id;
            const op = ops.find(x => String(x.id_operacion) === String(id));
            if (!op) return;

            const slotForm = body.querySelector("#op-inline-form-slot");
            renderOperacionForm(slotForm, {
                recintoId,
                op,
                mode: "actual_edit",
                onDone: async () => { await renderOperacionesForRecinto(recintoId); },
                onCancel: async () => { await renderOperacionesForRecinto(recintoId); },
            });
        });
    });

    // ELIMINAR (INLINE)
    body.querySelectorAll(".btn-del-op-inline").forEach(btn => {
        btn.addEventListener("click", async () => {
            const id = btn.dataset.id;

            const ok = await AppConfirm.open({
                title: "Eliminar operación",
                message: "¿Seguro que deseas eliminar la operación? También se eliminará del histórico. Este proceso no es reversible.",
                okText: "Eliminar",
                cancelText: "Cancelar",
                okClass: "btn-danger"
            });
            if (!ok) return;

            await fetchJson(`/api/operaciones/${id}`, { method: "DELETE" });
            NotificationSystem.show({ type: "success", title: "Operación eliminada", message: "" });
            await renderOperacionesForRecinto(recintoId);
        });
    });
    // AÑADIR (INLINE)
    const btnAdd = container.querySelector("#btn-add-op-inline");
    btnAdd.addEventListener("click", () => {
        const slotForm = body.querySelector("#op-inline-form-slot");
        renderOperacionForm(slotForm, {
            recintoId,
            mode: "actual_add",
            onDone: async () => { await renderOperacionesForRecinto(recintoId); },
            onCancel: async () => { await renderOperacionesForRecinto(recintoId); },
        });
    });
}

// ---------- Render HISTÓRICO (overlay) ----------
async function renderOperacionesHistorico(recintoId) {
    const listEl = document.getElementById("operaciones-historico-list");
    if (!listEl) return;

    listEl.innerHTML = `<div class="text-muted">Cargando histórico...</div>`;

    let ops = [];
    try {
        const data = await fetchJson(`/api/mis-recinto/${recintoId}/operaciones?all=1`);
        ops = Array.isArray(data) ? data : [];
    } catch (e) {
        console.warn(e);
        listEl.innerHTML = `<div class="text-danger">No se pudo cargar el histórico de operaciones.</div>`;
        return;
    }

    listEl.innerHTML = `
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div class="d-flex align-items-center gap-2">
          <i class="bi bi-journal-check text-success"></i>
          <span>Registro completo</span>
          <span class="badge bg-success">${ops.length}</span>
        </div>

        <div class="d-flex gap-2 ms-auto">
          <button id="btn-download-ops-csv"
            class="btn btn-outline-success btn-sm"
            ${ops.length ? "" : "disabled"}
            title="${ops.length ? "" : "No hay datos para exportar"}" type="button">
            <i class="bi bi-download me-1"></i> CSV
          </button>
          <button id="btn-add-op-historico" class="btn btn-success btn-sm">
            + Añadir al Histórico
          </button>
        </div>
      </div>

      <div class="side-divider"></div>

      <div class="table-responsive historico-table-wrap">
        <table class="table table-sm table-hover align-middle historico-table mb-0">
          <thead>
            <tr>
              <th style="min-width:110px;">Día</th>
              <th style="min-width:120px;">Tipo</th>
              <th style="min-width:220px;">Descripción</th>

              <th style="min-width:120px;">Riego m³</th>
              <th style="min-width:180px;">Sistema</th>
              <th style="min-width:180px;">Procedencia</th>

              <th style="min-width:140px;">Cantidad</th>
              <th style="min-width:220px;">Producto</th>
              <th style="min-width:160px;">Fert. tipo</th>
              <th style="min-width:160px;">Método</th>
              <th style="min-width:160px;">Material</th>

              <th style="min-width:220px;">Otras (Catálogo / Opción)</th>
              <th style="min-width:220px;">Observaciones</th>

              <th style="min-width:220px;" class="text-end">Acciones</th>
            </tr>
          </thead>
          <tbody>
            ${ops.map(op => {
        let d = op?.detalle;
        if (typeof d === "string") { try { d = JSON.parse(d); } catch (_) { } }
        d = d || {};
        const t = String(op?.tipo || "").toUpperCase();

        const riego_m3 = t === "RIEGO" ? (d.volumen_m3 ?? "") : "";
        const riego_sis = t === "RIEGO" ? (d?.sistema_riego?.label || d?.sistema_riego?.codigo || "") : "";
        const riego_proc = t === "RIEGO" ? procedenciaAguaToText(d?.procedencia_agua) : "";

        const fert_cant = t === "FERTILIZACION" ? `${d?.cantidad ?? ""} ${d?.unidad ?? ""}`.trim() : "";
        const fert_prod = t === "FERTILIZACION" ? (d?.producto?.label || d?.producto?.codigo || "") : "";
        const fert_tipo = t === "FERTILIZACION" ? (d?.tipo_fertilizacion?.label || d?.tipo_fertilizacion?.codigo || "") : "";
        const fert_met = t === "FERTILIZACION" ? (d?.metodo_aplicacion?.label || d?.metodo_aplicacion?.codigo || "") : "";
        const fert_mat = t === "FERTILIZACION" ? (d?.material?.label || d?.material?.codigo || "") : "";

        const otras = t === "OTRAS" ? `${d?.catalogo || ""}${d?.label ? " / " + d.label : ""}`.trim() : "";
        const obs = d?.observaciones || d?.obs || op?.descripcion || "";

        return `
                <tr>
                  <td>${escapeHtml(formatDateOnly(op.fecha))}</td>
                  <td><span class="badge ${opBadgeClass(op.tipo)}">${escapeHtml(opTipoLabel(op.tipo))}</span></td>
                  <td>${escapeHtml(op?.descripcion || "—")}</td>

                  <td>${escapeHtml(riego_m3 === "" ? "—" : String(riego_m3))}</td>
                  <td>${escapeHtml(riego_sis || "—")}</td>
                  <td>${escapeHtml(riego_proc || "—")}</td>

                  <td>${escapeHtml(fert_cant || "—")}</td>
                  <td>${escapeHtml(fert_prod || "—")}</td>
                  <td>${escapeHtml(fert_tipo || "—")}</td>
                  <td>${escapeHtml(fert_met || "—")}</td>
                  <td>${escapeHtml(fert_mat || "—")}</td>

                  <td>${escapeHtml(otras || "—")}</td>
                  <td>${escapeHtml(obs || "—")}</td>

                  <td class="text-end">
                    <div class="d-flex gap-2 justify-content-end flex-wrap">
                      <button class="btn btn-success btn-sm btn-edit-op" data-id="${op.id_operacion}">
                        <i class="bi bi-pencil-fill me-1"></i> Editar
                      </button>
                      <button class="btn btn-danger btn-sm btn-del-op" data-id="${op.id_operacion}">
                        <i class="bi bi-trash-fill me-1"></i> Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              `;
    }).join("")}
          </tbody>
        </table>
      </div>

      <div id="op-hist-form-slot" class="mt-3"></div>
    `;

    // Deshabilitar botón CSV si no hay datos
    const csvBtn = listEl.querySelector("#btn-download-ops-csv");
    if (csvBtn && csvBtn.disabled) {
        csvBtn.classList.remove("btn-outline-success");
        csvBtn.classList.add("btn-outline-secondary");

        const wrap = document.createElement("span");
        wrap.className = "d-inline-block";
        wrap.title = "Ahora mismo no se puede descargar CSV";

        csvBtn.parentNode.insertBefore(wrap, csvBtn);
        wrap.appendChild(csvBtn);
    }

    // Añadir histórico
    listEl.querySelector("#btn-add-op-historico")?.addEventListener("click", () => {
        const slot = listEl.querySelector("#op-hist-form-slot");
        renderOperacionForm(slot, {
            recintoId,
            op: null,
            mode: "historico_add",
            onDone: async () => { await renderOperacionesHistorico(recintoId); },
            onCancel: async () => { await renderOperacionesHistorico(recintoId); },
        });
    });

    // Editar
    listEl.querySelectorAll(".btn-edit-op").forEach(btn => {
        btn.addEventListener("click", () => {
            const id = btn.dataset.id;
            const op = ops.find(x => String(x.id_operacion) === String(id));
            if (!op) return;

            const slot = listEl.querySelector("#op-hist-form-slot");
            renderOperacionForm(slot, {
                recintoId,
                op,
                mode: "historico_edit",
                onDone: async () => { await renderOperacionesHistorico(recintoId); },
                onCancel: async () => { await renderOperacionesHistorico(recintoId); },
            });
        });
    });

    // Eliminar
    listEl.querySelectorAll(".btn-del-op").forEach(btn => {
        btn.addEventListener("click", async () => {
            const id = btn.dataset.id;

            const ok = await AppConfirm.open({
                title: "Eliminar operación",
                message: "¿Seguro que deseas eliminar la operación? Este proceso no es reversible.",
                okText: "Eliminar",
                cancelText: "Cancelar",
                okClass: "btn-danger"
            });
            if (!ok) return;

            await fetchJson(`/api/operaciones/${id}`, { method: "DELETE" });
            NotificationSystem.show({ type: "success", title: "Operación eliminada", message: "" });
            await renderOperacionesHistorico(recintoId);
        });
    });

    listEl.querySelector("#btn-download-ops-csv")?.addEventListener("click", () => {
        if (!Array.isArray(ops) || ops.length === 0) return;
        const headers = [
            "id_operacion",
            "fecha",
            "tipo",
            "descripcion",

            "riego_volumen_m3",
            "riego_sistema",
            "riego_procedencia",
            "riego_inicio",
            "riego_fin",
            "riego_metodo_medicion",
            "riego_lectura_inicial_m3",
            "riego_lectura_final_m3",

            "fert_tipo",
            "fert_metodo",
            "fert_material",
            "fert_producto_codigo",
            "fert_producto_label",
            "fert_cantidad",
            "fert_unidad",

            "otras_catalogo",
            "otras_codigo",
            "otras_label",

            "observaciones"
        ];

        const rows = (ops || []).map(op => {
            let d = op?.detalle;
            if (typeof d === "string") { try { d = JSON.parse(d); } catch (_) { } }
            d = d || {};
            const t = String(op?.tipo || "").toUpperCase();

            // RIEGO
            const r_vol = t === "RIEGO" ? (d.volumen_m3 ?? d.volumen ?? "") : "";
            const r_sis = t === "RIEGO" ? (d?.sistema_riego?.label || d?.sistema_riego?.codigo || "") : "";
            const r_proc = t === "RIEGO" ? procedenciaAguaToText(d?.procedencia_agua) : "";
            const r_fi = t === "RIEGO" ? (d?.fecha_inicio || "") : "";
            const r_ff = t === "RIEGO" ? (d?.fecha_fin || "") : "";
            const r_met = t === "RIEGO" ? (d?.medicion?.metodo || "") : "";
            const r_li = t === "RIEGO" ? (d?.medicion?.lectura_inicial_m3 ?? "") : "";
            const r_lf = t === "RIEGO" ? (d?.medicion?.lectura_final_m3 ?? "") : "";

            // FERTILIZACION
            const f_tipo = t === "FERTILIZACION" ? (d?.tipo_fertilizacion?.label || d?.tipo_fertilizacion?.codigo || "") : "";
            const f_met = t === "FERTILIZACION" ? (d?.metodo_aplicacion?.label || d?.metodo_aplicacion?.codigo || "") : "";
            const f_mat = t === "FERTILIZACION" ? (d?.material?.label || d?.material?.codigo || "") : "";
            const f_prod_c = t === "FERTILIZACION" ? (d?.producto?.codigo || "") : "";
            const f_prod_l = t === "FERTILIZACION" ? (d?.producto?.label || "") : "";
            const f_cant = t === "FERTILIZACION" ? (d?.cantidad ?? "") : "";
            const f_uni = t === "FERTILIZACION" ? (d?.unidad || "") : "";

            // OTRAS
            const o_cat = t === "OTRAS" ? (d?.catalogo || "") : "";
            const o_cod = t === "OTRAS" ? (d?.codigo || "") : "";
            const o_lab = t === "OTRAS" ? (d?.label || "") : "";

            const obs = d?.observaciones || d?.obs || op?.descripcion || "";

            return [
                op?.id_operacion ?? "",
                formatDateOnly(op?.fecha),
                op?.tipo ?? "",
                op?.descripcion ?? "",

                r_vol,
                r_sis,
                r_proc,
                r_fi,
                r_ff,
                r_met,
                r_li,
                r_lf,

                f_tipo,
                f_met,
                f_mat,
                f_prod_c,
                f_prod_l,
                f_cant,
                f_uni,

                o_cat,
                o_cod,
                o_lab,

                obs ?? ""
            ];
        });

        const csv = rowsToCsv(headers, rows, ";");
        const file = `operaciones_historico_recinto_${recintoId || currentSideRecintoId || "NA"}.csv`;
        downloadCsv(file, csv);
    });

}

// --------------------------
// Catálogos SIEX (helpers)
// --------------------------
const _catCache = new Map();

async function fetchCatalogoOps(catalogo, { parent = null, q = null, limit = 200 } = {}) {
    const key = JSON.stringify({ catalogo, parent, q, limit });
    if (_catCache.has(key)) return _catCache.get(key);

    const params = new URLSearchParams();
    if (parent) params.set("parent", parent);
    if (q) params.set("q", q);
    if (limit) params.set("limit", String(limit));

    const url = `/api/catalogos/operaciones/${encodeURIComponent(String(catalogo).toUpperCase())}` +
        (params.toString() ? `?${params.toString()}` : "");

    const data = await fetchJson(url);
    const arr = Array.isArray(data) ? data : [];
    await Promise.all(arr.map(attachSistemaCultivoLabel));
    _catCache.set(key, arr);
    return arr;
}

// --------------------------------
// Catálogo SIEX: SISTEMA_CULTIVO
// --------------------------------
let _sistemaCultivoMap = null;         // Map<string,string>
let _sistemaCultivoMapPromise = null;  // Promise<Map>

async function loadSistemaCultivoMap() {
    if (_sistemaCultivoMap) return _sistemaCultivoMap;
    if (_sistemaCultivoMapPromise) return _sistemaCultivoMapPromise;

    _sistemaCultivoMapPromise = (async () => {
        const ops = await fetchCatalogoOps("SISTEMA_CULTIVO", { limit: 2000 });
        const m = new Map();
        (ops || []).forEach((it) => {
            const cod = String(it?.codigo ?? "").trim();
            const name = String(it?.nombre || it?.descripcion || "").trim();
            if (cod && name) m.set(cod, name);
        });
        _sistemaCultivoMap = m;
        return m;
    })().catch((err) => {
        console.warn("No se pudo cargar el catálogo SISTEMA_CULTIVO", err);
        _sistemaCultivoMap = new Map();
        return _sistemaCultivoMap;
    });

    return _sistemaCultivoMapPromise;
}

function extractSistemaCultivoCodigo(obj) {
    const sc = obj?.sistema_cultivo;
    const cod =
        (sc && typeof sc === "object" ? sc.codigo : null) ??
        obj?.sistema_cultivo_codigo ??
        null;
    return cod == null ? null : String(cod).trim() || null;
}

async function attachSistemaCultivoLabel(obj) {
    if (!obj) return obj;

    const cod = extractSistemaCultivoCodigo(obj);
    if (!cod) {
        obj._sistema_cultivo_label = null;
        return obj;
    }

    const map = await loadSistemaCultivoMap();
    // Importante: si no hay label, NO devolvemos el código (la UI mostrará "—")
    obj._sistema_cultivo_label = map.get(cod) || null;
    return obj;
}


function fillSelectFromCatalog(selectEl, catalogo, { selected = "", placeholder = "Selecciona...", parent = null, q = null, limit = 500 } = {}) {
    if (!selectEl) return;

    const sel = String(selected ?? "").trim();

    // placeholder
    selectEl.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = placeholder;
    selectEl.appendChild(opt0);

    // construir query
    const params = new URLSearchParams();
    if (parent) params.set("parent", parent);
    if (q) params.set("q", q);
    if (limit) params.set("limit", String(limit));

    const url = `/api/catalogos/operaciones/${encodeURIComponent(String(catalogo).toUpperCase())}` + (params.toString() ? `?${params}` : "");

    fetchJson(url)
        .then(list => {
            const arr = Array.isArray(list) ? list : [];

            for (const r of arr) {
                const code = String(r.codigo ?? "").trim();
                const label = String(r.nombre ?? "").trim() || code;
                if (!code) continue;

                const opt = document.createElement("option");
                opt.value = code;
                opt.textContent = label;
                selectEl.appendChild(opt);
            }

            if (sel) selectEl.value = sel;

            if (sel && selectEl.value !== sel) {
                const opt = document.createElement("option");
                opt.value = sel;
                opt.textContent = sel;
                opt.selected = true;
                selectEl.appendChild(opt);
                selectEl.value = sel;
            }
        })
        .catch(err => {
            console.warn("No se pudo cargar catálogo", catalogo, err);
            if (sel) {
                const opt = document.createElement("option");
                opt.value = sel;
                opt.textContent = sel;
                opt.selected = true;
                selectEl.appendChild(opt);
                selectEl.value = sel;
            }
        });
}


// typeahead muy ligero
function attachTypeaheadCatalog(inputEl, listEl, hiddenCodeEl, catalogo, { minChars = 2, limit = 20 } = {}) {
    if (!inputEl || !listEl) return;

    let lastQ = "";
    let timer = null;

    inputEl.addEventListener("input", () => {
        const q = (inputEl.value || "").trim();
        if (q.length < minChars) {
            listEl.innerHTML = "";
            listEl.classList.add("d-none");
            if (hiddenCodeEl) hiddenCodeEl.value = "";
            return;
        }

        lastQ = q;
        clearTimeout(timer);
        timer = setTimeout(async () => {
            try {
                const rows = await fetchCatalogoOps(catalogo, { q, limit });
                // si el usuario ya cambió el texto, no renderiza resultados viejos
                if (lastQ !== q) return;

                if (!rows.length) {
                    listEl.innerHTML = "";
                    listEl.classList.add("d-none");
                    if (hiddenCodeEl) hiddenCodeEl.value = "";
                    return;
                }

                listEl.innerHTML = rows.map(r => `
            <button type="button" class="list-group-item list-group-item-action"
                    data-code="${escapeHtml(r.codigo)}"
                    data-label="${escapeHtml(r.nombre || r.codigo)}">
              <div class="fw-semibold">${escapeHtml(r.nombre || r.codigo)}</div>
              ${r.descripcion ? `<div class="small text-muted">${escapeHtml(r.descripcion)}</div>` : ``}
            </button>
          `).join("");

                listEl.classList.remove("d-none");

                listEl.querySelectorAll("button").forEach(btn => {
                    btn.addEventListener("click", () => {
                        inputEl.value = btn.dataset.label || "";
                        if (hiddenCodeEl) hiddenCodeEl.value = btn.dataset.code || "";
                        listEl.innerHTML = "";
                        listEl.classList.add("d-none");
                    });
                });

            } catch (e) {
                console.warn("typeahead error", e);
            }
        }, 200);
    });

    // cerrar al perder foco (con delay para permitir click)
    inputEl.addEventListener("blur", () => setTimeout(() => {
        listEl.classList.add("d-none");
    }, 150));
}

// ---------- FORM (inline y overlay) ----------
function renderOperacionForm(container, { recintoId, op = null, mode = "actual", onDone = null, onCancel = null }) {
    if (!container) return;

    // normaliza detalle
    let det = op?.detalle;
    if (typeof det === "string") {
        try { det = JSON.parse(det); } catch (_) { }
    }
    det = det || {};

    const tipoDefault = (op?.tipo || "RIEGO").toUpperCase();

    container.innerHTML = `
      <div class="card op-card" style="border-radius:16px">
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <div class="fw-bold">${op ? "Editar operación" : "Añadir operación"}</div>
            <button id="btn-cancel-op" type="button" class="btn btn-sm btn-outline-secondary">Cancelar</button>
          </div>

          <div class="row g-2">
            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Tipo *</label>
              <select id="op-tipo" class="form-select">
                <option value="RIEGO">Riego</option>
                <option value="FERTILIZACION">Fertilización</option>
                <option value="OTRAS">Otras Operaciones</option>
              </select>
            </div>

            <div class="col-12 col-md-4">
              <label id="op-fecha-label" class="form-label fw-bold">Fecha *</label>
              <input id="op-fecha" class="form-control" type="date">
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Descripción</label>
              <input id="op-desc" class="form-control" type="text" placeholder="(Opcional)">
            </div>
          </div>

          <div class="side-soft-divider" style="margin:14px 0;"></div>

          <div id="op-detalle-slot"></div>

          <div class="mt-3">
            <button id="btn-save-op" type="button" class="btn btn-success w-100">Guardar</button>
            <div id="op-form-msg" class="text-muted" style="font-size:12px; margin-top:8px"></div>
          </div>
        </div>
      </div>
    `;

    const tipoSel = container.querySelector("#op-tipo");
    const fechaInp = container.querySelector("#op-fecha");
    const descInp = container.querySelector("#op-desc");
    const slot = container.querySelector("#op-detalle-slot");
    const msg = container.querySelector("#op-form-msg");

    // defaults
    tipoSel.value = tipoDefault;
    fechaInp.value = op?.fecha ? String(op.fecha).slice(0, 10) : (new Date().toISOString().slice(0, 10));
    descInp.value = op?.descripcion || "";

    function renderDetalle(tipo) {
        const t = String(tipo || "").toUpperCase();

        if (t === "RIEGO") {
            container.querySelector("#op-fecha-label").textContent = (t === "RIEGO") ? "Día *" : "Fecha *";
            const fi = det?.fecha_inicio ? String(det.fecha_inicio).slice(0, 16) : "";
            const ff = det?.fecha_fin ? String(det.fecha_fin).slice(0, 16) : "";
            const vol = det?.volumen_m3 ?? "";
            const sis = det?.sistema_riego?.codigo || "";
            const procArr = normalizeProcedenciaAgua(det?.procedencia_agua);
            const procCodes = procArr.map(x => x.codigo).filter(Boolean);
            const metodo = det?.medicion?.metodo || "MANUAL";
            const li = det?.medicion?.lectura_inicial_m3 ?? "";
            const lf = det?.medicion?.lectura_final_m3 ?? "";
            const obs = det?.observaciones || "";

            slot.innerHTML = `
          <div class="row g-2">
            <div class="col-12 col-md-6">
              <label class="form-label fw-bold">Inicio</label>
              <input id="riego-fi" class="form-control" type="datetime-local" value="${escapeHtml(fi)}">
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label fw-bold">Fin</label>
              <input id="riego-ff" class="form-control" type="datetime-local" value="${escapeHtml(ff)}">
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Volumen (m³) *</label>
              <input id="riego-vol" class="form-control" type="number" step="0.01" min="0" value="${escapeHtml(vol)}">
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Sistema riego *</label>
              <select id="riego-sis" class="form-select"></select>
              <div class="form-text">Catálogo SIEX: RIEGO_SISTEMA</div>
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Procedencia *</label>
              <div id="riego-proc-box" class="border rounded-3 p-2" style="max-height:180px; overflow:auto;"></div>
              <div class="form-text">Catálogo SIEX: RIEGO_PROCEDENCIA</div>
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Medición</label>
              <select id="riego-metodo" class="form-select">
                <option value="MANUAL">Manual</option>
                <option value="CONTADOR">Contador</option>
                <option value="TELEMETRIA">Telemetría</option>
              </select>
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Lectura inicial (m³)</label>
              <input id="riego-li" class="form-control" type="number" step="0.01" min="0" value="${escapeHtml(li)}">
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Lectura final (m³)</label>
              <input id="riego-lf" class="form-control" type="number" step="0.01" min="0" value="${escapeHtml(lf)}">
            </div>

            <div class="col-12">
              <label class="form-label fw-bold">Observaciones</label>
              <textarea id="riego-obs" class="form-control" rows="2" placeholder="(Opcional)">${escapeHtml(obs)}</textarea>
            </div>
          </div>
        `;

            fillSelectFromCatalog(slot.querySelector("#riego-sis"), "RIEGO_SISTEMA", { selected: sis, placeholder: "Sistema..." });
            (async () => {
                const box = slot.querySelector("#riego-proc-box");
                const list = await fetchCatalogoOps("RIEGO_PROCEDENCIA", { limit: 500 });

                const selectedCodes = new Set(procCodes);

                box.innerHTML = list.map(r => {
                    const code = String(r.codigo ?? "").trim();
                    const label = String(r.nombre ?? "").trim() || code;
                    const checked = selectedCodes.has(code) ? "checked" : "";
                    return `
              <label class="d-flex align-items-center gap-2 mb-1" style="font-size:13px">
                <input class="form-check-input riego-proc-chk" type="checkbox" value="${escapeHtml(code)}" ${checked}>
                <span>${escapeHtml(label)}</span>
              </label>
            `;
                }).join("");
            })();

            slot.querySelector("#riego-metodo").value = metodo;

            const fechaMain = container.querySelector("#op-fecha");
            const fiEl = slot.querySelector("#riego-fi");

            fiEl?.addEventListener("change", () => {
                if (fiEl.value) fechaMain.value = fiEl.value.slice(0, 10);
            });

            fechaMain?.addEventListener("change", () => {
                if (!fiEl.value && fechaMain.value) {
                    fiEl.value = `${fechaMain.value}T00:00`;
                }
            });

            return;
        }

        // FERTILIZACION
        const tipoF = det?.tipo_fertilizacion?.codigo || "";
        const prodCode = det?.producto?.codigo || "";
        const prodLabel = det?.producto?.label || "";
        const cant = det?.cantidad ?? "";
        const uni = det?.unidad || "kg";
        const met = det?.metodo_aplicacion?.codigo || "";
        const mat = det?.material?.codigo || "";
        const obs = det?.observaciones || "";

        slot.innerHTML = `
        <div class="row g-2">

          <div class="col-12 col-md-4">
            <label class="form-label fw-bold">Tipo fertilización *</label>
            <select id="fer-tipo" class="form-select"></select>
            <div class="form-text">Catálogo SIEX: FERT_TIPO</div>
          </div>

          <div class="col-12 col-md-4">
            <label class="form-label fw-bold">Método aplicación</label>
            <select id="fer-metodo" class="form-select"></select>
            <div class="form-text">Catálogo SIEX: FERT_METODO</div>
          </div>

          <div class="col-12 col-md-4">
            <label class="form-label fw-bold">Material</label>
            <select id="fer-material" class="form-select"></select>
            <div class="form-text">Catálogo SIEX: FERT_MATERIAL</div>
          </div>

          <div class="col-12 col-md-6 position-relative">
            <label class="form-label fw-bold">Producto *</label>
            <input id="fer-prod" class="form-control" type="text" placeholder="Escribe para buscar..." value="${escapeHtml(prodLabel)}">
            <input id="fer-prod-code" type="hidden" value="${escapeHtml(prodCode)}">
            <div id="fer-prod-list" class="list-group position-absolute w-100 d-none" style="z-index:1050; max-height:220px; overflow:auto;"></div>
            <div class="form-text">Catálogo SIEX: FERT_PRODUCTO (búsqueda)</div>
          </div>

          <div class="col-6 col-md-3">
            <label class="form-label fw-bold">Cantidad *</label>
            <input id="fer-cant" class="form-control" type="number" step="0.01" min="0" value="${escapeHtml(cant)}">
          </div>

          <div class="col-6 col-md-3">
            <label class="form-label fw-bold">Unidad</label>
            <select id="fer-uni" class="form-select">
              <option value="kg">kg</option>
              <option value="t">t</option>
              <option value="l">l</option>
            </select>
          </div>

          <div class="col-12">
            <label class="form-label fw-bold">Observaciones</label>
            <textarea id="fer-obs" class="form-control" rows="2" placeholder="(Opcional)">${escapeHtml(obs)}</textarea>
          </div>

          <div class="accordion mt-2" id="fert-adv-acc">
            <div class="accordion-item">
              <h2 class="accordion-header" id="fert-adv-h">
                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#fert-adv-c">
                  Avanzado (opcional)
                </button>
              </h2>
              <div id="fert-adv-c" class="accordion-collapse collapse" data-bs-parent="#fert-adv-acc">
                <div class="accordion-body">
                  <div class="row g-2">
                    <div class="col-12 col-md-4">
                      <label class="form-label fw-bold">Macronutriente</label>
                      <select id="fer-macro" class="form-select"></select>
                    </div>
                    <div class="col-12 col-md-4">
                      <label class="form-label fw-bold">Micronutriente</label>
                      <select id="fer-micro" class="form-select"></select>
                    </div>
                    <div class="col-12 col-md-4">
                      <label class="form-label fw-bold">Metales pesados</label>
                      <select id="fer-metales" class="form-select"></select>
                    </div>
                    <div class="col-12 col-md-6">
                      <label class="form-label fw-bold">Tratamiento estiércoles</label>
                      <select id="fer-estiercol" class="form-select"></select>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>
      `;

        // cargar selects
        fillSelectFromCatalog(slot.querySelector("#fer-tipo"), "FERT_TIPO", { selected: tipoF, placeholder: "Tipo..." });
        fillSelectFromCatalog(slot.querySelector("#fer-metodo"), "FERT_METODO", { selected: met, placeholder: "Método..." });
        fillSelectFromCatalog(slot.querySelector("#fer-material"), "FERT_MATERIAL", { selected: mat, placeholder: "Material..." });
        fillSelectFromCatalog(slot.querySelector("#fer-macro"), "FERT_MACRO", { selected: det?.composicion_opcional?.macro?.codigo || "", placeholder: "(Opcional)" });
        fillSelectFromCatalog(slot.querySelector("#fer-micro"), "FERT_MICRO", { selected: det?.composicion_opcional?.micro?.codigo || "", placeholder: "(Opcional)" });
        fillSelectFromCatalog(slot.querySelector("#fer-metales"), "FERT_METALES", { selected: det?.composicion_opcional?.metales?.codigo || "", placeholder: "(Opcional)" });
        fillSelectFromCatalog(slot.querySelector("#fer-estiercol"), "FERT_TRAT_ESTIERCOL", { selected: det?.tratamiento_estiercol?.codigo || "", placeholder: "(Opcional)" });


        // typeahead producto
        attachTypeaheadCatalog(
            slot.querySelector("#fer-prod"),
            slot.querySelector("#fer-prod-list"),
            slot.querySelector("#fer-prod-code"),
            "FERT_PRODUCTO",
            { minChars: 2, limit: 20 }
        );

        // defaults
        slot.querySelector("#fer-uni").value = uni;

        // OTRAS
        if (t === "OTRAS") {
            // defaults
            const cat = det?.catalogo || "";
            const codigo = det?.codigo || "";
            const parent = det?.parent || "";

            slot.innerHTML = `
          <div class="row g-2">
            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Catálogo *</label>
              <select id="otras-cat" class="form-select">
                <option value="">Selecciona...</option>
                <option value="ACTIVIDAD_AGRARIA">Actividad agraria</option>
                <option value="ACTIVIDAD_CUBIERTA">Actividad sobre la cubierta</option>
              </select>
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Opción *</label>
              <select id="otras-item" class="form-select" disabled>
                <option value="">Selecciona catálogo primero...</option>
              </select>
              <div class="form-text">Catálogo SIEX: el que elijas arriba</div>
            </div>

            <div class="col-12 col-md-4">
              <label class="form-label fw-bold">Observaciones</label>
              <input id="otras-obs" class="form-control" type="text" placeholder="(Opcional)" value="${escapeHtml(det?.observaciones || "")}">
            </div>
          </div>
        `;

            const catSel = slot.querySelector("#otras-cat");
            const itemSel = slot.querySelector("#otras-item");

            // set catálogo
            catSel.value = cat;

            function loadItems() {
                const c = (catSel.value || "").trim();
                if (!c) {
                    itemSel.disabled = true;
                    itemSel.innerHTML = `<option value="">Selecciona catálogo primero...</option>`;
                    return;
                }
                itemSel.disabled = false;
                fillSelectFromCatalog(itemSel, c, { selected: codigo, placeholder: "Selecciona..." });
            }

            catSel.addEventListener("change", () => {
                itemSel.value = "";
                loadItems();
            });

            loadItems();
            return;
        }

    }

    renderDetalle(tipoSel.value);

    tipoSel.addEventListener("change", () => {
        det = {}; // cambia tipo => limpia detalle
        renderDetalle(tipoSel.value);
    });

    container.querySelector("#btn-cancel-op")?.addEventListener("click", () => {
        onCancel?.();
    });

    container.querySelector("#btn-save-op")?.addEventListener("click", async () => {
        msg.textContent = "";
        msg.className = "text-muted";

        const tipo = String(tipoSel.value || "").toUpperCase();
        const fecha = parseDateToISO(fechaInp.value);
        const descripcion = (descInp.value || "").trim() || null;

        if (!tipo) { msg.textContent = "Selecciona el tipo."; msg.className = "text-danger"; return; }
        if (!fecha) { msg.textContent = "Selecciona la fecha."; msg.className = "text-danger"; return; }

        // Construir payload
        const payload = {
            schema_version: 1,
            tipo,
            fecha,
            descripcion,
            detalle: {}
        };

        if (tipo === "RIEGO") {
            const vol = Number(slot.querySelector("#riego-vol")?.value);
            if (!Number.isFinite(vol) || vol < 0) {
                msg.textContent = "Volumen (m³) inválido.";
                msg.className = "text-danger";
                return;
            }

            const sisSel = slot.querySelector("#riego-sis");

            const sisCode = (sisSel?.value || "").trim();

            const box = slot.querySelector("#riego-proc-box");
            const checked = Array.from(box?.querySelectorAll(".riego-proc-chk:checked") || []);

            const procedencias = checked.map(chk => ({
                codigo: chk.value,
                label: (chk.parentElement?.querySelector("span")?.textContent || "").trim() || chk.value,
                fuente: "SIEX"
            }));

            if (!sisCode) { msg.textContent = "Selecciona el sistema de riego."; msg.className = "text-danger"; return; }
            if (!procedencias.length) { msg.textContent = "Selecciona la procedencia del agua."; msg.className = "text-danger"; return; }

            const metodo = slot.querySelector("#riego-metodo")?.value || "MANUAL";

            const fi = slot.querySelector("#riego-fi")?.value || null;
            const ff = slot.querySelector("#riego-ff")?.value || null;

            const li = slot.querySelector("#riego-li")?.value;
            const lf = slot.querySelector("#riego-lf")?.value;

            payload.detalle = {
                fecha_inicio: fi ? fi : null,
                fecha_fin: ff ? ff : null,
                volumen_m3: vol,

                sistema_riego: {
                    codigo: sisCode,
                    label: (sisSel?.selectedOptions?.[0]?.textContent || "").trim() || sisCode,
                    fuente: "SIEX"
                },
                procedencia_agua: procedencias,
                medicion: {
                    metodo,
                    lectura_inicial_m3: (li !== "" && li != null) ? Number(li) : null,
                    lectura_final_m3: (lf !== "" && lf != null) ? Number(lf) : null
                },
                observaciones: (slot.querySelector("#riego-obs")?.value || "").trim() || null
            };
        }

        if (tipo === "FERTILIZACION") {
            const tipoSel = slot.querySelector("#fer-tipo");
            const metSel = slot.querySelector("#fer-metodo");
            const matSel = slot.querySelector("#fer-material");
            const macroSel = slot.querySelector("#fer-macro");
            const microSel = slot.querySelector("#fer-micro");
            const metalSel = slot.querySelector("#fer-metales");
            const estSel = slot.querySelector("#fer-estiercol");

            const tipoCode = tipoSel?.value || "";
            const tipoLabel = (tipoSel?.selectedOptions?.[0]?.textContent || "").trim() || tipoCode;

            const metCode = metSel?.value || "";
            const metLabel = (metSel?.selectedOptions?.[0]?.textContent || "").trim() || metCode;

            const matCode = matSel?.value || "";
            const matLabel = (matSel?.selectedOptions?.[0]?.textContent || "").trim() || matCode;

            const prodLabel = (slot.querySelector("#fer-prod")?.value || "").trim();
            const prodCode = (slot.querySelector("#fer-prod-code")?.value || "").trim() || null;

            const cant = Number(slot.querySelector("#fer-cant")?.value);
            const uni = slot.querySelector("#fer-uni")?.value || "kg";

            if (!tipoCode) { msg.textContent = "Selecciona el tipo de fertilización."; msg.className = "text-danger"; return; }
            if (!prodLabel) { msg.textContent = "Indica el producto."; msg.className = "text-danger"; return; }
            if (!Number.isFinite(cant) || cant <= 0) { msg.textContent = "Cantidad inválida."; msg.className = "text-danger"; return; }

            function pickOpt(sel) {
                const code = (sel?.value || "").trim();
                if (!code) return null;
                const label = (sel?.selectedOptions?.[0]?.textContent || "").trim() || code;
                return { codigo: code, label, fuente: "SIEX" };
            }

            payload.detalle = {
                tipo_fertilizacion: { codigo: tipoCode, label: tipoLabel, fuente: "SIEX" },
                metodo_aplicacion: metCode ? { codigo: metCode, label: metLabel, fuente: "SIEX" } : null,
                material: matCode ? { codigo: matCode, label: matLabel, fuente: "SIEX" } : null,
                producto: { codigo: prodCode, label: prodLabel, fuente: "SIEX" },
                cantidad: cant,
                unidad: uni,
                observaciones: (slot.querySelector("#fer-obs")?.value || "").trim() || null
            };

            payload.detalle.composicion_opcional = {
                macro: pickOpt(macroSel),
                micro: pickOpt(microSel),
                metales: pickOpt(metalSel),
            };

            payload.detalle.tratamiento_estiercol = pickOpt(estSel);
        }

        if (tipo === "OTRAS") {
            const cat = slot.querySelector("#otras-cat")?.value || "";
            const cod = slot.querySelector("#otras-item")?.value || "";
            const label = (slot.querySelector("#otras-item")?.selectedOptions?.[0]?.textContent || "").trim();
            const obs = (slot.querySelector("#otras-obs")?.value || "").trim() || null;

            if (!cat) { msg.textContent = "Selecciona catálogo."; msg.className = "text-danger"; return; }
            if (!cod) { msg.textContent = "Selecciona una opción."; msg.className = "text-danger"; return; }

            payload.detalle = {
                catalogo: cat,
                codigo: cod,
                label: label || cod,
                observaciones: obs
            };
        }

        // ENDPOINTS
        try {
            if (op && op.id_operacion) {
                await fetchJson(`/api/operaciones/${op.id_operacion}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
            } else {
                await fetchJson(`/api/mis-recinto/${recintoId}/operaciones`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
            }

            NotificationSystem.show({ type: "success", title: "Operación guardada", message: "" });
            onDone?.();

        } catch (e) {
            console.warn(e);
            const backendMsg = e?.data?.error || e?.data?.message || "";
            msg.textContent = backendMsg || "No se pudo guardar la operación.";
            msg.className = "text-danger";
        }
    });
}

// Función para actualizar el histórico de operaciones
function actualizarHistoricoOperaciones() {
  const sp = document.getElementById("side-panel");
  const panel = document.getElementById("operaciones-historico-panel");
  
  if (sp && panel && sp.classList.contains("operaciones-open")) {
    // El panel está abierto, recargar los datos
    if (currentSideRecintoId) {
      renderOperacionesHistorico(currentSideRecintoId);
    }
    return true;
  }
  return false;
}