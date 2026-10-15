// GeoSigma viewer: map of sites coloured by model resistivity at a chosen depth,
// with each site's 1D models, their provenance and a section along the line.
"use strict";

const state = { depth: 500, sigma: false, hidden: new Set(), site: null, dataset: null, surveys: [] };
const $ = (id) => document.getElementById(id);
// A read-only web copy (geosigma.export_static) sets GEOSIGMA_STATIC with its own api and basemap.
const STATIC = window.GEOSIGMA_STATIC || null;
const api = STATIC ? STATIC.api : (path) => fetch(path).then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)));

// Colour ramp on log10(rho), 1 to 1000 ohm.m: conductive red to resistive blue.
const RAMP = [[0, "#b2182b"], [0.5, "#ef8a62"], [1, "#fddbc7"], [1.5, "#d1e5f0"], [2, "#67a9cf"], [3, "#2166ac"]];
const RELIABILITY = {
  reliable: "within the model's depth of investigation",
  unknown_doi: "depth of investigation not given in the report",
  below_doi: "below the depth of investigation",
  beyond_model: "deeper than the model reaches",
  no_model: "no 1D model at this site",
};

const fmt = (rho) => {
  if (rho == null) return "n/a";
  if (state.sigma) return `${(1000 / rho).toPrecision(3)} mS/m`;
  return `${rho.toPrecision(3)} Ω·m`;
};

const map = new maplibregl.Map({
  container: "map",
  style: STATIC ? STATIC.style : {
    version: 8,
    sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256,
      attribution: "© OpenStreetMap contributors" } },
    layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.6 } }],
  },
  center: [35.1, 31.6], zoom: 6.6,
});
map.addControl(new maplibregl.NavigationControl(), "top-left");
map.addControl(new maplibregl.ScaleControl(), "bottom-left");

function colourExpr() {
  const stops = RAMP.flatMap(([v, c]) => [v, c]);
  return ["case", ["==", ["get", "rho_at_depth"], null], "#9aa4b2",
    ["interpolate", ["linear"], ["log10", ["max", ["get", "rho_at_depth"], 0.01]], ...stops]];
}

async function loadSites(current = () => true) {
  const gj = await api(`/api/sites?depth=${state.depth}`);
  if (!current()) return;
  gj.features = gj.features.filter((f) => !state.hidden.has(f.properties.survey));
  for (const f of gj.features) f.properties.rho_at_depth ??= null;
  if (map.getSource("sites")) {
    map.getSource("sites").setData(gj);
    return;
  }
  map.addSource("sites", { type: "geojson", data: gj });
  map.addLayer({
    id: "sites", type: "circle", source: "sites",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 3, 10, 6, 14, 9],
      "circle-color": colourExpr(),
      "circle-opacity": ["match", ["get", "reliability"], "reliable", 1, "unknown_doi", 0.9, "below_doi", 0.35, 0.15],
      "circle-stroke-width": ["match", ["get", "reliability"], "unknown_doi", 1, "reliable", 1, 1],
      "circle-stroke-color": ["match", ["get", "reliability"], "beyond_model", "#9aa4b2", "no_model", "#9aa4b2", "#ffffff"],
    },
  });
  map.addLayer({
    id: "selected", type: "circle", source: "sites", filter: ["==", ["get", "site"], ""],
    paint: { "circle-radius": 11, "circle-color": "rgba(0,0,0,0)", "circle-stroke-width": 2, "circle-stroke-color": "#111" },
  });
  map.on("click", "sites", (e) => selectSite(e.features[0].properties));
  map.on("mouseenter", "sites", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "sites", () => (map.getCanvas().style.cursor = ""));
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
  map.on("mousemove", "sites", (e) => {
    const p = e.features[0].properties;
    popup.setLngLat(e.lngLat).setHTML(
      `<b>${p.name || p.site}</b><br>${fmt(p.rho_at_depth === "null" ? null : p.rho_at_depth)} at ${state.depth} m` +
      `<br><span style="color:#687385">${RELIABILITY[p.reliability] || ""}</span>`).addTo(map);
  });
  map.on("mouseleave", "sites", () => popup.remove());
  fitTo(gj);
}

function fitTo(gj) {
  if (!gj.features.length) return;
  const b = new maplibregl.LngLatBounds();
  gj.features.forEach((f) => b.extend(f.geometry.coordinates));
  map.fitBounds(b, { padding: 60, maxZoom: 11, duration: 0 });
}

async function loadSurveys() {
  state.surveys = await api("/api/surveys");
  const cov = await api(`/api/coverage?depth=${state.depth}`);
  $("surveys").innerHTML = state.surveys.map((s) => {
    const c = cov[s.id] || {};
    const n = s.n_datasets;
    const ok = (c.reliable || 0) + (c.unknown_doi || 0);
    return `<div class="survey"><label><input type="checkbox" data-s="${s.id}" ${state.hidden.has(s.id) ? "" : "checked"}>
      ${s.name}</label><small>${s.year} · ${s.methods} · ${s.n_sites} sites, ${n} datasets` +
      (c ? ` · ${ok} models reach ${state.depth} m` : "") + ` · ${s.extraction_status}</small></div>`;
  }).join("") || '<p class="muted">No surveys in the database yet.</p>';
  document.querySelectorAll("[data-s]").forEach((cb) => cb.addEventListener("change", () => {
    cb.checked ? state.hidden.delete(cb.dataset.s) : state.hidden.add(cb.dataset.s);
    loadSites();
  }));
}

function legend() {
  const grad = RAMP.map(([v, c]) => `${c} ${(v / 3) * 100}%`).join(",");
  const labels = state.sigma ? ["1000", "100", "10", "1 mS/m"] : ["1", "10", "100", "1000 Ω·m"];
  $("legend").innerHTML = `<div class="legendbar" style="background:linear-gradient(to right,${grad})"></div>
    <div class="legendrow">${labels.map((l) => `<span>${l}</span>`).join("")}</div>
    <p><span class="sym" style="background:#67a9cf"></span>model value at the depth</p>
    <p><span class="sym" style="background:#67a9cf;opacity:.35"></span>below depth of investigation</p>
    <p><span class="sym" style="border:1px solid #9aa4b2"></span>model too shallow, or no model</p>
    <p class="muted">Most digitised models have no stated depth of investigation; check the source page.</p>`;
}

async function selectSite(p) {
  state.site = p;
  map.setFilter("selected", ["all", ["==", ["get", "site"], p.site], ["==", ["get", "survey"], p.survey]]);
  $("detailEmpty").hidden = true;
  $("detail").hidden = false;
  $("siteTitle").textContent = p.name || p.site;
  const survey = state.surveys.find((s) => s.id === p.survey);
  $("siteMeta").textContent = `${survey ? survey.name : p.survey} · ${p.orig}`;
  const ids = typeof p.datasets === "string" ? JSON.parse(p.datasets) : p.datasets;
  const dss = await Promise.all(ids.map((id) => api(`/api/datasets/${encodeURIComponent(id)}`)));
  state.siteDatasets = dss;
  $("dsList").innerHTML = dss.map((d, i) => `<div class="ds" data-i="${i}">${d.method} ${d.level} ${d.representation}
    ${d.model_type ? "(" + d.model_type + ")" : ""}${d.spacing_m ? " a = " + d.spacing_m + " m" : ""}${d.measured_on && d.representation === "profile" ? " · " + d.measured_on : ""}${d.representation === "map_grid" && d.line ? " · " + d.line : ""} · confidence ${d.confidence}
    ${d.status === "draft" ? '<span class="badge">unreviewed</span>' : ""}</div>`).join("") ||
    '<p class="muted">No datasets at this site yet.</p>';
  document.querySelectorAll(".ds").forEach((el) => el.addEventListener("click", () => showDataset(dss[+el.dataset.i], el)));
  $("showSection").hidden = !p.line || !p.has_model;  // sections are drawn from depth models
  if (dss.length) showDataset(dss[0], document.querySelector(".ds"));
  else { Plotly.purge("profile"); $("prov").innerHTML = ""; }
}

function profileTraces(d) {
  const v = (rho) => (state.sigma ? 1000 / rho : rho);
  if (d.layers && d.layers.length) {
    const x = [], y = [];
    // an open-ended last layer (half-space) is drawn a third deeper than its top, so it shows
    const lastTop = Math.max(...d.layers.map((l) => l.top_m));
    const bottom = Math.max(d.depth_max_m || 0, ...d.layers.map((l) => l.bottom_m || 0), lastTop * 1.3 || 100);
    for (const l of d.layers) {
      const r = l.rho_ohmm ?? l.rho_min;  // a lower bound ("infinity" on the sheet) is drawn at its bound
      if (r == null) { x.push(null, null); y.push(l.top_m, l.bottom_m ?? bottom); continue; }
      x.push(v(r), v(r));
      y.push(l.top_m, l.bottom_m ?? bottom);
    }
    return { x, y };
  }
  return { x: d.samples.map((s) => v(s.rho_ohmm)), y: d.samples.map((s) => s.depth_m) };
}

function showDataset(d, el) {
  state.dataset = d;
  document.querySelectorAll(".ds").forEach((e) => e.classList.toggle("active", e === el));
  try {
  const shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: state.depth, y1: state.depth,
    line: { color: "#888", dash: "dot", width: 1 } }];
  if (d.doi_m) shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: d.doi_m, y1: d.doi_m,
    line: { color: "#a86a00", dash: "dash", width: 1.5 } });
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const t = profileTraces(d);
  if (d.representation === "model_1d") {
    const pts = !(d.layers && d.layers.length);  // values at a few depths: show the points
    Plotly.react("profile", [{ ...t, mode: pts ? "lines+markers" : "lines", line: { color: "#1f5fa8", width: 2, shape: "linear" },
      hovertemplate: `%{x:.3g} ${state.sigma ? "mS/m" : "Ω·m"} at %{y:.0f} m<extra></extra>` }], {
      margin: { l: 55, r: 10, t: 10, b: 45 }, shapes,
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: dark ? "#e4e8ee" : "#1d2430" },
      xaxis: { type: "log", title: state.sigma ? "Conductivity (mS/m)" : "Resistivity (Ω·m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      yaxis: { autorange: "reversed", title: d.depth_ref === "below_sea_level" ? "Depth below sea level (m)" : "Depth below ground (m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      annotations: d.doi_m ? [{ xref: "paper", x: 1, y: d.doi_m, text: "DOI", showarrow: false, xanchor: "right", yanchor: "bottom" }] : [],
    }, { displayModeBar: false, responsive: true });
  } else if (d.representation === "sounding_curve") {
    Plotly.react("profile", [{ x: d.curve.map((c) => c.x), y: d.curve.map((c) => c.rho_a), mode: "markers",
      marker: { color: "#1f5fa8", size: 7 }, hovertemplate: "%{x:.3g}: %{y:.3g} Ω·m<extra></extra>" }], {
      margin: { l: 55, r: 10, t: 10, b: 45 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: dark ? "#e4e8ee" : "#1d2430" },
      xaxis: { type: "log", title: d.x_quantity || "x" }, yaxis: { type: "log", title: "Apparent resistivity (Ω·m)" },
    }, { displayModeBar: false, responsive: true });
  } else if (d.representation === "profile") {
    // every date of this line and spacing, with the selected station marked
    const same = (state.siteDatasets || []).filter((o) => o.representation === "profile" && o.line === d.line && o.spacing_m === d.spacing_m);
    const palette = ["#1f5fa8", "#c2410c", "#15803d"];
    const traces = same.map((o, k) => ({ x: o.profile.map((q) => q.station), y: o.profile.map((q) => q.rho_a),
      name: o.measured_on, mode: "lines+markers", line: { color: palette[k % 3], width: o === d ? 2.5 : 1.2 },
      marker: { size: o === d ? 6 : 4 }, hovertemplate: "reading %{x}: %{y:.3g} Ω·m<extra>" + o.measured_on + "</extra>" }));
    const here = d.profile.find((q) => q.site === (state.site && state.site.site));
    Plotly.react("profile", traces, {
      margin: { l: 55, r: 10, t: 10, b: 45 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: dark ? "#e4e8ee" : "#1d2430" }, showlegend: same.length > 1, legend: { orientation: "h", y: 1.12 },
      shapes: here ? [{ type: "line", yref: "paper", y0: 0, y1: 1, x0: here.station, x1: here.station, line: { color: "#888", dash: "dot", width: 1 } }] : [],
      xaxis: { title: `Reading along ${d.line} (a = ${d.spacing_m} m)`, gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      yaxis: { type: "log", title: "Apparent resistivity (Ω·m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
    }, { displayModeBar: false, responsive: true });
  } else if (d.representation === "map_grid") {
    // roving-dipole maps: this station's apparent resistivity for every source that covers it
    const sid = state.site && state.site.site;
    const maps = (state.siteDatasets || []).filter((o) => o.representation === "map_grid" && o.survey === d.survey);
    const rows = maps.map((o) => [o, o.profile.find((q) => q.site === sid)]).filter(([, q]) => q);
    Plotly.react("profile", [{ x: rows.map(([o]) => o.line), y: rows.map(([, q]) => q.rho_a), type: "bar",
      marker: { color: rows.map(([o]) => (o === d ? "#c2410c" : "#1f5fa8")) },
      hovertemplate: "%{x}: %{y:.3g} Ω·m<extra></extra>" }], {
      margin: { l: 55, r: 10, t: 10, b: 70 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: dark ? "#e4e8ee" : "#1d2430" },
      xaxis: { title: "Transmitter (source)", type: "category", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      yaxis: { type: "log", title: "Apparent resistivity (Ω·m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
    }, { displayModeBar: false, responsive: true });
  } else {
    Plotly.purge("profile");
    $("profile").innerHTML = d.representation === "interface_depth"
      ? `<p>Interface at <b>${d.interface_depth_m} m</b> below ground: ${d.criterion || ""}</p>`
      : `<p>${d.summary || d.representation}</p>`;
  }
  } catch (e) {  // e.g. the chart library did not load: still show the source below
    console.error(e);
    $("profile").innerHTML = `<p class="muted">The chart could not be drawn${window.Plotly ? "" : " (the Plotly chart library did not load; check the internet connection or a content blocker)"}.</p>`;
  }
  renderReview(d);
  const p = d.provenance;
  const doc = d.document_info;
  const pages = p.pages || [];
  $("prov").innerHTML = `<h2>Where this came from</h2>
    <p>${doc ? doc.title : p.document}</p>
    ${(d.source_views || []).map((v, i) => sourceView(d, v, i)).join("") || (pages.length ? "<p>Page " + pages.join(", ") + "</p>" : "")}
    <p class="muted">The chart above is our digitised version of what is framed here.
    ${p.method.replace("_", " ")}${p.tool ? " with " + p.tool : ""} on ${p.extracted_on || "?"}
    ${d.digitisation_error ? "<br>Reading error " + d.digitisation_error : ""}
    ${d.doi_m ? "<br>Depth of investigation " + d.doi_m + " m" + (d.doi_estimated ? " (estimated)" : "") : "<br>No depth of investigation in the report"}
    ${d.notes ? "<br>" + d.notes : ""}</p>`;
}

// The part of a source page a dataset was read from, with the selected station ringed.
function frame(v, whole) {
  const site = state.site && state.site.site;
  const mark = v.marks.find((m) => m.site === site);
  if (whole || (!v.region && !(v.zoom && mark))) return [0, 0, 1, 1];
  if (v.zoom && mark) {  // a window around the station, about a fifth of the page wide
    const w = 0.22, h = Math.min(1, (w / (v.aspect || 1.4)) * 0.75);
    const x0 = Math.min(Math.max(mark.x - w / 2, 0), 1 - w), y0 = Math.min(Math.max(mark.y - h / 2, 0), 1 - h);
    return [x0, y0, x0 + w, y0 + h];
  }
  return v.region;
}

function sourceCrop(d, v, i, whole) {
  const img = STATIC ? STATIC.sourceImage(d.survey, v.document, v.page)
    : { src: `/api/source/${d.survey}/${v.document}/page/${v.page}.png?dpi=${v.zoom ? 200 : 150}`, x: 0, y: 0, w: 1, h: 1 };
  if (!img) return `<p class="muted">Page image not included in this copy.</p>`;
  const [x0, y0, x1, y1] = frame(v, whole);
  const rw = x1 - x0, rh = y1 - y0, aspect = v.aspect || 1.4;
  // img.{x,y,w,h}: where the page sits inside the image file, as fractions of that file
  const W = 100 / (rw * img.w), left = -(img.x + x0 * img.w) * W, top = -(img.y + y0 * img.h) / (rh * img.h) * 100;
  const site = state.site && state.site.site;
  const rings = v.marks.filter((m) => m.site === site && m.x >= x0 && m.x <= x1 && m.y >= y0 && m.y <= y1)
    .map((m) => `<span class="ring" style="left:${((m.x - x0) / rw) * 100}%;top:${((m.y - y0) / rh) * 100}%"></span>`).join("")
    + (v.boxes || []).map(([a, b, c, e]) => `<span class="hl" style="left:${((a - x0) / rw) * 100}%;top:${((b - y0) / rh) * 100}%;`
      + `width:${((c - a) / rw) * 100}%;height:${((e - b) / rh) * 100}%"></span>`).join("");
  return `<div class="crop${whole ? " whole" : ""}" data-i="${i}" title="Click to switch between this part and the whole page"
    style="aspect-ratio:${rw / (rh * aspect)}"><img loading="lazy" alt="Source page ${v.page}" src="${img.src}"
    style="width:${W}%;left:${left}%;top:${top}%" onerror="this.parentNode.replaceWith(Object.assign(document.createElement('p'),{className:'muted',textContent:'Source PDF not available locally.'}))">${rings}</div>`;
}

function sourceView(d, v, i) {
  return `<figure class="src"><figcaption>${v.caption}</figcaption>${sourceCrop(d, v, i, false)}</figure>`;
}

async function showSection() {
  const p = state.site;
  if (!window.Plotly) {
    $("sectionPane").hidden = false;
    $("section").innerHTML = '<p class="muted">The Plotly chart library did not load; check the internet connection or a content blocker.</p>';
    return;
  }
  if (!p || !p.line) return;
  const s = await api(`/api/sections/${p.survey}/${encodeURIComponent(p.line)}`);
  $("sectionPane").hidden = false;
  $("sectionTitle").textContent = `Line ${s.line}: 1D models side by side (${s.stations.length} stations)`;
  const z = s.depths.map((_, i) => s.stations.map((st) => (st.rho[i] ? Math.log10(state.sigma ? 1000 / st.rho[i] : st.rho[i]) : null)));
  const colors = RAMP.map(([v, c]) => [v / 3, c]);
  Plotly.react("section", [{
    type: "heatmap", x: s.stations.map((st) => st.distance_m), y: s.depths, z, zmin: state.sigma ? 0 : 0, zmax: 3,
    colorscale: state.sigma ? colors.map(([v, c], i) => [v, colors[colors.length - 1 - i][1]]) : colors,
    text: s.stations.map((st) => st.site), hovertemplate: "%{x} m, %{y} m: 10^%{z:.2f}<extra></extra>",
    colorbar: { title: state.sigma ? "log σ (mS/m)" : "log ρ (Ω·m)" },
  }], {
    margin: { l: 55, r: 10, t: 6, b: 40 }, paper_bgcolor: "rgba(0,0,0,0)",
    xaxis: { title: "Distance along line (m)", tickvals: s.stations.map((st) => st.distance_m), ticktext: s.stations.map((st) => st.site) },
    yaxis: { autorange: "reversed", title: "Depth (m)" },
  }, { displayModeBar: false, responsive: true });
}

// The map follows the slider while it is dragged; requests that come back late are dropped.
let depthTimer = null, depthSeq = 0;
function setDepth(z, final) {
  state.depth = z;
  $("depthOut").textContent = `${z} m`;
  clearTimeout(depthTimer);
  depthTimer = setTimeout(async () => {
    const seq = ++depthSeq;
    await loadSites(() => seq === depthSeq);
    if (final) {
      loadSurveys();
      if (state.dataset) showDataset(state.dataset, document.querySelector(".ds.active"));
    }
  }, final ? 0 : STATIC ? 0 : 60);
}
$("prov").addEventListener("click", (e) => {
  const el = e.target.closest(".crop");
  if (!el || !state.dataset) return;
  const i = +el.dataset.i;
  el.outerHTML = sourceCrop(state.dataset, state.dataset.source_views[i], i, !el.classList.contains("whole"));
});
$("depth").addEventListener("input", (e) => setDepth(+e.target.value, false));
$("depth").addEventListener("change", (e) => setDepth(+e.target.value, true));
$("sigma").addEventListener("change", (e) => {
  state.sigma = e.target.checked;
  legend();
  if (state.dataset) showDataset(state.dataset, document.querySelector(".ds.active"));
  if (!$("sectionPane").hidden) showSection();
});
$("showSection").addEventListener("click", showSection);
$("closeSection").addEventListener("click", () => ($("sectionPane").hidden = true));

legend();
loadSurveys();
map.on("load", () => loadSites());


// Review: the decision is written to the dataset's source file by the API.
function renderReview(d) {
  const by = d.provenance.checked_by ? ` by ${d.provenance.checked_by}${d.provenance.checked_on ? " on " + d.provenance.checked_on : ""}` : "";
  if (STATIC) { $("review").innerHTML = `<span>Review: <b>${d.status}</b>${by}</span><span class="muted">Review in the local tool.</span>`; return; }
  const btn = (st, label) => `<button data-st="${st}" class="${d.status === st ? "on" : ""}">${label}</button>`;
  $("review").innerHTML = `<span>Review: <b>${d.status}</b>${by}</span>
    ${btn("checked", "Checked")}${btn("approved", "Approve")}${btn("rejected", "Reject")}
    ${d.status !== "draft" ? btn("draft", "Undo") : ""}
    <input id="reviewNote" placeholder="Note (optional)" value="${(d.review_note || "").replace(/"/g, "&quot;")}">`;
  $("review").querySelectorAll("button").forEach((b) => b.addEventListener("click", async () => {
    const r = await fetch(`/api/datasets/${encodeURIComponent(d.id)}/status`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: b.dataset.st, note: $("reviewNote").value || null }),
    });
    if (!r.ok) { alert("Could not save: " + (await r.text())); return; }
    const saved = await r.json();
    Object.assign(d, { status: saved.status, review_note: saved.review_note, provenance: { ...d.provenance, ...saved.provenance } });
    renderReview(d);
    const el = document.querySelector(".ds.active .badge");
    if (el && d.status !== "draft") el.remove();
  }));
}
