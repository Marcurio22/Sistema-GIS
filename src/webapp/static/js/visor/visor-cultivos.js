// ==========================================================
// Cultivos (UI del panel derecho)
// Requiere endpoints (a implementar en backend):
//   GET    /api/catalogos/usos-sigpac
//   GET    /api/catalogos/productos-fega
//   GET    /api/mis-recinto/<id>/cultivo            -> 404 si no hay
//   POST   /api/cultivos                           -> crea
//   PATCH  /api/cultivos/<id_cultivo>              -> actualiza
//   DELETE /api/cultivos/<id_cultivo>              -> elimina
// ==========================================================

let _usosSigpac = null;     // [{codigo, descripcion, grupo}]
let _productosFega = null;  // [{codigo, descripcion}]

// Para "N/A - ALTRAMUZ", etc...
const _cultivosCustom = [
    { codigo: null, descripcion: "SIN CULTIVO" },
    { codigo: null, descripcion: "ALTRAMUZ" },
    { codigo: null, descripcion: "ALTRAMUZ DULCE" }
];

async function fetchJson(url, opts = {}, allow404 = false) {
    const resp = await fetch(url, opts);
    const txt = await resp.text().catch(() => "");

    let data = null;
    try { data = txt ? JSON.parse(txt) : null; } catch (_) { }

    if (!resp.ok) {
        // Caso esperado: "no hay cultivo todavía"
        if (allow404 && resp.status === 404) return null;

        const err = new Error(`HTTP ${resp.status} en ${url}`);
        err.status = resp.status;
        err.url = url;
        err.body = txt;
        err.data = data;

        console.warn("fetchJson error", resp.status, url, txt);
        throw err;
    }

    return data; // puede ser null si no hay JSON
}

// Convierte fechas de inputs a ISO (YYYY-MM-DD).
// Acepta: YYYY-MM-DD (input type="date"), DD/MM/YYYY y DD-MM-YYYY.
function parseDateToISO(v) {
    if (!v) return null;
    const s = String(v).trim();
    if (!s) return null;

    // Ya viene en ISO
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;

    // DD/MM/YYYY
    let m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;

    // DD-MM-YYYY
    m = s.match(/^(\d{2})-(\d{2})-(\d{4})$/);
    if (m) return `${m[3]}-${m[2]}-${m[1]}`;

    // Como último recurso: intenta Date()
    const d = new Date(s);
    if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);

    return null;
}

const toISODate = parseDateToISO;

async function loadUsosSigpac() {
    if (_usosSigpac) return _usosSigpac;
    _usosSigpac = await fetchJson("/api/catalogos/usos-sigpac");
    return _usosSigpac;
}

async function loadProductosFega() {
    if (_productosFega) return _productosFega;
    _productosFega = await fetchJson("/api/catalogos/productos-fega");
    return _productosFega;
}

const _productosFegaByUso = new Map();

async function loadProductosFegaPorUso(usoSigpac) {
    const key = String(usoSigpac || "").trim();
    if (!key) return [];
    if (_productosFegaByUso.has(key)) return _productosFegaByUso.get(key);
    const list = await fetchJson(`/api/catalogos/productos-fega/${encodeURIComponent(key)}`);
    _productosFegaByUso.set(key, list || []);
    return list || [];
}

function byCodigo(list) {
    const m = new Map();
    (list || []).forEach(it => m.set(String(it.codigo), it));
    return m;
}

function norm(s) {
    return String(s ?? "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

function formatCodigoDesc(codigo, descripcion) {
    const code = (codigo === null || codigo === undefined || codigo === "") ? "N/A" : String(codigo);
    const desc = safeText(descripcion, "N/A");
    return `${code}-${desc}`;
}

function guessGrupoUso(usoCode, usosMap) {
    const u = usosMap.get(String(usoCode));
    return u?.grupo || null;
}

async function getCultivoRecinto(recintoId) {
    const raw = await fetchJson(`/api/mis-recinto/${recintoId}/cultivo`, {}, true);
    if (!raw) return null;

    const cultivo = normalizeCultivoFromApi(raw);
    await attachSistemaCultivoLabel(cultivo);
    return cultivo;
}

async function renderCultivosForRecinto(recintoId) {
    const container = document.getElementById("cultivos-container");
    if (!container) return;

    container.innerHTML = `<div class="text-muted">Cargando cultivos...</div>`;

    let usos = [];
    let productos = [];
    try {
        [usos, productos] = await Promise.all([loadUsosSigpac(), loadProductosFega()]);
    } catch (e) {
        console.warn(e);
        container.innerHTML = `
    <div class="text-danger">No se pudieron cargar los catálogos (SIGPAC/FEGA).</div>
    <div class="text-muted" style="font-size:12px">Revisa /api/catalogos/usos-sigpac y /api/catalogos/productos-fega</div>
    `;
        return;
    }

    try {
        const cultivo = await getCultivoRecinto(recintoId);

        // ✅ Caso normal: no hay cultivo
        if (!cultivo) {
            renderCultivoEmpty(container, recintoId, usos, productos);
            return;
        }

        renderCultivoView(container, recintoId, cultivo, usos, productos);
    } catch (e) {
        console.warn(e);
        container.innerHTML = `<div class="text-danger">Error cargando cultivo del recinto.</div>`;
    }
}

function renderCultivoEmpty(container, recintoId, usos, productos) {
    container.innerHTML = `
    <button id="btn-add-cultivo" type="button" class="btn btn-success w-100">
    Añadir cultivo
    </button>
    <div class="text-muted" style="font-size:12px; margin-top:8px">
    Añade un cultivo a este recinto (FEGA o personalizado).
    </div>
`;
    container.querySelector("#btn-add-cultivo").addEventListener("click", () => {
        renderCultivoForm(container, { recintoId, cultivo: null, usos, productos });
    });
}

function estadoLabel(v) {
    const s = String(v || "").toLowerCase().trim();
    const map = {
        planificado: "Planificado",
        en_curso: "En curso",
        implantado: "Plantado",
        cosechado: "Cosechado",
        abandonado: "Abandonado"
    };
    return map[s] || safeText(v, "N/A");
}

let needsRefreshActualCultivo = false;

function openHistoricoPanel() {
    const sp = document.getElementById("side-panel");
    const panel = document.getElementById("cultivos-historico-panel");
    if (!sp || !panel) return;
    sp.classList.add("cultivos-historico-open");
    panel.classList.remove("d-none");
    panel.setAttribute("aria-hidden", "false");
}

function closeHistoricoPanel() {
    const sp = document.getElementById("side-panel");
    const panel = document.getElementById("cultivos-historico-panel");
    if (!sp || !panel) return;
    sp.classList.remove("cultivos-historico-open");
    panel.classList.add("d-none");
    panel.setAttribute("aria-hidden", "true");

    // si se tocó el cultivo actual desde el histórico, repinta el actual al volver
    if (needsRefreshActualCultivo && currentSideRecintoId) {
        needsRefreshActualCultivo = false;
        renderCultivosForRecinto(currentSideRecintoId);
    }
}

window.openGaleriaPanel = function openGaleriaPanel() {
    const sp = document.getElementById("side-panel");
    const overlay = document.getElementById("galeria-panel");
    const body = document.getElementById("galeria-panel-body");
    const gal = document.getElementById("galeria-imagenes");
    const historico = document.getElementById("cultivos-historico-panel");
    if (!sp || !overlay || !body || !gal || !historico) return;

    // Cierra histórico si estuviera abierto
    closeHistoricoPanel?.();

    // Mover galería dentro del overlay (evita duplicados / pisadas)
    body.appendChild(gal);

    // Activar estado
    sp.classList.add("galeria-open");
    overlay.classList.remove("d-none");
    overlay.setAttribute("aria-hidden", "false");
};

window.closeGaleriaPanel = function closeGaleriaPanel() {
    const sp = document.getElementById("side-panel");
    const overlay = document.getElementById("galeria-panel");
    const gal = document.getElementById("galeria-imagenes");
    const historico = document.getElementById("cultivos-historico-panel");
    if (!sp || !overlay || !gal || !historico) return;

    // Devolver galería a su sitio (antes del histórico)
    historico.parentNode.insertBefore(gal, historico);

    // Desactivar estado
    sp.classList.remove("galeria-open");
    overlay.classList.add("d-none");
    overlay.setAttribute("aria-hidden", "true");
};

// // Botones del overlay
// document.getElementById("btn-volver-galeria")?.addEventListener("click", (e) => {
//   e.preventDefault(); e.stopPropagation();
//   closeGaleriaPanel();
// });

// document.getElementById("btn-cerrar-galeria")?.addEventListener("click", (e) => {
//   e.preventDefault(); e.stopPropagation();
//   document.getElementById("side-close")?.click(); // cierra el split completo
// });

(function initGaleriaOverlayButtonsOnce() {
    const volver = document.getElementById("btn-volver-galeria");
    const cerrar = document.getElementById("btn-cerrar-galeria");

    if (volver && !volver.dataset.bound) {
        volver.dataset.bound = "1";
        volver.addEventListener("click", (e) => {
            e.preventDefault(); e.stopPropagation();

            // Preferimos el controlador propio de la galería si existe,
            // si no, cerramos el overlay directamente.
            if (window.galeria?.contraerGaleria) window.galeria.contraerGaleria();
            else closeGaleriaPanel();
        });
    }

    if (cerrar && !cerrar.dataset.bound) {
        cerrar.dataset.bound = "1";
        cerrar.addEventListener("click", (e) => {
            e.preventDefault(); e.stopPropagation();
            document.getElementById("side-close")?.click();
        });
    }
})();


document.getElementById("btn-cerrar-historico")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    document.getElementById("side-close")?.click();
});

document.getElementById("btn-volver-historico")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    closeHistoricoPanel();
});

function openAvanzadoModal(av) {
    const body = document.getElementById("modalAvanzadoCultivoBody");
    if (!body) return;

    if (typeof av === "string") { try { av = JSON.parse(av); } catch (_) { av = null; } }

    if (!hasAvanzado(av)) {
        body.innerHTML = `<div class="text-muted">No hay datos avanzados.</div>`;
    } else {
        const rows = [];

        function addRow(label, obj) {
            if (!obj || typeof obj !== "object") return;
            const v = obj.label || obj.codigo;
            if (!v) return;
            rows.push(`<tr><th style="width:45%">${escapeHtml(label)}</th><td>${escapeHtml(v)}</td></tr>`);
        }

        addRow("Aprovechamiento", av.aprovechamiento);
        addRow("Tipo cobertura del suelo", av.tipo_cobertura_suelo);
        addRow("Destino del cultivo", av.destino_cultivo);

        // material vegetal
        if (av.material_vegetal) {
            addRow("Material vegetal - tipo", av.material_vegetal.tipo);
            addRow("Material vegetal - detalle", av.material_vegetal.detalle);
        }

        addRow("Tipo de labor", av.tipo_labor);
        addRow("Procedencia material vegetal", av.procedencia_material_vegetal);
        addRow("SENP", av.senp);

        body.innerHTML = `
    <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
        <tbody>${rows.join("")}</tbody>
        </table>
    </div>
    `;
    }

    const el = document.getElementById("modalAvanzadoCultivo");
    const modal = bootstrap.Modal.getOrCreateInstance(el);
    modal.show();
}

document.getElementById("btn-historico-cultivos")?.addEventListener("click", async (e) => {
    e.preventDefault();
    e.stopPropagation();

    if (!currentSideRecintoId) return;

    openHistoricoPanel();

    const listEl = document.getElementById("cultivos-historico-list");

    // Repinta histórico entero
    const reloadHistorico = async () => {
        if (!currentSideRecintoId) return;

        listEl.innerHTML = `<div class="text-muted">Cargando histórico...</div>`;

        let currentCultivoId = null;
        try {
            const cur = await getCultivoRecinto(currentSideRecintoId);
            currentCultivoId = cur?.id_cultivo ?? null;
        } catch (e) {
            if (!(e && e.status === 404)) throw e;
        }

        try {
            const [usos, productos, hist] = await Promise.all([
                loadUsosSigpac(),
                loadProductosFega(),
                fetchJson(`/api/mis-recinto/${currentSideRecintoId}/cultivos-historico`)
            ]);

            const usosMap = byCodigo(usos);
            const prodMap = byCodigo(productos);

            const arr = (Array.isArray(hist) ? hist : []).map(normalizeCultivoFromApi);
            const count = arr.length;

            listEl.innerHTML = `
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div class="d-flex align-items-center gap-2">
            <i class="bi bi-journal-check text-success"></i>
            <span>Registro completo</span>
            <span class="badge bg-success">${count}</span>
        </div>

        <div class="d-flex gap-2 ms-auto">
            <button id="btn-download-cultivos-csv"
            class="btn btn-outline-success btn-sm"
            ${Number(count) > 0 ? "" : "disabled"}
            title="${count ? "" : "No hay datos para exportar"}" type="button">
            <i class="bi bi-download me-1"></i> CSV
            </button>
            <button id="btn-add-historico" class="btn btn-success btn-sm">
            + Añadir al Histórico
            </button>
        </div>
        </div>

        <div class="side-divider"></div>
        <div id="historico-cards"></div>
    `;

            // CSV disabled: gris + tooltip (el title no funciona en button disabled)
            const csvBtn = listEl.querySelector("#btn-download-cultivos-csv");
            if (csvBtn && csvBtn.disabled) {
                csvBtn.classList.remove("btn-outline-success");
                csvBtn.classList.add("btn-outline-secondary");

                const wrap = document.createElement("span");
                wrap.className = "d-inline-block";
                wrap.title = "Ahora mismo no se puede descargar CSV";

                csvBtn.parentNode.insertBefore(wrap, csvBtn);
                wrap.appendChild(csvBtn);
            }

            const cardsEl = listEl.querySelector("#historico-cards");

            if (!arr.length) {
                cardsEl.innerHTML = `<div class="text-muted">No hay histórico todavía.</div>`;
            } else {
                const COLS = 11;

                cardsEl.innerHTML = `
            <div class="table-responsive historico-table-wrap">
            <table class="table table-sm table-hover align-middle historico-table mb-0">
                <thead>
                <tr>
                    <th style="min-width:140px;">Fechas</th>
                    <th style="min-width:180px;">Uso SIGPAC</th>
                    <th style="min-width:180px;">Tipo cultivo</th>
                    <th style="min-width:140px;">Variedad</th>
                    <th style="min-width:120px;">Explotación</th>
                    <th style="min-width:170px;">Sistema cultivo</th>
                    <th style="min-width:150px;">Avanzado</th>
                    <th style="min-width:160px;">Campaña / Registro</th>
                    <th style="min-width:120px;">Estado</th>
                    <th style="min-width:220px;">Observaciones</th>
                    <th style="min-width:170px;" class="text-end">Acciones</th>
                </tr>
                </thead>
                <tbody>
                ${arr.map((c) => {
                    console.log("Render cultivo histórico:", c);
                    const isCamp = String(c.tipo_registro || "").toUpperCase().includes("CAMP");
                    const inicio = isCamp ? c.fecha_siembra : c.fecha_implantacion;
                    const fin = c.fecha_cosecha_real || c.fecha_cosecha_estimada;

                    const isCurrent = currentCultivoId && String(c.id_cultivo) === String(currentCultivoId);

                    const u = usosMap.get(String(c.uso_sigpac));
                    const usoLbl = formatCodigoDesc(c.uso_sigpac, u?.descripcion || c.uso_sigpac);

                    let tipoLbl = "N/A";
                    const origen = String(c.origen_cultivo || "").toUpperCase();
                    if (origen === "F" && c.cod_producto != null) {
                        const p = prodMap.get(String(c.cod_producto));
                        tipoLbl = formatCodigoDesc(c.cod_producto, p?.descripcion || c.tipo_cultivo);
                    } else {
                        tipoLbl = formatCodigoDesc(null, c.cultivo_custom || c.tipo_cultivo);
                    }

                    const campOrReg = isCamp
                        ? safeText(c.campana, "N/A")
                        : safeText(tipoRegistroLabel(c.tipo_registro));

                    const obsText = (c.observaciones && String(c.observaciones).trim()) ? String(c.observaciones) : "";
                    const hasObs = !!obsText.trim();

                    const sisCult = c.sistema_cultivo;
                    const sisCultLbl = sisCult?.label
                        ? String(sisCult.label).trim()
                        : "—";

                    const advYes = hasAvanzado(c.avanzado);

                    // Preview corto (sin saltos) + botón Ver/Ocultar
                    const obsOneLine = hasObs ? obsText.replace(/\s+/g, " ").trim() : "";
                    const obsPreview = hasObs
                        ? escapeHtml(obsOneLine.slice(0, 70) + (obsOneLine.length > 70 ? "…" : ""))
                        : "";

                    const showToggle = hasObs || isCurrent; // aunque no haya obs, el actual tiene aviso útil
                    const targetId = `hist-obs-${c.id_cultivo}`;

                    const obsCellHtml = hasObs
                        ? `<span class="hist-obs-preview">${obsPreview}</span>`
                        : `<span class="text-muted">(Sin observaciones)</span>`;

                    const toggleBtn = showToggle
                        ? `<button type="button"
                                class="btn btn-outline-success btn-sm btn-toggle-obs"
                                data-target="${targetId}"
                                aria-expanded="false">
                            Ver
                        </button>`
                        : ``;

                    const obsFullHtml = hasObs
                        ? `<div class="border rounded-3 p-2 hist-obs-box" style="white-space:pre-wrap;">${escapeHtml(obsText)}</div>`
                        : `<div class="text-muted">(Sin observaciones)</div>`;

                   return `
                    <tr>
                        <td class="hist-fechas">
                        ${safeText(formatDateOnly(inicio))} → ${safeText(formatDateOnly(fin))}
                        ${isCurrent ? `<span class="badge bg-success ms-2">Actual</span>` : ``}
                        </td>

                        <td>${safeText(usoLbl)}</td>
                        <td>${safeText(tipoLbl)}</td>
                        <td>${safeText(c.variedad, "N/A")}</td>
                        <td>${safeText(sistemaLabel(c.sistema_explotacion))}</td>
                        <td>${sisCultLbl ? escapeHtml(sisCultLbl) : "<span class='text-muted'>—</span>"}</td>
                        <td>
                        ${advYes
                            ? `<span class="badge bg-success me-2">Sí</span>
                            <button type="button"
                                    class="btn btn-outline-success btn-sm btn-ver-avanzado"
                                    data-id="${c.id_cultivo}">
                                Ver
                            </button>`
                            : `<span class="badge bg-secondary">No</span>`
                        }
                        </td>
                        <td>${campOrReg}</td>
                        <td>${estadoLabel(c.estado)}</td>

                        <td>
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                            ${obsCellHtml}
                            ${toggleBtn}
                        </div>
                        </td>

                        <td class="text-end">
                        <div class="d-flex gap-2 justify-content-end flex-wrap hist-actions">
                            <button class="btn btn-success btn-sm btn-edit-hist" data-id="${c.id_cultivo}">
                            <i class="bi bi-pencil-fill me-1"></i> Editar
                            </button>
                            <button class="btn btn-danger btn-sm btn-del-hist" data-id="${c.id_cultivo}" ${isCurrent ? "disabled" : ""}>
                            <i class="bi bi-trash-fill me-1"></i> Eliminar
                            </button>
                        </div>
                        </td>
                    </tr>

                    <tr id="${targetId}" class="hist-obs-row d-none">
                        <td colspan="${COLS}">
                        <div class="hist-obs-detail">
                            <div class="fw-bold mb-2">Observaciones</div>
                            ${obsFullHtml}

                            ${isCurrent ? `
                            <div class="text-muted mt-2" style="font-size:12px">
                                Este es el cultivo actual. Para eliminarlo, hazlo desde la página principal del cultivo.
                            </div>
                            ` : ``}
                        </div>
                        </td>
                    </tr>
                    `;
                }).join("")}
                </tbody>
            </table>
            </div>
        `;

                // Toggle Observaciones (Ver/Ocultar)
                cardsEl.querySelectorAll(".btn-toggle-obs").forEach(btn => {
                    btn.addEventListener("click", (ev) => {
                        const b = ev.currentTarget;
                        const targetId = b.dataset.target;
                        const row = cardsEl.querySelector(`#${CSS.escape(targetId)}`);
                        if (!row) return;

                        const isHidden = row.classList.contains("d-none");
                        row.classList.toggle("d-none", !isHidden);

                        b.textContent = isHidden ? "Ocultar" : "Ver";
                        b.setAttribute("aria-expanded", isHidden ? "true" : "false");
                    });
                });

                // Eliminar registro (igual que antes)
                cardsEl.querySelectorAll(".btn-del-hist").forEach(btn => {
                    btn.addEventListener("click", async (ev) => {
                        const id = ev.currentTarget.dataset.id;

                        const ok = await AppConfirm.open({
                            title: "Eliminar cultivo",
                            message: "¿Seguro que deseas eliminar el cultivo? Este proceso no es reversible.",
                            okText: "Eliminar",
                            cancelText: "Cancelar",
                            okClass: "btn-danger"
                        });
                        if (!ok) return;

                        await fetchJson(`/api/cultivos/${id}`, { method: "DELETE" });
                        await reloadHistorico();
                    });
                });

                // Editar registro (igual que antes)
                cardsEl.querySelectorAll(".btn-edit-hist").forEach(btn => {
                    btn.addEventListener("click", (ev) => {
                        const id = ev.currentTarget.dataset.id;
                        const item = arr.find(x => String(x.id_cultivo) === String(id));
                        if (!item) return;

                        renderCultivoForm(listEl, {
                            recintoId: currentSideRecintoId,
                            cultivo: item,
                            usos,
                            productos,
                            mode: "historico_edit",
                            cultivoId: Number(id),
                            currentCultivoId,
                            onDone: reloadHistorico,
                            onCancel: reloadHistorico
                        });
                    });
                });

                // Ver modal Avanzado
                cardsEl.querySelectorAll(".btn-ver-avanzado").forEach(btn => {
                    btn.addEventListener("click", () => {
                        const id = btn.dataset.id;
                        const item = arr.find(x => String(x.id_cultivo) === String(id));
                        openAvanzadoModal(item?.avanzado || null);
                    });
                });
            }

            // Añadir al histórico
            listEl.querySelector("#btn-add-historico")?.addEventListener("click", () => {
                renderCultivoForm(listEl, {
                    recintoId: currentSideRecintoId,
                    cultivo: null,
                    usos,
                    productos,
                    mode: "historico_add",
                    onDone: reloadHistorico,
                    onCancel: reloadHistorico
                });
            });

            listEl.querySelector("#btn-download-cultivos-csv")?.addEventListener("click", () => {
                // if (!Array.isArray(arr) || arr.length === 0) return;
                const headers = [
                    "id_cultivo",
                    "fecha_inicio",
                    "fecha_fin",
                    "uso_sigpac_codigo",
                    "uso_sigpac_desc",
                    "tipo_cultivo_codigo",
                    "tipo_cultivo_desc",
                    "variedad",
                    "explotacion",
                    "campana_o_registro",
                    "estado",
                    "sistema_cultivo",
                    "avanzado_si_no",
                    "avanzado_json",
                    "observaciones"
                ];

                const rows = arr.map((c) => {
                    const isCamp = String(c.tipo_registro || "").toUpperCase().includes("CAMP");
                    const inicio = isCamp ? c.fecha_siembra : c.fecha_implantacion;
                    const fin = c.fecha_cosecha_real || c.fecha_cosecha_estimada;

                    const u = usosMap.get(String(c.uso_sigpac));
                    const usoDesc = u?.descripcion || "";

                    let tipoCod = "";
                    let tipoDesc = "";

                    const origen = String(c.origen_cultivo || "").toUpperCase();
                    if (origen === "F" && c.cod_producto != null) {
                        const p = prodMap.get(String(c.cod_producto));
                        tipoCod = String(c.cod_producto);
                        tipoDesc = p?.descripcion || (c.tipo_cultivo || "");
                    } else {
                        // custom u otros: NO ponemos origen en CSV, y dejamos código vacío
                        tipoCod = "";
                        tipoDesc = (c.cultivo_custom || c.tipo_cultivo || "");
                    }

                    const campOrReg = isCamp ? (c.campana ?? "") : tipoRegistroLabel(c.tipo_registro);

                    return [
                        c.id_cultivo ?? "",
                        formatDateOnly(inicio),
                        formatDateOnly(fin),
                        c.uso_sigpac ?? "",
                        usoDesc,
                        tipoCod,
                        tipoDesc,
                        c.variedad ?? "",
                        sistemaLabel(c.sistema_explotacion),
                        campOrReg ?? "",
                        estadoLabel(c.estado),
                        (c?._sistema_cultivo_label ? String(c._sistema_cultivo_label) : ""),
                        (hasAvanzado(c.avanzado) ? "Sí" : "No"),
                        (c.avanzado ? JSON.stringify(c.avanzado) : ""),
                        c.observaciones ?? ""
                    ];
                });

                const csv = rowsToCsv(headers, rows, ";");
                const file = `cultivos_historico_recinto_${currentSideRecintoId || "NA"}.csv`;
                downloadCsv(file, csv);
            });

        } catch (err) {
            console.warn(err);
            listEl.innerHTML = `<div class="text-danger">No se pudo cargar el histórico.</div>`;
        }
    };

    // Primer pintado al abrir
    await reloadHistorico();
});

function formatDateOnly(v) {
    if (!v) return "N/A";
    const s = String(v).trim();

    // ✅ Si viene como YYYY-MM-DD, lo devolvemos directamente sin Date()
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[3]}/${m[2]}/${m[1]}`;

    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return safeText(v);

    const dd = String(d.getDate()).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const yy = d.getFullYear();
    return `${dd}/${mm}/${yy}`;
}

function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s ?? "";
    return div.innerHTML;
}

function parseMaybeJson(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "object") return v;
    if (typeof v !== "string") return null;

    const s = v.trim();
    if (!s) return null;

    try { return JSON.parse(s); } catch (_) { return null; }
}

function normalizeCatalogObj(v) {
    if (v == null || v === "") return null;

    if (typeof v === "string") {
        const s = v.trim();
        if (!s) return null;

        if ((s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"))) {
            try {
                const parsed = JSON.parse(s);
                return normalizeCatalogObj(parsed);
            } catch (e) {
                // sigue como string normal
            }
        }

        return { codigo: s, label: s, fuente: "SIEX" };
    }

    if (typeof v === "object") {
        if (Array.isArray(v)) {
            if (!v.length) return null;
            return normalizeCatalogObj(v[0]);
        }
        const codigo = String(v.codigo ?? v.codigo_siex ?? v.code ?? v.id ?? "").trim();
        const label = String(v.label ?? v.nombre ?? v.descripcion ?? v.valor ?? codigo).trim();
        const fuente = String(v.fuente || "SIEX");

        if (!codigo && !label) return null;

        return { ...v, codigo: codigo || label, label: label || codigo, fuente };
    }

    return null;
}


function normalizeCultivoFromApi(c) {
    if (!c || typeof c !== "object") return c;

    // Copia superficial
    const out = { ...c };

    // Compat: algunos endpoints/versiones pueden devolver claves distintas
    if (out.sistema_cultivo == null) {
        out.sistema_cultivo =
            out.sistemaCultivo ??
            out.sistema_de_cultivo ??
            out.sistemaCultivoSIEX ??
            out.sistemaCultivoObj ??
            null;
    }

    if (out.avanzado == null) {
        out.avanzado =
            out.avanzado_cultivo ??
            out.cultivo_avanzado ??
            out.avanzadoCultivo ??
            out.avanzado_json ??
            null;
    }

    // sistema_cultivo puede venir como objeto o string
    out.sistema_cultivo = normalizeCatalogObj(out.sistema_cultivo);

    // Fallback: en histórico puede venir solo sistema_cultivo_codigo (texto) desde BBDD
    if (!out.sistema_cultivo && out.sistema_cultivo_codigo) {
        const cod = String(out.sistema_cultivo_codigo).trim();
        if (cod) out.sistema_cultivo = { codigo: cod, label: cod, fuente: "SIEX" };
    }

    // avanzado puede venir como objeto o string JSON
    out.avanzado = (typeof out.avanzado === "string") ? parseMaybeJson(out.avanzado) : out.avanzado;
    if (out.avanzado && typeof out.avanzado !== "object") out.avanzado = null;

    // Normaliza también los nested típicos del avanzado (por si vienen como strings)
    if (out.avanzado) {
        const a = out.avanzado;
        if (a.aprovechamiento) a.aprovechamiento = normalizeCatalogObj(a.aprovechamiento);
        if (a.tipo_cobertura_suelo) a.tipo_cobertura_suelo = normalizeCatalogObj(a.tipo_cobertura_suelo);
        if (a.destino_cultivo) a.destino_cultivo = normalizeCatalogObj(a.destino_cultivo);
        if (a.tipo_labor) a.tipo_labor = normalizeCatalogObj(a.tipo_labor);
        if (a.procedencia_material_vegetal) a.procedencia_material_vegetal = normalizeCatalogObj(a.procedencia_material_vegetal);
        if (a.senp) a.senp = normalizeCatalogObj(a.senp);

        if (a.material_vegetal && typeof a.material_vegetal === "object") {
            if (a.material_vegetal.tipo) a.material_vegetal.tipo = normalizeCatalogObj(a.material_vegetal.tipo);
            if (a.material_vegetal.detalle) a.material_vegetal.detalle = normalizeCatalogObj(a.material_vegetal.detalle);
        }
    }

    return out;
}

// Check robusto (para "Sí/No" y para normalizar a null)
function hasAvanzado(a) {
    a = (typeof a === "string") ? parseMaybeJson(a) : a;
    if (!a || typeof a !== "object") return false;

    const stack = [a];
    while (stack.length) {
        const x = stack.pop();
        if (!x) continue;

        if (typeof x === "string") {
            if (x.trim()) return true;
            continue;
        }
        if (typeof x === "number") {
            if (Number.isFinite(x)) return true;
            continue;
        }
        if (Array.isArray(x)) {
            for (const it of x) stack.push(it);
            continue;
        }
        if (typeof x === "object") {
            for (const [k, v] of Object.entries(x)) {
                if (v === null || v === undefined) continue;
                if (k === "fuente") continue; // no cuenta como "relleno"
                stack.push(v);
            }
        }
    }
    return false;
}


function csvEscape(value, delimiter = ";") {
    if (value === null || value === undefined) return "";
    let s = String(value);

    // normaliza saltos de línea
    s = s.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

    // si contiene comillas, delimitador o salto de línea => entrecomillar
    const mustQuote = s.includes('"') || s.includes("\n") || s.includes(delimiter);
    if (s.includes('"')) s = s.replace(/"/g, '""');
    return mustQuote ? `"${s}"` : s;
}

function rowsToCsv(headers, rows, delimiter = ";") {
    const head = headers.map(h => csvEscape(h, delimiter)).join(delimiter);
    const body = rows.map(r => r.map(v => csvEscape(v, delimiter)).join(delimiter)).join("\n");
    return head + "\n" + body;
}

function downloadCsv(filename, csvText) {
    const blob = new Blob(["\ufeff", csvText], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();

    setTimeout(() => URL.revokeObjectURL(url), 2000);
}


function cultivoTipoLabel(c) {
    const code = (c.cod_producto == null) ? "N/A" : String(c.cod_producto);
    const name = safeText(c.tipo_cultivo || c.cultivo_custom, "N/A");
    return `${code}-${name}`;
}

function cultivoUsoLabel(c, usosMap) {
    const u = usosMap.get(String(c.uso_sigpac));
    return formatCodigoDesc(c.uso_sigpac, u?.descripcion || c.uso_sigpac);
}

function sistemaLabel(val) {
    const v = String(val || "").toUpperCase();
    if (v === "R") return "Regadío";
    if (v === "S") return "Secano";
    return "N/A";
}

function tipoRegistroLabel(val) {
    const v = String(val || "").toUpperCase();
    if (v.includes("IMPL")) return "Plantación";
    if (v.includes("CAMP")) return "Campaña";
    return safeText(val, "N/A");
}

function renderCultivoView(container, recintoId, cultivo, usos, productos) {
    const usosMap = byCodigo(usos);
    const tipoReg = tipoRegistroLabel(cultivo.tipo_registro);
    console.log("Render view cultivo:", cultivo);
    const sisCultLbl = cultivo?._sistema_cultivo_label ? String(cultivo._sistema_cultivo_label).trim() : "";
    const isCamp = String(cultivo.tipo_registro || "").toUpperCase().includes("CAMP");

    const inicio = isCamp ? cultivo.fecha_siembra : cultivo.fecha_implantacion;
    const fin = cultivo.fecha_cosecha_real || cultivo.fecha_cosecha_estimada;

    const variedad = cultivo.variedad ? safeText(cultivo.variedad) : "N/A";
    const obs = cultivo.observaciones || "";

    container.innerHTML = `
    <div class="cultivo-grid">
    <div class="cultivo-field">
        <div class="k">Uso SIGPAC</div>
        <div class="v">${safeText(cultivoUsoLabel(cultivo, usosMap))}</div>
    </div>
    <div class="cultivo-field">
        <div class="k">Tipo cultivo</div>
        <div class="v">${safeText(cultivoTipoLabel(cultivo))}</div>
    </div>

    <div class="cultivo-field">
        <div class="k">Variedad</div>
        <div class="v">${safeText(variedad)}</div>
    </div>
    <div class="cultivo-field">
        <div class="k">Explotación</div>
        <div class="v">${safeText(sistemaLabel(cultivo.sistema_explotacion))}</div>
    </div>

    <div class="cultivo-field">
        <div class="k">Sistema de cultivo</div>
        <div class="v">${sisCultLbl ? escapeHtml(sisCultLbl) : "<span class='text-muted'>—</span>"}</div>
    </div>

    <div class="cultivo-field">
        <div class="k">${isCamp ? "Campaña" : "Tipo registro"}</div>
        <div class="v">${isCamp ? safeText(cultivo.campana, "N/A") : safeText(tipoReg)}</div>
    </div>
    <div class="cultivo-field">
        <div class="k">Estado</div>
        <div class="v">${estadoLabel(cultivo.estado)}</div>
    </div>

    <div class="cultivo-field">
        <div class="k">Fecha inicio</div>
        <div class="v">${safeText(formatDateOnly(inicio))}</div>
    </div>
    <div class="cultivo-field">
        <div class="k">Fecha fin</div>
        <div class="v">${safeText(formatDateOnly(fin))}</div>
    </div>
    </div>

    ${hasAvanzado(cultivo.avanzado) ? `
    <div class="side-soft-divider"></div>
    <div class="mt-3">
        <div class="d-flex justify-content-between align-items-center mb-1">
        <div class="fw-bold">Avanzado</div>
        <button type="button" class="btn btn-outline-success btn-sm" id="btn-ver-avanzado-main">Ver</button>
        </div>
    </div>
    ` : ``}

    <div class="side-soft-divider"></div>
    <div class="mt-3">
    <div class="fw-bold mb-1">Observaciones</div>

    <!-- Texto normal (no editable) -->
    <div id="obs-view" class="border rounded-3 p-2" style="min-height:90px; white-space:pre-wrap;"></div>

    <!-- Textarea sólo cuando el usuario pulsa “Editar observaciones” -->
    <textarea id="obs-edit" class="form-control d-none" rows="3" placeholder="(Opcional)"></textarea>

    <div class="cultivo-actions mt-2" id="obs-view-actions">
        <button id="btn-edit-obs" class="btn btn-outline-success btn-sm" type="button">
        Editar observaciones
        </button>
        <button id="btn-edit-cultivo" class="btn btn-outline-success btn-sm" type="button">
        Editar cultivo
        </button>
        <button id="btn-del-cultivo" class="btn btn-outline-danger btn-sm" type="button">
        Eliminar cultivo
        </button>
    </div>

        <div class="cultivo-actions mt-2 d-none" id="obs-edit-actions">
            <button id="btn-obs-accept" class="btn btn-success btn-sm" type="button">Aceptar</button>
            <button id="btn-obs-cancel" class="btn btn-secondary btn-sm" type="button">Cancelar</button>
        </div>
        </div>
`;

    // --- Observaciones: render “texto normal” ---
    const obsView = container.querySelector("#obs-view");
    const obsEdit = container.querySelector("#obs-edit");
    const viewActions = container.querySelector("#obs-view-actions");
    const editActions = container.querySelector("#obs-edit-actions");

    // Ver avanzado (si existe)
    const btnVerAv = container.querySelector("#btn-ver-avanzado-main");
    if (btnVerAv) {
        btnVerAv.addEventListener("click", () => openAvanzadoModal(cultivo.avanzado));
    }

    function renderObsText(text) {
        const t = String(text || "");
        if (!t.trim()) {
            obsView.innerHTML = `<span class="text-muted">(Sin observaciones)</span>`;
        } else {
            obsView.textContent = t;
        }
    }

    renderObsText(obs);
    obsEdit.value = obs;

    let obsOriginal = obsEdit.value;

    container.querySelector("#btn-edit-obs").addEventListener("click", () => {
        obsOriginal = obsEdit.value;

        obsView.classList.add("d-none");
        obsEdit.classList.remove("d-none");

        viewActions.classList.add("d-none");
        editActions.classList.remove("d-none");

        obsEdit.focus();
    });

    container.querySelector("#btn-obs-cancel").addEventListener("click", () => {
        obsEdit.value = obsOriginal;

        obsEdit.classList.add("d-none");
        obsView.classList.remove("d-none");

        editActions.classList.add("d-none");
        viewActions.classList.remove("d-none");
    });

    container.querySelector("#btn-obs-accept").addEventListener("click", async () => {
        try {
            const val = obsEdit.value;

            await fetchJson(`/api/cultivos/${cultivo.id_cultivo}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ observaciones: val }),
            });

            cultivo.observaciones = val;
            obsOriginal = val;

            renderObsText(val);

            obsEdit.classList.add("d-none");
            obsView.classList.remove("d-none");

            editActions.classList.add("d-none");
            viewActions.classList.remove("d-none");

            NotificationSystem.show({
                type: "success",
                title: "Observaciones guardadas",
                message: ""
            });
        } catch (e) {
            console.warn(e);
            NotificationSystem.show({
                type: "error",
                title: "Error",
                message: "No se pudieron guardar las observaciones"
            });
        }
    });

    // Editar cultivo
    container.querySelector("#btn-edit-cultivo").addEventListener("click", async () => {
        try {
            const cultivoFresh = await getCultivoRecinto(recintoId);
            renderCultivoForm(container, { recintoId: cultivoFresh.id_recinto || recintoId, cultivo: cultivoFresh, usos, productos });
        } catch (e) {
            console.warn("No se pudo refrescar cultivo antes de editar, uso el objeto en memoria.", e);
            renderCultivoForm(container, { recintoId: cultivo.id_recinto || recintoId, cultivo, usos, productos });
        }
    });

    // Eliminar cultivo
    container.querySelector("#btn-del-cultivo").addEventListener("click", () => {
        abrirConfirmacionEliminarCultivo(recintoId);
    });
}

async function abrirConfirmacionEliminarCultivo(recintoId) {
    const ok = await AppConfirm.open({
        title: "Eliminar cultivo",
        message: "¿Seguro que deseas eliminar el cultivo actual? Este proceso no es reversible y también se eliminará su entrada correspondiente en el histórico.",
        okText: "Eliminar",
        cancelText: "Cancelar",
        okClass: "btn-danger"
    });

    if (!ok) return;

    try {
        await fetchJson(`/api/mis-recinto/${recintoId}/cultivo`, { method: "DELETE" });
        NotificationSystem.show({
            type: "success",
            title: "Cultivo eliminado",
            message: ""
        });
        renderCultivosForRecinto(recintoId);
    } catch (e) {
        console.warn(e);
        NotificationSystem.show({
            type: "error",
            title: "Error",
            message: "No se pudo eliminar el cultivo"
        });
    }
}

function openSs(ssEl) { ssEl.classList.add("open"); }
function closeSs(ssEl) { ssEl.classList.remove("open"); }

function attachSearchSelect(ssEl, items, opts) {
    const input = ssEl.querySelector("input");
    const menu = ssEl.querySelector(".ss-menu");
    const hidden = ssEl.querySelector("input[type=hidden]");
    const {
        getLabel,
        getValue,
        onSelect,
        allowFreeText = false,
        emptyText = "Sin resultados",
        signal,
    } = opts;

    function renderList(list) {
        menu.innerHTML = "";
        if (!list.length) {
            const d = document.createElement("div");
            d.className = "ss-item text-muted";
            d.textContent = emptyText;
            menu.appendChild(d);
            return;
        }
        for (const it of list) {
            const d = document.createElement("div");
            d.className = "ss-item";
            d.textContent = getLabel(it);
            d.addEventListener("mousedown", (ev) => {
                ev.preventDefault();
                const val = getValue(it);
                hidden.value = (val === null || val === undefined) ? "" : String(val);
                input.value = getLabel(it);
                closeSs(ssEl);
                onSelect?.(it);
            }, { signal });
            menu.appendChild(d);
        }
    }

    function filterNow() {
        const q = norm(input.value);
        const list = items.filter(it => {
            const label = norm(getLabel(it));
            const val = norm(getValue(it));
            return !q || label.includes(q) || val.includes(q);
        });
        renderList(list.slice(0, 200));
    }

    input.addEventListener("focus", () => { openSs(ssEl); filterNow(); }, { signal });
    input.addEventListener("input", () => { openSs(ssEl); filterNow(); }, { signal });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeSs(ssEl);
        if (allowFreeText && e.key === "Enter") closeSs(ssEl);
    }, { signal });

    document.addEventListener("click", (e) => {
        if (!ssEl.contains(e.target)) closeSs(ssEl);
    }, { signal });

    renderList(items.slice(0, 50));
    return {
        setItems(newItems) { items = newItems; filterNow(); },
        getSelectedValue() { return hidden.value || null; }
    };
}


function renderCultivoForm(container, args) {
    if (container.__cultivoFormAbort) container.__cultivoFormAbort.abort();
    const abort = new AbortController();
    container.__cultivoFormAbort = abort;
    const { signal } = abort;

    const { recintoId, cultivo, usos, productos, mode = "actual", cultivoId = null, currentCultivoId = null, onDone = null, onCancel = null } = args;

    const usosMap = byCodigo(usos);
    const productosAll = productos || [];

    const estadoOpts = [
        { v: "planificado", l: "Planificado" },
        { v: "implantado", l: "Plantado" },
        { v: "en_curso", l: "En cultivo" },
        { v: "cosechado", l: "Cosechado" },
        { v: "abandonado", l: "Abandonado" }
    ];

    const tipoRegOpts = [
        { v: "CAMPANA", l: "Campaña (año a año)" },
        { v: "IMPLANTACION", l: "Plantación (permanente)" },
    ];

    container.innerHTML = `
    <div class="card" style="border-radius:16px">
    <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
        <div class="fw-bold">${cultivo ? "Editar cultivo" : "Añadir cultivo"}</div>
        <button id="btn-cancel-cultivo" type="button" class="btn btn-sm btn-outline-secondary">Cancelar</button>
        </div>

        <div class="mb-3 ss" id="ss-uso">
        <label class="form-label fw-bold">Uso SIGPAC *</label>
        <input class="form-control" type="text" placeholder="Busca: CI-Cítricos, OV-Olivar, TA-Tierras arables..." autocomplete="off">
        <input type="hidden" id="uso_sigpac_val">
        <div class="ss-menu"></div>
        </div>

        <div class="d-flex justify-content-between align-items-center mb-1">
        <label class="form-label fw-bold mb-0">Tipo de cultivo *</label>
        <button id="btn-ver-todos" type="button" class="btn btn-sm btn-outline-success" disabled>Ver todos</button>
        </div>

        <div class="mb-3 ss" id="ss-prod">
        <input class="form-control" type="text" placeholder="Busca por código o nombre: 99-PATATA, N/A-ALTRAMUZ..." autocomplete="off" disabled>
        <input type="hidden" id="cod_producto_val">
        <div class="ss-menu"></div>
        <div class="form-text" id="prod-help">Selecciona primero el uso SIGPAC.</div>
        </div>

        <div class="mb-3" id="custom-wrap" style="display:none">
        <label class="form-label fw-bold">Cultivo personalizado</label>
        <input id="cultivo_custom" class="form-control" type="text" placeholder="Escribe el cultivo (p.ej. ALTRAMUZ)">
        </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Sistema de cultivo *</label>
        <select id="cultivo-sistema" class="form-select" required></select>
        <div class="form-text">Catálogo SIEX: SISTEMA_CULTIVO</div>
        </div>

        <div class="mb-3 position-relative">
        <label class="form-label fw-bold">Variedad (opcional)</label>
        <input id="variedad" class="form-control" type="text" 
            placeholder="Empieza a escribir: Picual, Arbequina..." 
            autocomplete="off">
        <div id="variedad-suggestions" class="list-group position-absolute w-100" style="z-index:1000; max-height:200px; overflow-y:auto; display:none;"></div>
        <div class="form-text">Selecciona una variedad de la lista o escribe una nueva.</div>
    </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Estado</label>
        <select id="estado" class="form-select">
            ${estadoOpts.map(o => `<option value="${o.v}">${o.l}</option>`).join("")}
        </select>
        </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Explotación</label>
        <div class="d-flex gap-3">
            <div class="form-check">
            <input class="form-check-input" type="radio" name="sistema_explotacion" id="exp-sec" value="S" checked>
            <label class="form-check-label" for="exp-sec">Secano</label>
            </div>
            <div class="form-check">
            <input class="form-check-input" type="radio" name="sistema_explotacion" id="exp-reg" value="R">
            <label class="form-check-label" for="exp-reg">Regadío</label>
            </div>
        </div>
        </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Tipo de registro</label>
        <select id="tipo_registro" class="form-select">
            ${tipoRegOpts.map(o => `<option value="${o.v}">${o.l}</option>`).join("")}
        </select>
        </div>

        <div class="mb-3" id="campana-wrap" style="display:none">
        <label class="form-label fw-bold">Campaña</label>
        <input id="campana" class="form-control" type="number" min="1900" max="2200" placeholder="2026">
        </div>

        <div class="mb-3" id="fecha-inicio-wrap">
        <label class="form-label fw-bold" id="lbl-fecha-inicio">Fecha siembra</label>
        <input id="fecha_inicio" class="form-control" type="date">
        </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Fecha fin (opcional)</label>
        <input id="fecha_fin" class="form-control" type="date">
        <div class="form-text">Si no indicas fecha fin, se estimará automáticamente.</div>
        </div>

        <div class="mb-3">
        <label class="form-label fw-bold">Observaciones (opcional)</label>
        <textarea id="observaciones" class="form-control" rows="3" placeholder="Escribe notas..."></textarea>
        </div>

        <div class="accordion mt-2" id="cultivo-adv-acc">
        <div class="accordion-item">
            <h2 class="accordion-header" id="cultivo-adv-h">
            <button class="accordion-button collapsed" type="button"
                    data-bs-toggle="collapse" data-bs-target="#cultivo-adv-c">
                Avanzado (opcional)
            </button>
            </h2>

            <div id="cultivo-adv-c" class="accordion-collapse collapse" data-bs-parent="#cultivo-adv-acc">
            <div class="accordion-body">
                <div class="row g-2">

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Aprovechamiento</label>
                    <select id="adv-aprovechamiento" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: APROVECHAMIENTO</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Tipo cobertura del suelo</label>
                    <select id="adv-tipo-cobertura" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: TIPO_COBERTURA_SUELO</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Destino del cultivo</label>
                    <select id="adv-destino" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: DESTINO_CULTIVO</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Material vegetal (tipo)</label>
                    <select id="adv-mvr-tipo" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: MVR_TIPO</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Material vegetal (detalle)</label>
                    <select id="adv-mvr-detalle" class="form-select" disabled></select>
                    <div class="form-text">Catálogo SIEX: MVR_DETALLE (depende de tipo)</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Tipo de labor</label>
                    <select id="adv-tipo-labor" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: TIPO_LABOR</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">Procedencia material vegetal</label>
                    <select id="adv-proc-mv" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: PROCEDENCIA_MATERIAL_VEGETAL</div>
                </div>

                <div class="col-12 col-md-4">
                    <label class="form-label fw-bold">SENP</label>
                    <select id="adv-senp" class="form-select"></select>
                    <div class="form-text">Catálogo SIEX: SENP</div>
                </div>

                </div>
            </div>
            </div>
        </div>
        </div>

        <button id="btn-save-cultivo" type="button" class="btn btn-success w-100">Guardar</button>
        <div id="cultivo-form-msg" class="text-muted" style="font-size:12px; margin-top:8px"></div>
    </div>
    </div>
`;

    // Autocompletado de variedad
    const variedadInput = container.querySelector("#variedad");
    const suggestionsList = container.querySelector("#variedad-suggestions");
    let timeoutVariedad = null;

    variedadInput.addEventListener("input", async (e) => {
        const query = e.target.value.trim();

        // Limpiar timeout anterior
        if (timeoutVariedad) {
            clearTimeout(timeoutVariedad);
        }

        // Si está vacío, ocultar sugerencias
        if (query.length < 1) {
            suggestionsList.style.display = "none";
            suggestionsList.innerHTML = "";
            return;
        }

        // Esperar 200ms después de que el usuario deje de escribir
        timeoutVariedad = setTimeout(async () => {
            try {
                // Obtener el producto seleccionado (opcional, para filtrar)
                const productoId = container.querySelector("#cod_producto_val")?.value || "";

                // Construir URL con parámetros - CON /api
                let url = `/api/variedades/buscar?q=${encodeURIComponent(query)}`;
                if (productoId && productoId !== "") {
                    url += `&producto_id=${productoId}`;
                }

                const response = await fetch(url);
                const variedades = await response.json();

                // Mostrar sugerencias SOLO si hay resultados
                if (variedades.length > 0) {
                    suggestionsList.innerHTML = variedades.map(v => `
            <button type="button" class="list-group-item list-group-item-action" data-nombre="${v.nombre}">
            ${v.nombre}
            </button>
        `).join("");
                    suggestionsList.style.display = "block";
                } else {
                    // Si no hay resultados, simplemente ocultar las sugerencias
                    // El usuario puede seguir escribiendo lo que quiera
                    suggestionsList.style.display = "none";
                    suggestionsList.innerHTML = "";
                }
            } catch (error) {
                console.error("Error buscando variedades:", error);
                suggestionsList.style.display = "none";
                suggestionsList.innerHTML = "";
            }
        }, 200); // Debounce de 200ms
    }, { signal });

    // Click en una sugerencia
    suggestionsList.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (btn) {
            const nombre = btn.getAttribute("data-nombre");
            variedadInput.value = nombre;
            suggestionsList.style.display = "none";
            suggestionsList.innerHTML = "";
        }
    }, { signal });

    // Cerrar sugerencias al hacer click fuera
    document.addEventListener("click", (e) => {
        if (!variedadInput.contains(e.target) && !suggestionsList.contains(e.target)) {
            suggestionsList.style.display = "none";
        }
    }, { signal });

    variedadInput.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            suggestionsList.classList.add("d-none");
            return;
        }
        if (e.key === "Enter") {
            const first = suggestionsList.querySelector("li[data-value]");
            if (first) {
                variedadInput.value = first.dataset.value || "";
                suggestionsList.classList.add("d-none");
                suggestionsList.innerHTML = "";
                e.preventDefault();
            }
        }
    }, { signal });

    // Elementos SS
    const ssUsoEl = container.querySelector("#ss-uso");
    const ssProdEl = container.querySelector("#ss-prod");
    const btnVerTodos = container.querySelector("#btn-ver-todos");

    // --- SISTEMA_CULTIVO (obligatorio) ---
    const sisCultSel = container.querySelector("#cultivo-sistema");

    const sisCultSelected =
        (cultivo?.sistema_cultivo && typeof cultivo.sistema_cultivo === "object")
            ? (cultivo.sistema_cultivo.codigo || "")
            : (cultivo?.sistema_cultivo || "");

    fillSelectFromCatalog(
        container.querySelector("#cultivo-sistema"),
        "SISTEMA_CULTIVO",
        {
            selected: (cultivo?.sistema_cultivo?.codigo || cultivo?.sistema_cultivo || ""),
            placeholder: "Selecciona..."
        }
    );

    const usoItems = usos.map(u => ({
        codigo: u.codigo,
        descripcion: u.descripcion,
        grupo: u.grupo,
        label: formatCodigoDesc(u.codigo, u.descripcion),
    }));

    let modoVerTodos = false;
    let selectedUso = null;
    let selectedProd = null;
    let productosUso = [];

    const ssUso = attachSearchSelect(ssUsoEl, usoItems, {
        getLabel: (it) => it.label,
        getValue: (it) => it.codigo,
        onSelect: async (it) => {
            selectedUso = it;

            ssProdEl.querySelector("input").disabled = false;
            ssProdEl.querySelector("#prod-help").style.display = "none";
            btnVerTodos.disabled = false;

            modoVerTodos = false;
            btnVerTodos.textContent = "Ver todos";

            try {
                productosUso = await loadProductosFegaPorUso(it.codigo);
            } catch (_) {
                productosUso = [];
            }

            actualizarListaProductos();
        },
        signal
    });

    function buildProductosList() {
        const base = productosAll.map(p => ({
            codigo: p.codigo,
            descripcion: p.descripcion,
            origen: "F",
            label: formatCodigoDesc(p.codigo, p.descripcion),
        }));
        const custom = _cultivosCustom.map(p => ({
            codigo: null,
            descripcion: p.descripcion,
            origen: "C",
            label: formatCodigoDesc(null, p.descripcion),
        }));
        const otro = [{
            codigo: "__OTRO__",
            descripcion: "OTRO (escribir…)",
            origen: "C",
            label: "N/A-OTRO (escribir…)"
        }];

        return [...base, ...custom, ...otro];
    }

    let productosItems = buildProductosList();
    let ssProd = attachSearchSelect(ssProdEl, [], {
        getLabel: (it) => it.label,
        getValue: (it) => (it.codigo === null ? "" : it.codigo),
        onSelect: (it) => {
            selectedProd = it;
            const customWrap = container.querySelector("#custom-wrap");
            const customInput = container.querySelector("#cultivo_custom");
            const codHidden = container.querySelector("#cod_producto_val");

            if (it.codigo === "__OTRO__") {
                customWrap.style.display = "";
                codHidden.value = ""; // null
                customInput.focus();
            } else if (it.origen === "C") {
                customWrap.style.display = "";
                codHidden.value = ""; // null
                customInput.value = it.descripcion;
            } else {
                customWrap.style.display = "none";
                codHidden.value = String(it.codigo);
                customInput.value = "";
            }
        },
        signal
    });

    function actualizarListaProductos() {
        const baseList = (modoVerTodos || !productosUso.length) ? productosAll : productosUso;

        const fega = (baseList || []).map(p => ({
            codigo: p.codigo,
            descripcion: p.descripcion,
            origen: "F",
            label: formatCodigoDesc(p.codigo, p.descripcion),
        }));

        const custom = _cultivosCustom.map(p => ({
            codigo: null,
            descripcion: p.descripcion,
            origen: "C",
            label: formatCodigoDesc(null, p.descripcion),
        }));

        const otro = [{
            codigo: "__OTRO__",
            descripcion: "OTRO (escribir…)",
            origen: "C",
            label: "N/A-OTRO (escribir…)"
        }];

        productosItems = [...fega, ...custom, ...otro];
        ssProd.setItems(productosItems);

        const help = container.querySelector("#prod-help");
        if (!modoVerTodos && !productosUso.length) {
            help.style.display = "";
            help.textContent = "No hay productos asociados a este uso (según histórico). Pulsa “Ver todos”.";
        } else {
            help.style.display = "none";
        }
    }

    btnVerTodos.addEventListener("click", () => {
        modoVerTodos = !modoVerTodos;
        btnVerTodos.textContent = modoVerTodos ? "Filtrar" : "Ver todos";
        actualizarListaProductos();
    }, { signal });

    // Tipo registro: muestra campaña o cambia etiqueta de fecha
    const tipoRegSel = container.querySelector("#tipo_registro");
    const campWrap = container.querySelector("#campana-wrap");
    const lblInicio = container.querySelector("#lbl-fecha-inicio");

    function syncTipoRegistroUi() {
        const v = tipoRegSel.value;
        const isCamp = v === "CAMPANA";
        campWrap.style.display = isCamp ? "" : "none";
        lblInicio.textContent = isCamp ? "Fecha siembra" : "Fecha plantación";
    }
    tipoRegSel.addEventListener("change", syncTipoRegistroUi, { signal });
    syncTipoRegistroUi();

    // -------- Avanzado (opcional) --------
    function pickObjFromSelect(sel) {
        if (!sel) return null;

        // 1) valor normal del select
        let code = (sel.value || "").trim();

        // 2) si el select está vacío pero el catálogo usa hidden input, lo buscamos
        if (!code) {
            const hiddenId = sel.getAttribute("data-hidden-code-id") || sel.dataset.hiddenCodeId;
            if (hiddenId) {
                const hiddenEl = document.getElementById(hiddenId);
                if (hiddenEl?.value) code = hiddenEl.value.trim();
            }
        }

        if (!code) return null;
        const label = (sel.selectedOptions?.[0]?.textContent || "").trim() || code;
        return { codigo: code, label, fuente: "SIEX" };
    }


    // Lee avanzado existente
    let adv = cultivo?.avanzado ?? null;
    if (typeof adv === "string") { try { adv = JSON.parse(adv); } catch (_) { adv = null; } }
    adv = (adv && typeof adv === "object") ? adv : null;

    const advAprove = container.querySelector("#adv-aprovechamiento");
    const advCob = container.querySelector("#adv-tipo-cobertura");
    const advDest = container.querySelector("#adv-destino");
    const advMvrTipo = container.querySelector("#adv-mvr-tipo");
    const advMvrDet = container.querySelector("#adv-mvr-detalle");
    const advTipoLabor = container.querySelector("#adv-tipo-labor");
    const advProcMv = container.querySelector("#adv-proc-mv");
    const advSenp = container.querySelector("#adv-senp");

    // selected codes
    const advAproveSel = adv?.aprovechamiento?.codigo || "";
    const advCobSel = adv?.tipo_cobertura_suelo?.codigo || "";
    const advDestSel = adv?.destino_cultivo?.codigo || "";

    const advMvrTipoSel = adv?.material_vegetal?.tipo?.codigo || "";
    const advMvrDetSel = adv?.material_vegetal?.detalle?.codigo || "";

    const advTipoLaborSel = adv?.tipo_labor?.codigo || "";
    const advProcMvSel = adv?.procedencia_material_vegetal?.codigo || "";
    const advSenpSel = adv?.senp?.codigo || "";

    // cargar selects simples
    fillSelectFromCatalog(advAprove, "APROVECHAMIENTO", { selected: advAproveSel, placeholder: "(Opcional)" });
    fillSelectFromCatalog(advCob, "TIPO_COBERTURA_SUELO", { selected: advCobSel, placeholder: "(Opcional)" });
    fillSelectFromCatalog(advDest, "DESTINO_CULTIVO", { selected: advDestSel, placeholder: "(Opcional)" });

    fillSelectFromCatalog(advMvrTipo, "MVR_TIPO", { selected: advMvrTipoSel, placeholder: "(Opcional)" });
    fillSelectFromCatalog(advTipoLabor, "TIPO_LABOR", { selected: advTipoLaborSel, placeholder: "(Opcional)" });
    fillSelectFromCatalog(advProcMv, "PROCEDENCIA_MATERIAL_VEGETAL", { selected: advProcMvSel, placeholder: "(Opcional)" });
    fillSelectFromCatalog(advSenp, "SENP", { selected: advSenpSel, placeholder: "(Opcional)" });

    function reloadMvrDetalle({ selected = "" } = {}) {
        const tipo = (advMvrTipo?.value || "").trim();
        if (!tipo) {
            advMvrDet.disabled = true;
            advMvrDet.innerHTML = `<option value="">(Selecciona tipo primero)</option>`;
            return;
        }
        advMvrDet.disabled = false;
        fillSelectFromCatalog(advMvrDet, "MVR_DETALLE", {
            selected,
            placeholder: "(Opcional)",
            parent: tipo
        });
    }

    // inicial detalle (si ya venía algo)
    setTimeout(() => reloadMvrDetalle({ selected: advMvrDetSel }), 0);

    advMvrTipo.addEventListener("change", () => {
        // al cambiar tipo, resetea detalle y recarga por parent
        reloadMvrDetalle({ selected: "" });
    }, { signal });

    // Si venimos de editar
    if (cultivo) {
        // Uso sigpac
        const u = usosMap.get(String(cultivo.uso_sigpac));
        if (cultivo.uso_sigpac) {
            ssUsoEl.querySelector("input").value = formatCodigoDesc(cultivo.uso_sigpac, u?.descripcion || cultivo.uso_sigpac);
            ssUsoEl.querySelector("#uso_sigpac_val").value = cultivo.uso_sigpac;
            selectedUso = { codigo: cultivo.uso_sigpac, grupo: u?.grupo };
            ssProdEl.querySelector("input").disabled = false;
            btnVerTodos.disabled = false;
            actualizarListaProductos();
        }

        // Tipo cultivo
        const customWrap = container.querySelector("#custom-wrap");
        const customInput = container.querySelector("#cultivo_custom");
        const codHidden = container.querySelector("#cod_producto_val");
        const isFega = (cultivo.origen_cultivo || "").toUpperCase() === "F";

        if (isFega && cultivo.cod_producto != null) {
            const p = productosAll.find(x => String(x.codigo) === String(cultivo.cod_producto));
            ssProdEl.querySelector("input").value = formatCodigoDesc(cultivo.cod_producto, p?.descripcion || cultivo.tipo_cultivo);
            codHidden.value = String(cultivo.cod_producto);
            customWrap.style.display = "none";
        } else {
            ssProdEl.querySelector("input").value = formatCodigoDesc(null, cultivo.cultivo_custom || cultivo.tipo_cultivo);
            codHidden.value = "";
            customWrap.style.display = "";
            customInput.value = cultivo.cultivo_custom || cultivo.tipo_cultivo || "";
        }

        // resto campos
        container.querySelector("#variedad").value = cultivo.variedad || "";
        container.querySelector("#estado").value = cultivo.estado || "en_curso";

        const exp = (cultivo.sistema_explotacion || "S").toUpperCase();
        container.querySelector("#exp-sec").checked = (exp === "S");
        container.querySelector("#exp-reg").checked = (exp === "R");

        const tr = String(cultivo.tipo_registro || "CAMPANA").toUpperCase().includes("IMPL") ? "IMPLANTACION" : "CAMPANA";
        tipoRegSel.value = tr;
        syncTipoRegistroUi();

        container.querySelector("#campana").value = cultivo.campana || "";
        const inicio = (tr === "CAMPANA") ? cultivo.fecha_siembra : cultivo.fecha_implantacion;
        container.querySelector("#fecha_inicio").value = inicio ? String(inicio).slice(0, 10) : "";
        const fin = cultivo.fecha_cosecha_real || cultivo.fecha_cosecha_estimada;
        container.querySelector("#fecha_fin").value = fin ? String(fin).slice(0, 10) : "";

        container.querySelector("#observaciones").value = cultivo.observaciones || "";
    } else {
        // defaults
        container.querySelector("#estado").value = "planificado";
    }

    container.querySelector("#btn-cancel-cultivo").addEventListener("click", () => {
        if (mode === "historico_add" || mode === "historico_edit") {
            if (mode === "historico_edit" && currentCultivoId && String(cultivoId) === String(currentCultivoId)) {
                // Si acabo de editar el actual desde el histórico, repintar la vista principal YA
                renderCultivosForRecinto(recintoId);
            }
            if (typeof onDone === "function") onDone();
        } else {
            renderCultivosForRecinto(recintoId);
        }
    }, { signal });

    container.querySelector("#btn-save-cultivo").addEventListener("click", async () => {
        const msg = container.querySelector("#cultivo-form-msg");
        msg.textContent = "";

        const uso = container.querySelector("#uso_sigpac_val").value;
        if (!uso) {
            msg.textContent = "Selecciona un uso SIGPAC.";
            msg.className = "text-danger";
            return;
        }

        const cod = container.querySelector("#cod_producto_val").value;
        const custom = (container.querySelector("#cultivo_custom")?.value || "").trim();

        let origen = "F";
        let cod_producto = null;
        let cultivo_custom = null;

        if (cod) {
            origen = "F";
            cod_producto = Number(cod);
        } else {
            origen = "C";
            cultivo_custom = custom || (selectedProd?.descripcion || "");
        }

        if (origen === "C" && !cultivo_custom) {
            msg.textContent = "Indica el cultivo personalizado (o elige uno de la lista).";
            msg.className = "text-danger";
            return;
        }

        // --- Validación SISTEMA_CULTIVO ---
        const sisCultSel = container.querySelector("#cultivo-sistema");
        const sisCultCode = (sisCultSel?.value || "").trim();

        if (!sisCultCode) {
            msg.textContent = "Selecciona el sistema de cultivo.";
            msg.className = "text-danger";
            return;
        }

        const sistema_cultivo = {
            codigo: sisCultCode,
            label: (sisCultSel?.selectedOptions?.[0]?.textContent || "").trim() || sisCultCode,
            fuente: "SIEX"
        };


        const variedad = (container.querySelector("#variedad")?.value || "").trim() || null;
        const estado = container.querySelector("#estado")?.value || "en_curso";
        const sistema = container.querySelector("input[name='sistema_explotacion']:checked")?.value || "S";

        const tipo_registro = container.querySelector("#tipo_registro")?.value || "CAMPANA";
        const campana = (tipo_registro === "CAMPANA")
            ? (Number(container.querySelector("#campana")?.value) || null)
            : null;

        const fechaInicioRaw = container.querySelector("#fecha_inicio")?.value || null;
        const fechaFinRaw = container.querySelector("#fecha_fin")?.value || null;

        const fechaInicio = parseDateToISO(fechaInicioRaw);
        const fechaFin = parseDateToISO(fechaFinRaw);

        if (fechaFin && fechaInicio && fechaFin < fechaInicio) {
            msg.textContent = "La fecha fin no puede ser anterior a la de inicio.";
            msg.className = "text-danger";
            return;
        }

        if (!fechaInicio) {
            msg.textContent = "Selecciona la fecha de inicio.";
            msg.className = "text-danger";
            return;
        }

        // --- Validación campaña vs fecha (error custom) ---
        if (tipo_registro === "CAMPANA") {
            if (!campana) {
                msg.textContent = "Selecciona un año de campaña.";
                msg.className = "text-danger";
                return;
            }

            // fechaInicio viene ISO: YYYY-MM-DD
            const yFecha = Number(String(fechaInicio).slice(0, 4));
            if (Number.isFinite(yFecha) && Math.abs(yFecha - campana) >= 2) {
                msg.textContent =
                    `Año inválido: la fecha de siembra (${yFecha}) no cuadra con la campaña (${campana}). ` +
                    `Debe ser el mismo año o como mucho ±1 año.`;
                msg.className = "text-danger";
                return;
            }
        }

        // Si no hay fecha fin: estimación simple
        let fechaCosechaEst = fechaFin;
        let cosechaAuto = false;

        if (!fechaFin) {
            cosechaAuto = true;
            const d = new Date(fechaInicio);
            const deltaDays = (tipo_registro === "CAMPANA") ? 120 : 365;
            d.setDate(d.getDate() + deltaDays);
            fechaCosechaEst = d.toISOString().slice(0, 10);
        }

        const observaciones = container.querySelector("#observaciones")?.value || null;

        const payload = {
            id_recinto: recintoId,
            uso_sigpac: uso,
            sistema_cultivo: sistema_cultivo,
            sistema_explotacion: sistema,
            tipo_registro: tipo_registro,
            campana: campana,
            estado: estado,
            variedad: variedad,
            origen_cultivo: origen,
            cod_producto: cod_producto,
            cultivo_custom: cultivo_custom,
            observaciones: observaciones,
            cosecha_estimada_auto: cosechaAuto,
        };

        // Fechas según tipo_registro
        if (tipo_registro === "CAMPANA") {
            payload.fecha_siembra = toISODate(fechaInicio);
        } else {
            payload.fecha_implantacion = toISODate(fechaInicio);
        }
        payload.fecha_cosecha_estimada = toISODate(fechaCosechaEst);

        // Construir Avanzado (opcional)
        const aAprove = pickObjFromSelect(advAprove);
        const aCob = pickObjFromSelect(advCob);
        const aDest = pickObjFromSelect(advDest);

        const mvTipoObj = pickObjFromSelect(advMvrTipo);
        const mvDetObjBase = pickObjFromSelect(advMvrDet);
        const mvDetObj = mvDetObjBase
            ? { ...mvDetObjBase, parent: (advMvrTipo?.value || "").trim() || null }
            : null;

        const materialVegetal =
            (mvTipoObj || mvDetObj)
                ? { tipo: mvTipoObj, detalle: mvDetObj }
                : null;

        const aTipoLabor = pickObjFromSelect(advTipoLabor);
        const aProcMv = pickObjFromSelect(advProcMv);
        const aSenp = pickObjFromSelect(advSenp);

        const avanzadoRaw = {
            aprovechamiento: aAprove,
            tipo_cobertura_suelo: aCob,
            destino_cultivo: aDest,
            material_vegetal: materialVegetal,
            tipo_labor: aTipoLabor,
            procedencia_material_vegetal: aProcMv,
            senp: aSenp
        };

        // normaliza a null si está vacío
        function normalizeAvanzado(av) {
            if (!av || typeof av !== "object") return null;

            // aplanado simple
            const vals = [
                av.aprovechamiento, av.tipo_cobertura_suelo, av.destino_cultivo,
                av.tipo_labor, av.procedencia_material_vegetal, av.senp
            ];

            const mv = av.material_vegetal;
            if (mv && (mv.tipo || mv.detalle)) vals.push(mv.tipo, mv.detalle);

            const hasAny = vals.some(v => v && (v.codigo || v.label));
            return hasAny ? av : null;
        }

        payload.avanzado = normalizeAvanzado(avanzadoRaw);

        // -------------------------
        // ENDPOINT SEGÚN MODO
        // -------------------------
        let url, method;

        if (mode === "historico_add") {
            url = `/api/mis-recinto/${recintoId}/cultivo-historico`;
            method = "POST";
        } else if (mode === "historico_edit") {
            if (!cultivoId) {
                msg.textContent = "Error: falta id_cultivo para editar el histórico.";
                msg.className = "text-danger";
                return;
            }
            url = `/api/cultivos/${cultivoId}`;
            method = "PATCH";
        } else {
            // modo actual
            url = `/api/mis-recinto/${recintoId}/cultivo`;
            method = cultivo ? "PATCH" : "POST";
        }

        try {
            await fetchJson(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            NotificationSystem.show({
                type: "success",
                title: "Cultivo guardado",
                message: "El cultivo ha sido guardado correctamente",
            });

            if (mode === "historico_edit" && currentCultivoId && String(cultivoId) === String(currentCultivoId)) {
                needsRefreshActualCultivo = true;
                // Repinta ya el actual en background aunque esté oculto
                renderCultivosForRecinto(recintoId);
            }

            // -------------------------
            // POST-ACCIÓN SEGÚN MODO
            // -------------------------
            if (mode === "historico_add" || mode === "historico_edit") {
                // volver al overlay y refrescar histórico
                if (typeof onDone === "function") onDone();
            } else {
                renderCultivosForRecinto(recintoId);
            }
        } catch (e) {
            console.warn(e);

            const backendMsg = e?.data?.error || e?.data?.message || "";

            if (backendMsg.includes("fecha de inicio debe ser anterior")) {
                msg.textContent = "El cultivo no puede ser más reciente que el actual.";
            } else if (backendMsg.includes("La fecha fin no puede ser anterior")) {
                msg.textContent = "La fecha fin no puede ser anterior a la de inicio.";
            } else if (backendMsg) {
                msg.textContent = backendMsg;
            } else {
                msg.textContent = "No se pudo guardar el cultivo.";
            }

            msg.className = "text-danger";
        }
    }, { signal });
}

function actualizarHistoricoCultivos() {
    const sp = document.getElementById("side-panel");
    const panel = document.getElementById("cultivos-historico-panel");

    if (sp && panel && sp.classList.contains("cultivos-historico-open")) {
        // El panel está abierto, recargar los datos
        if (currentSideRecintoId) {
            const btnHistorico = document.getElementById("btn-historico-cultivos");
            if (btnHistorico) {
                btnHistorico.click(); // Simular click para recargar
            }
        }
        return true;
    }
    return false;
}

window.renderCultivosForRecinto = window.renderCultivosForRecinto || renderCultivosForRecinto;
window.closeHistoricoPanel = window.closeHistoricoPanel || closeHistoricoPanel;
window.closeGaleriaPanel = window.closeGaleriaPanel || closeGaleriaPanel;
window.actualizarHistoricoCultivos = window.actualizarHistoricoCultivos || actualizarHistoricoCultivos;
