// GeoSigma viewer: map of sites coloured by model resistivity at a chosen depth,
// with each site's 1D models, their provenance and a section along the line.
"use strict";

const state = { depth: 500, sigma: false, hidden: new Set(), site: null, dataset: null, surveys: [] };
const $ = (id) => document.getElementById(id);
const api = (path) => fetch(path).then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)));

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
  style: {
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

async function loadSites() {
  const gj = await api(`/api/sites?depth=${state.depth}`);
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
  $("dsList").innerHTML = dss.map((d, i) => `<div class="ds" data-i="${i}">${d.method} ${d.level} ${d.representation}
    ${d.model_type ? "(" + d.model_type + ")" : ""} · confidence ${d.confidence}
    ${d.status === "draft" ? '<span class="badge">unreviewed</span>' : ""}</div>`).join("") ||
    '<p class="muted">No datasets at this site yet.</p>';
  document.querySelectorAll(".ds").forEach((el) => el.addEventListener("click", () => showDataset(dss[+el.dataset.i], el)));
  $("showSection").hidden = !p.line;
  if (dss.length) showDataset(dss[0], document.querySelector(".ds"));
  else { Plotly.purge("profile"); $("prov").innerHTML = ""; }
}

function profileTraces(d) {
  const v = (rho) => (state.sigma ? 1000 / rho : rho);
  if (d.layers && d.layers.length) {
    const x = [], y = [];
    const bottom = d.depth_max_m || Math.max(...d.layers.map((l) => l.bottom_m || l.top_m * 1.5 || 100));
    for (const l of d.layers) {
      x.push(v(l.rho_ohmm), v(l.rho_ohmm));
      y.push(l.top_m, l.bottom_m ?? bottom);
    }
    return { x, y };
  }
  return { x: d.samples.map((s) => v(s.rho_ohmm)), y: d.samples.map((s) => s.depth_m) };
}

function showDataset(d, el) {
  state.dataset = d;
  document.querySelectorAll(".ds").forEach((e) => e.classList.toggle("active", e === el));
  const shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: state.depth, y1: state.depth,
    line: { color: "#888", dash: "dot", width: 1 } }];
  if (d.doi_m) shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: d.doi_m, y1: d.doi_m,
    line: { color: "#a86a00", dash: "dash", width: 1.5 } });
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const t = profileTraces(d);
  if (d.representation === "model_1d") {
    Plotly.react("profile", [{ ...t, mode: "lines", line: { color: "#1f5fa8", width: 2, shape: "linear" },
      hovertemplate: `%{x:.3g} ${state.sigma ? "mS/m" : "Ω·m"} at %{y:.0f} m<extra></extra>` }], {
      margin: { l: 55, r: 10, t: 10, b: 45 }, shapes,
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: dark ? "#e4e8ee" : "#1d2430" },
      xaxis: { type: "log", title: state.sigma ? "Conductivity (mS/m)" : "Resistivity (Ω·m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      yaxis: { autorange: "reversed", title: "Depth below ground (m)", gridcolor: dark ? "#2e343e" : "#e6e9ef" },
      annotations: d.doi_m ? [{ xref: "paper", x: 1, y: d.doi_m, text: "DOI", showarrow: false, xanchor: "right", yanchor: "bottom" }] : [],
    }, { displayModeBar: false, responsive: true });
  } else {
    Plotly.purge("profile");
    $("profile").innerHTML = `<p>${d.summary || d.representation}</p>`;
  }
  const p = d.provenance;
  const doc = d.document_info;
  const pages = p.pages || [];
  $("prov").innerHTML = `<h2>Where this came from</h2>
    <p>${doc ? doc.title : p.document}${pages.length ? ", page " + pages.join(", ") : ""}${p.figure ? "<br>" + p.figure : ""}</p>
    <p class="muted">${p.method.replace("_", " ")}${p.tool ? " with " + p.tool : ""} on ${p.extracted_on || "?"}
    ${d.digitisation_error ? "<br>Reading error " + d.digitisation_error : ""}
    ${d.doi_m ? "<br>Depth of investigation " + d.doi_m + " m" + (d.doi_estimated ? " (estimated)" : "") : "<br>No depth of investigation in the report"}
    ${d.notes ? "<br>" + d.notes : ""}</p>
    ${pages.length ? `<a href="/api/source/${d.survey}/${p.document}/page/${pages[0]}.png?dpi=200" target="_blank">
      <img loading="lazy" alt="Source page" src="/api/source/${d.survey}/${p.document}/page/${pages[0]}.png?dpi=70"
      onerror="this.replaceWith(document.createTextNode('Source PDF not available locally.'))"></a>` : ""}`;
}

async function showSection() {
  const p = state.site;
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

$("depth").addEventListener("input", (e) => ($("depthOut").textContent = `${e.target.value} m`));
$("depth").addEventListener("change", (e) => {
  state.depth = +e.target.value;
  loadSites(); loadSurveys();
  if (state.dataset) showDataset(state.dataset, document.querySelector(".ds.active"));
});
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
map.on("load", loadSites);
