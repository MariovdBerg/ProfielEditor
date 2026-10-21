/* Profieleditor – interactieve bewerking van .prfl-profielen.
 *
 * Het profiel wordt in de editor bewaard als één lijst punten [x, z, r] van voorland tot kruin,
 * met `voorland` = aantal voorlandpunten inclusief de teen (0 = geen voorland).
 * Het teenpunt is dus punten[voorland - 1] en tevens het eerste dijkpunt.
 * Lezen, controleren en schrijven gebeurt op de server met prflcheck.
 */
"use strict";

// ── Constanten (gelijk aan prflcheck/checks.py) ──────────────────────────────
const TANAMIN = 0.01, TANAMAX = 1.0, TANAFLW = 1 / 15, TANASTL = 0.125;
const TANAMINVOORLAND = 0.1, DELTAXMINVOORLAND = 10, DELTAXMINDIJK = 0.1;
const RAAKAFSTAND = 12;      // pixels waarbinnen een punt geraakt wordt
const MARGE = { l: 64, r: 18, t: 18, b: 44 };

// ── Toestand ──────────────────────────────────────────────────────────────────
const staat = {
  instellingen: null,
  overzicht: null,       // {vakken: [...], ...}
  vakIndex: -1,          // index in overzicht.vakken
  data: null,            // antwoord van /api/profiel
  profiel: null,         // het profiel dat bewerkt wordt
  opgeslagenJson: "",    // laatst geladen/opgeslagen toestand, om wijzigingen te herkennen
  selectie: null,        // index van het geselecteerde punt
  historie: [], toekomst: [],
  beeld: null,           // {x0, x1, z0, z1}
  check: null,
  filter: "alle",
  ahn: null,             // AHN-lijnen bij het geopende profiel: {lijnen, melding, waarschuwingen}
  spiegel: new Set(),    // profielen waarvan de AHN-lijnen gespiegeld worden (alleen deze sessie)
};

const $ = (sel) => document.querySelector(sel);
const canvas = $("#grafiek");
const ctx = canvas.getContext("2d");

// ── Hulpfuncties ──────────────────────────────────────────────────────────────
async function api(pad, body) {
  const opties = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const antwoord = await fetch(pad, opties);
  const data = await antwoord.json().catch(() => ({ fout: `HTTP ${antwoord.status}` }));
  if (!antwoord.ok || data.fout) throw new Error(data.fout || `HTTP ${antwoord.status}`);
  return data;
}

function toast(tekst, ms = 2600) {
  const el = $("#toast");
  el.textContent = tekst;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), ms);
}

const afronden = (v, d = 3) => Math.round(v * 10 ** d) / 10 ** d;
const fmt = (v, d = 3) => (v === null || v === undefined || Number.isNaN(v) ? "" : Number(v).toFixed(d));
const kloon = (o) => JSON.parse(JSON.stringify(o));
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function puntLabel(i, p = staat.profiel) {
  const n = p.voorland;
  if (n > 0 && i < n - 1) return `V${i + 1}`;
  return `P${n > 0 ? i - n + 2 : i + 1}`;
}
const isVoorlandPunt = (i, p = staat.profiel) => p.voorland > 0 && i < p.voorland - 1;
const teenIndex = (p = staat.profiel) => (p.voorland > 0 ? p.voorland - 1 : 0);

/** Classificeer elk deel tussen punt i en i+1, zoals prflcheck dat doet. */
function profieldelen(p = staat.profiel) {
  const delen = [];
  const pts = p.punten;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, z1] = pts[i], [x2, z2] = pts[i + 1];
    const dx = x2 - x1, dz = z2 - z1;
    const voorland = p.voorland > 0 && i < p.voorland - 1;
    let soort, reden = "";
    if (voorland) {
      soort = "voorland";
      if (dx <= 0) reden = "x loopt niet op";
      else if (dx < DELTAXMINVOORLAND) reden = "afstand < 10 m";
      else if (Math.abs(dz / dx) > TANAMINVOORLAND) reden = "steiler dan 1:10";
      else if (z2 < pts[0][1]) reden = "lager dan eerste punt";
    } else {
      const tan = dz / dx;
      if (dx <= 0) reden = "x loopt niet op";
      else if (dz <= 0) reden = "z loopt niet op";
      else if (dx < DELTAXMINDIJK) reden = "afstand < 0,1 m";
      else if (tan > TANAMAX) reden = "steiler dan 1:1";
      else if (tan < TANAMIN) reden = "flauwer dan 1:100";
      else if (tan > TANAFLW && tan < TANASTL) reden = "tussen berm en talud";
      soort = tan <= TANAFLW ? "berm" : "talud";
    }
    const helling = Math.abs(dz) < 1e-9 ? null : Math.abs(dx / dz);
    delen.push({ i, soort: reden ? "fout" : soort, reden, helling, dx, dz });
  }
  return delen;
}

const hellingTekst = (h) => (h === null ? "—" : `1:${h >= 100 ? h.toFixed(0) : h.toFixed(1)}`);

// ── Kleuren uit CSS ───────────────────────────────────────────────────────────
let kleur = {};
function leesKleuren() {
  const s = getComputedStyle(document.documentElement);
  for (const naam of ["achtergrond", "raster", "as", "tekst", "talud", "berm", "voorland", "fout",
    "origineel", "kruin", "dam", "punt-rand", "selectie", "ahn"]) {
    kleur[naam] = s.getPropertyValue(`--g-${naam}`).trim();
  }
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { leesKleuren(); tekenLegenda(); teken(); });

// ── Coördinaten ───────────────────────────────────────────────────────────────
function afmeting() {
  const r = canvas.getBoundingClientRect();
  return { w: r.width, h: r.height };
}
function naarScherm(x, z) {
  const { w, h } = afmeting(), b = staat.beeld;
  return [
    MARGE.l + ((x - b.x0) / (b.x1 - b.x0)) * (w - MARGE.l - MARGE.r),
    h - MARGE.b - ((z - b.z0) / (b.z1 - b.z0)) * (h - MARGE.t - MARGE.b),
  ];
}
function naarWereld(px, py) {
  const { w, h } = afmeting(), b = staat.beeld;
  return [
    b.x0 + ((px - MARGE.l) / (w - MARGE.l - MARGE.r)) * (b.x1 - b.x0),
    b.z0 + ((h - MARGE.b - py) / (h - MARGE.t - MARGE.b)) * (b.z1 - b.z0),
  ];
}

function passend() {
  if (!staat.profiel) return;
  const pts = [...staat.profiel.punten];
  if ($("#toon-origineel").checked && staat.data) pts.push(...staat.data.origineel.punten);
  const zs = pts.map((p) => p[1]);
  const k = staat.profiel.kruinhoogte;
  if (k !== null && Number.isFinite(k)) zs.push(k);
  if (!pts.length) { staat.beeld = { x0: -10, x1: 10, z0: -1, z1: 5 }; teken(); return; }
  let x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]));
  let z0 = Math.min(...zs), z1 = Math.max(...zs);
  if (x1 - x0 < 1) { x0 -= 1; x1 += 1; }
  if (z1 - z0 < 0.5) { z0 -= 0.5; z1 += 0.5; }
  const mx = (x1 - x0) * 0.06, mz = (z1 - z0) * 0.12;
  staat.beeld = { x0: x0 - mx, x1: x1 + mx, z0: z0 - mz, z1: z1 + mz };
  teken();
}

function zoom(factorX, factorZ, px, py) {
  const [cx, cz] = naarWereld(px, py), b = staat.beeld;
  staat.beeld = {
    x0: cx + (b.x0 - cx) * factorX, x1: cx + (b.x1 - cx) * factorX,
    z0: cz + (b.z0 - cz) * factorZ, z1: cz + (b.z1 - cz) * factorZ,
  };
  teken();
}

// ── Tekenen ───────────────────────────────────────────────────────────────────
function mooieStap(bereik, aantal) {
  const ruw = bereik / aantal, macht = 10 ** Math.floor(Math.log10(ruw)), f = ruw / macht;
  return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * macht;
}

function teken() {
  const dpr = window.devicePixelRatio || 1;
  const { w, h } = afmeting();
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  $("#leeg").hidden = !!staat.profiel;
  $("#legenda").hidden = !staat.profiel;
  if (!staat.profiel || !staat.beeld) return;

  const p = staat.profiel, b = staat.beeld;
  const pw = w - MARGE.l - MARGE.r, ph = h - MARGE.t - MARGE.b;

  // Raster en assen
  ctx.font = "11px Segoe UI, system-ui, sans-serif";
  ctx.lineWidth = 1;
  const sx = mooieStap(b.x1 - b.x0, Math.max(3, pw / 90)), sz = mooieStap(b.z1 - b.z0, Math.max(3, ph / 50));
  const dx = Math.max(0, -Math.floor(Math.log10(sx))), dz = Math.max(0, -Math.floor(Math.log10(sz)));
  ctx.strokeStyle = kleur.raster;
  ctx.fillStyle = kleur.tekst;
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (let x = Math.ceil(b.x0 / sx) * sx; x <= b.x1; x += sx) {
    const [px] = naarScherm(x, 0);
    ctx.beginPath(); ctx.moveTo(px, MARGE.t); ctx.lineTo(px, h - MARGE.b); ctx.stroke();
    ctx.fillText(x.toFixed(dx), px, h - MARGE.b + 5);
  }
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let z = Math.ceil(b.z0 / sz) * sz; z <= b.z1; z += sz) {
    const [, py] = naarScherm(0, z);
    ctx.beginPath(); ctx.moveTo(MARGE.l, py); ctx.lineTo(w - MARGE.r, py); ctx.stroke();
    ctx.fillText(z.toFixed(dz), MARGE.l - 6, py);
  }
  ctx.strokeStyle = kleur.as;
  ctx.strokeRect(MARGE.l, MARGE.t, pw, ph);
  ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  ctx.fillText("Afstand [m]", MARGE.l + pw / 2, h - 8);
  ctx.save();
  ctx.translate(14, MARGE.t + ph / 2); ctx.rotate(-Math.PI / 2);
  ctx.fillText("Hoogte [m+NAP]", 0, 0);
  ctx.restore();

  ctx.save();
  ctx.beginPath(); ctx.rect(MARGE.l, MARGE.t, pw, ph); ctx.clip();

  // Kruinhoogte en damhoogte
  const horizontaal = (z, k, tekst) => {
    if (z === null || !Number.isFinite(z)) return;
    const [, py] = naarScherm(0, z);
    ctx.strokeStyle = k; ctx.setLineDash([2, 4]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(MARGE.l, py); ctx.lineTo(w - MARGE.r, py); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = k; ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    ctx.fillText(tekst, MARGE.l + 6, py - 2);
  };
  horizontaal(p.kruinhoogte, kleur.kruin, `Kruinhoogte ${fmt(p.kruinhoogte, 2)} m+NAP`);
  if (Number(p.damtype) > 0) horizontaal(p.damhoogte, kleur.dam, `Damhoogte ${fmt(p.damhoogte, 2)} m+NAP`);

  // AHN-dwarsprofielen (achtergrond)
  if ($("#toon-ahn").checked && staat.ahn?.lijnen?.length) {
    const spiegel = staat.spiegel.has(staat.data?.bestand) ? -1 : 1;
    ctx.strokeStyle = kleur.ahn; ctx.lineWidth = 1; ctx.globalAlpha = 0.35;
    for (const lijn of staat.ahn.lijnen) {
      ctx.beginPath();
      let vorigeX = null;
      for (const punt of lijn) {
        if (!punt) { vorigeX = null; continue; }   // grens tussen de delen van een multipart-lijn
        const [x, z] = punt;
        const [px, py] = naarScherm(spiegel * x, z);
        // een gat in de AHN-data (ontbrekende punten) niet overbruggen
        if (vorigeX === null || Math.abs(x - vorigeX) > 2.5) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        vorigeX = x;
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // Origineel profiel
  if ($("#toon-origineel").checked && staat.data && !zelfdePunten(staat.data.origineel, p)) {
    ctx.strokeStyle = kleur.origineel; ctx.lineWidth = 1.5; ctx.setLineDash([6, 4]);
    ctx.beginPath();
    staat.data.origineel.punten.forEach(([x, z], i) => {
      const [px, py] = naarScherm(x, z);
      i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
    });
    ctx.stroke(); ctx.setLineDash([]);
  }

  // Profieldelen
  const delen = profieldelen(p);
  ctx.lineWidth = 2.6; ctx.lineCap = "round";
  for (const d of delen) {
    const [x1, y1] = naarScherm(...p.punten[d.i]), [x2, y2] = naarScherm(...p.punten[d.i + 1]);
    ctx.strokeStyle = kleur[d.soort];
    ctx.setLineDash(d.soort === "voorland" ? [8, 5] : []);
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  ctx.setLineDash([]);

  // Hellingen
  if ($("#toon-hellingen").checked) {
    ctx.font = "10.5px Segoe UI, system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (const d of delen) {
      const [x1, y1] = naarScherm(...p.punten[d.i]), [x2, y2] = naarScherm(...p.punten[d.i + 1]);
      if (Math.hypot(x2 - x1, y2 - y1) < 46) continue;
      const tekst = hellingTekst(d.helling);
      const mx = (x1 + x2) / 2 + 8, my = (y1 + y2) / 2 + 4;
      const breedte = ctx.measureText(tekst).width + 6;
      ctx.fillStyle = kleur.achtergrond; ctx.globalAlpha = 0.8;
      ctx.fillRect(mx - breedte / 2, my - 1, breedte, 14);
      ctx.globalAlpha = 1; ctx.fillStyle = kleur[d.soort];
      ctx.fillText(tekst, mx, my);
    }
  }

  // Punten en labels
  ctx.font = "600 11px Segoe UI, system-ui, sans-serif";
  ctx.textAlign = "center"; ctx.textBaseline = "bottom";
  const teen = teenIndex(p);
  p.punten.forEach(([x, z], i) => {
    const [px, py] = naarScherm(x, z);
    const vl = isVoorlandPunt(i, p);
    if (i === staat.selectie) {
      ctx.strokeStyle = kleur.selectie; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(px, py, 10, 0, 2 * Math.PI); ctx.stroke();
    }
    ctx.fillStyle = vl ? kleur.voorland : kleur.talud;
    ctx.strokeStyle = kleur["punt-rand"]; ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (i === teen && p.voorland > 0) {
      ctx.moveTo(px, py - 7); ctx.lineTo(px + 7, py); ctx.lineTo(px, py + 7); ctx.lineTo(px - 7, py); ctx.closePath();
    } else {
      ctx.arc(px, py, vl ? 4.5 : 5.5, 0, 2 * Math.PI);
    }
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = i === staat.selectie ? kleur.selectie : kleur.tekst;
    ctx.fillText(puntLabel(i, p), px, py - 10);
  });
  ctx.restore();
}

function zelfdePunten(a, b) {
  return a.voorland === b.voorland && JSON.stringify(a.punten) === JSON.stringify(b.punten);
}

function tekenLegenda() {
  const regels = [
    ["talud", "", "Talud"], ["berm", "", "Berm"], ["voorland", "streep", "Voorland"],
    ["fout", "", "Ongeldig deel"], ["origineel", "streep", "Origineel"], ["kruin", "stippel", "Kruinhoogte"],
  ];
  const n = staat.ahn?.lijnen?.length;
  if (n) regels.push(["ahn", "", `AHN (${n} ${n === 1 ? "lijn" : "lijnen"})`]);
  $("#legenda").innerHTML = regels.map(([k, s, t]) => `<div><i class="${s}" style="border-color:${kleur[k]}"></i>${t}</div>`).join("");
}

// ── Muis ──────────────────────────────────────────────────────────────────────
let sleep = null;   // {soort: 'punt'|'pan', ...}

function raakPunt(px, py) {
  let beste = null, afstand = RAAKAFSTAND;
  staat.profiel.punten.forEach(([x, z], i) => {
    const [sx, sy] = naarScherm(x, z), d = Math.hypot(sx - px, sy - py);
    if (d <= afstand) { afstand = d; beste = i; }
  });
  return beste;
}

function raakDeel(px, py) {
  const pts = staat.profiel.punten;
  let beste = null, afstand = 8;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = naarScherm(...pts[i]), [bx, by] = naarScherm(...pts[i + 1]);
    const lx = bx - ax, ly = by - ay, l2 = lx * lx + ly * ly;
    const t = l2 ? Math.max(0, Math.min(1, ((px - ax) * lx + (py - ay) * ly) / l2)) : 0;
    const d = Math.hypot(px - (ax + t * lx), py - (ay + t * ly));
    if (d < afstand) { afstand = d; beste = { i, t }; }
  }
  return beste;
}

function muispositie(e) {
  const r = canvas.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}

canvas.addEventListener("contextmenu", (e) => e.preventDefault());

canvas.addEventListener("pointerdown", (e) => {
  if (!staat.profiel) return;
  const [px, py] = muispositie(e);
  const i = raakPunt(px, py);
  canvas.setPointerCapture(e.pointerId);
  if (i !== null && e.button !== 1) {
    selecteer(i);
    const richting = e.shiftKey ? "xz" : e.button === 2 ? "z" : "x";
    sleep = { soort: "punt", i, richting, start: kloon(staat.profiel), bewogen: false };
  } else {
    sleep = { soort: "pan", px, py, beeld: { ...staat.beeld } };
    canvas.style.cursor = "grabbing";
  }
});

canvas.addEventListener("pointermove", (e) => {
  if (!staat.profiel) return;
  const [px, py] = muispositie(e);
  const [wx, wz] = naarWereld(px, py);
  $("#cursorpos").textContent = `x = ${wx.toFixed(2)} m   z = ${wz.toFixed(2)} m+NAP`;

  if (!sleep) {
    canvas.style.cursor = raakPunt(px, py) !== null ? "pointer" : raakDeel(px, py) ? "copy" : "default";
    return;
  }
  if (sleep.soort === "pan") {
    const { w, h } = afmeting(), b = sleep.beeld;
    const ddx = ((px - sleep.px) / (w - MARGE.l - MARGE.r)) * (b.x1 - b.x0);
    const ddz = ((py - sleep.py) / (h - MARGE.t - MARGE.b)) * (b.z1 - b.z0);
    staat.beeld = { x0: b.x0 - ddx, x1: b.x1 - ddx, z0: b.z0 + ddz, z1: b.z1 + ddz };
    teken();
    return;
  }
  const punt = staat.profiel.punten[sleep.i];
  if (sleep.richting.includes("x")) punt[0] = afronden(wx);
  if (sleep.richting.includes("z")) punt[1] = afronden(wz);
  sleep.bewogen = true;
  $("#cursorpos").textContent = `${puntLabel(sleep.i)} sleept (${sleep.richting}): x = ${fmt(punt[0])}  z = ${fmt(punt[1])}`;
  gewijzigd({ historie: false, tabel: false });
  vulPuntvelden();
});

canvas.addEventListener("pointerup", () => {
  if (sleep?.soort === "punt" && sleep.bewogen) {
    staat.historie.push(sleep.start);
    staat.toekomst = [];
    gewijzigd({ historie: false });
  }
  sleep = null;
  canvas.style.cursor = "default";
});

canvas.addEventListener("dblclick", (e) => {
  if (!staat.profiel) return;
  const [px, py] = muispositie(e);
  if (raakPunt(px, py) !== null) return;
  const deel = raakDeel(px, py);
  if (!deel) return;
  const a = staat.profiel.punten[deel.i], b = staat.profiel.punten[deel.i + 1];
  voegPuntIn(deel.i + 1, [afronden(a[0] + deel.t * (b[0] - a[0])), afronden(a[1] + deel.t * (b[1] - a[1])), a[2]]);
});

canvas.addEventListener("wheel", (e) => {
  if (!staat.profiel) return;
  e.preventDefault();
  const f = e.deltaY > 0 ? 1.15 : 1 / 1.15;
  const [px, py] = muispositie(e);
  zoom(e.ctrlKey ? 1 : f, e.shiftKey ? 1 : f, px, py);
}, { passive: false });

new ResizeObserver(() => teken()).observe($("#grafiek-vak"));

// ── Bewerkingen ───────────────────────────────────────────────────────────────
function bewaarHistorie() {
  staat.historie.push(kloon(staat.profiel));
  if (staat.historie.length > 200) staat.historie.shift();
  staat.toekomst = [];
}

/** Na elke wijziging: tekenen, panelen bijwerken en (vertraagd) controleren. */
function gewijzigd({ historie = false, tabel = true } = {}) {
  if (historie) bewaarHistorie();
  if (staat.selectie !== null && staat.selectie >= staat.profiel.punten.length) {
    staat.selectie = staat.profiel.punten.length - 1;
  }
  teken();
  if (tabel) { vulTabel(); vulPuntvelden(); }
  else werkTabelWaardenBij();
  werkKnoppenBij();
  planCheck();
}

function selecteer(i) {
  staat.selectie = i;
  vulPuntvelden();
  document.querySelectorAll("#tabel-punten tbody tr").forEach((tr, j) => tr.classList.toggle("actief", j === i));
  document.querySelector("#tabel-punten tbody tr.actief")?.scrollIntoView({ block: "nearest" });
  werkKnoppenBij();
  teken();
}

function voegPuntIn(index, punt) {
  bewaarHistorie();
  const p = staat.profiel;
  p.punten.splice(index, 0, punt);
  // Een punt tussen twee voorlandpunten (vóór de teen) hoort bij het voorland
  if (p.voorland > 0 && index <= p.voorland - 1) p.voorland += 1;
  staat.selectie = index;
  gewijzigd();
  if (!inBeeld(punt)) passend();
}

function puntToevoegen() {
  const p = staat.profiel;
  if (!p) return;
  const i = staat.selectie ?? p.punten.length - 1;
  if (!p.punten.length) return voegPuntIn(0, [0, 0, 1]);
  const a = p.punten[i], b = p.punten[i + 1];
  const nieuw = b ? [afronden((a[0] + b[0]) / 2), afronden((a[1] + b[1]) / 2), a[2]] : [afronden(a[0] + 2), afronden(a[1] + 0.5), a[2]];
  voegPuntIn(i + 1, nieuw);
}

function voorlandpuntToevoegen() {
  const p = staat.profiel;
  if (!p || !p.punten.length) return;
  bewaarHistorie();
  const eerste = p.punten[0];
  p.punten.unshift([afronden(eerste[0] - 20), eerste[1], eerste[2]]);
  p.voorland = p.voorland > 0 ? p.voorland + 1 : 2;
  staat.selectie = 0;
  gewijzigd();
  if (!inBeeld(p.punten[0])) passend();
}

function inBeeld([x, z]) {
  const b = staat.beeld;
  return b && x >= b.x0 && x <= b.x1 && z >= b.z0 && z <= b.z1;
}

function puntVerwijderen() {
  const p = staat.profiel, i = staat.selectie;
  if (!p || i === null || p.punten.length <= 1) return;
  bewaarHistorie();
  p.punten.splice(i, 1);
  if (i < p.voorland) p.voorland -= 1;
  if (p.voorland === 1) p.voorland = 0;   // alleen nog de teen: geen voorland
  staat.selectie = Math.min(i, p.punten.length - 1);
  gewijzigd();
}

function teenHier() {
  const p = staat.profiel, i = staat.selectie;
  if (!p || i === null) return;
  bewaarHistorie();
  p.voorland = i === 0 ? 0 : i + 1;
  gewijzigd();
}

function zetVoorland(n) {
  const p = staat.profiel;
  n = Math.max(0, Math.min(Math.round(n) || 0, p.punten.length));
  if (n === 1) n = p.voorland >= 2 ? 0 : 2;
  if (n > p.punten.length) n = 0;
  if (n === p.voorland) return vulMeta();
  bewaarHistorie();
  p.voorland = n;
  gewijzigd();
  vulMeta();
}

function herstelOrigineel() {
  if (!staat.data) return;
  bewaarHistorie();
  staat.profiel = kloon(staat.data.origineel);
  staat.selectie = 0;
  gewijzigd();
  vulMeta();
  toast("Origineel profiel teruggezet (Ctrl+Z om terug te gaan)");
}

function ongedaanMaken() {
  if (!staat.historie.length) return;
  staat.toekomst.push(kloon(staat.profiel));
  staat.profiel = staat.historie.pop();
  gewijzigd();
  vulMeta();
}

function opnieuw() {
  if (!staat.toekomst.length) return;
  staat.historie.push(kloon(staat.profiel));
  staat.profiel = staat.toekomst.pop();
  gewijzigd();
  vulMeta();
}

function verschuif(dx, dz) {
  const p = staat.profiel, i = staat.selectie;
  if (!p || i === null) return;
  bewaarHistorie();
  p.punten[i][0] = afronden(p.punten[i][0] + dx);
  p.punten[i][1] = afronden(p.punten[i][1] + dz);
  gewijzigd();
}

// ── Panelen ───────────────────────────────────────────────────────────────────
function vulPuntvelden() {
  const p = staat.profiel, i = staat.selectie;
  const punt = p && i !== null ? p.punten[i] : null;
  for (const [id, k] of [["#punt-x", 0], ["#punt-z", 1], ["#punt-r", 2]]) {
    const el = $(id);
    el.disabled = !punt;
    if (document.activeElement !== el) el.value = punt ? fmt(punt[k]) : "";
  }
  $("#punt-naam").textContent = punt ? puntLabel(i) + (i === teenIndex() && p.voorland > 0 ? " (teen)" : "") : "";
}

function vulTabel() {
  const p = staat.profiel, tbody = $("#tabel-punten tbody");
  if (!p) { tbody.innerHTML = ""; return; }
  const delen = profieldelen(p);
  tbody.innerHTML = p.punten.map((pt, i) => {
    const d = delen[i];
    const helling = d ? `<span class="${d.soort}" title="${escapeHtml(d.reden || d.soort)}">${hellingTekst(d.helling)}</span>` : "";
    return `<tr data-i="${i}" class="${i === staat.selectie ? "actief" : ""}">
      <td class="lbl ${isVoorlandPunt(i) ? "voorland" : "dijk"}">${puntLabel(i)}${i === teenIndex() && p.voorland > 0 ? " ◆" : ""}</td>
      <td><input type="number" step="0.01" data-k="0" value="${fmt(pt[0])}"></td>
      <td><input type="number" step="0.01" data-k="1" value="${fmt(pt[1])}"></td>
      <td><input type="number" step="0.05" data-k="2" value="${fmt(pt[2], 2)}"></td>
      <td class="helling">${helling}</td></tr>`;
  }).join("");
}

/** Tijdens slepen alleen de waarden bijwerken (geen nieuwe tabel, dan blijft de focus staan). */
function werkTabelWaardenBij() {
  const p = staat.profiel, rijen = document.querySelectorAll("#tabel-punten tbody tr");
  if (rijen.length !== p.punten.length) return vulTabel();
  const delen = profieldelen(p);
  rijen.forEach((tr, i) => {
    tr.querySelectorAll("input").forEach((el) => {
      if (document.activeElement !== el) el.value = fmt(p.punten[i][+el.dataset.k], el.dataset.k === "2" ? 2 : 3);
    });
    const d = delen[i], cel = tr.querySelector(".helling");
    cel.innerHTML = d ? `<span class="${d.soort}" title="${escapeHtml(d.reden || d.soort)}">${hellingTekst(d.helling)}</span>` : "";
  });
}

function vulMeta() {
  const p = staat.profiel;
  const velden = { "#m-id": p?.id, "#m-kruinhoogte": fmt(p?.kruinhoogte), "#m-richting": fmt(p?.richting, 2),
    "#m-voorland": p?.voorland, "#m-damtype": p?.damtype, "#m-damhoogte": fmt(p?.damhoogte), "#m-damwand": p?.damwand,
    "#m-memo": p?.memo };
  for (const [id, v] of Object.entries(velden)) {
    const el = $(id);
    el.disabled = !p;
    if (document.activeElement !== el) el.value = v ?? "";
  }
}

function vulVakInfo() {
  const vak = staat.overzicht?.vakken[staat.vakIndex];
  const regels = [];
  const herkomst = (k) => (vak.bron?.[k] === "bestandsnaam" ? `${vak[k]} (uit bestandsnaam)` : vak[k] ?? "onbekend");
  if (vak) regels.push(["Traject", herkomst("traject")], ["Dijkvak", herkomst("dijkvak")]);
  if (vak?.vak_id) regels.push(["Vak-ID", vak.vak_id]);
  if (vak && staat.overzicht?.koppeltabel && !vak.in_koppeltabel) regels.push(["Koppeltabel", "staat er niet in"]);
  if (vak?.vak_id && staat.profiel && staat.profiel.id !== vak.vak_id) regels.push(["Let op", `ID in het profiel is ${staat.profiel.id}`]);
  if (staat.data) regels.push(["Origineel", staat.data.bestand]);
  if (staat.data?.versie) regels.push(["Geopend", `${staat.data.geladen}${staat.data.versie.dubbel
    ? " (dubbele naam)" : ` (achtervoegsel "${staat.data.versie.achtervoegsel}")`}`]);
  if (!vak?.bestaat && vak?.reden) regels.push(["Profiel", vak.reden]);
  for (const [k, v] of Object.entries(vak?.info || {})) regels.push([k, v]);
  $("#vak-info").innerHTML = regels.length
    ? `<dl class="vak-info">${regels.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`).join("")}</dl>` : "";
}

function werkKnoppenBij() {
  const p = staat.profiel, i = staat.selectie;
  $("#btn-undo").disabled = !staat.historie.length;
  $("#btn-redo").disabled = !staat.toekomst.length;
  for (const id of ["#btn-toevoegen", "#btn-voorland", "#btn-herstel", "#btn-passend", "#btn-opslaan", "#btn-download", "#btn-voorbeeld"]) {
    $(id).disabled = !p;
  }
  $("#btn-verwijderen").disabled = !p || i === null || p.punten.length <= 1;
  $("#btn-teen").disabled = !p || i === null || i === teenIndex() && p.voorland > 0 || (i === 0 && p.voorland === 0);
  const vuil = isGewijzigd();
  $("#kop-gewijzigd").hidden = !vuil;
  document.title = (vuil ? "● " : "") + "Profieleditor" + (staat.data ? ` – ${staat.data.bestand}` : "");
}

const isGewijzigd = () => !!staat.profiel && JSON.stringify(staat.profiel) !== staat.opgeslagenJson;

// ── Profielcheck ──────────────────────────────────────────────────────────────
let checkTimer = null, checkVolgnummer = 0;
function planCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(voerCheckUit, 120);
}

async function voerCheckUit() {
  if (!staat.profiel) return;
  const nummer = ++checkVolgnummer;
  try {
    const res = await api("/api/check", staat.profiel);
    if (nummer === checkVolgnummer) toonCheck(res);
  } catch (e) {
    if (nummer === checkVolgnummer) toonCheck({ ok: false, code: -1, naam: "FOUT", omschrijving: e.message });
  }
}

function toonCheck(res) {
  staat.check = res;
  const badge = $("#check-badge"), tekst = $("#check-tekst");
  if (!res) {
    badge.className = "check-badge"; badge.textContent = "–";
    tekst.className = "check-tekst gedempt"; tekst.textContent = "–";
    return;
  }
  badge.className = "check-badge " + (res.ok ? "ok" : "fout");
  badge.textContent = res.ok ? "✓ Profiel is ok" : `✗ ${res.naam}`;
  badge.title = res.omschrijving;
  tekst.className = "check-tekst " + (res.ok ? "ok" : "fout");
  tekst.innerHTML = `<b>${res.ok ? "✓" : "✗"} ${escapeHtml(res.naam)}</b> – ${escapeHtml(res.omschrijving)}`;
}

// ── Lijst met dijkvakken ──────────────────────────────────────────────────────
const ONBEKEND = "\u0000onbekend";   // waarde van het trajectfilter voor profielen zonder bekend traject

function vakZichtbaar(vak) {
  const zoek = $("#zoek").value.trim().toLowerCase();
  const tekst = `${vak.vak_id ?? ""} ${vak.traject ?? ""} ${vak.dijkvak ?? ""} ${vak.bestand ?? ""} ${(vak.versies || []).map((v) => v.naam).join(" ")} ${Object.values(vak.info || {}).join(" ")}`;
  if (zoek && !tekst.toLowerCase().includes(zoek)) return false;
  const traject = $("#filter-traject").value;
  if (traject && (vak.traject ?? ONBEKEND) !== traject) return false;
  switch (staat.filter) {
    case "fout": return !vak.bestaat || !vak.check?.ok;
    case "aangepast": return !!vak.aangepast;
    case "open": return vak.bestaat && !vak.aangepast;
    default: return true;
  }
}

/** Zichtbare vakken, gegroepeerd per traject (in volgorde van eerste voorkomen; onbekend traject als laatste). */
function zichtbareIndices() {
  const vakken = staat.overzicht?.vakken || [], groepen = new Map();
  vakken.forEach((v, i) => {
    if (!vakZichtbaar(v)) return;
    const groep = v.traject ?? ONBEKEND;
    if (!groepen.has(groep)) groepen.set(groep, []);
    groepen.get(groep).push(i);
  });
  const onbekend = groepen.get(ONBEKEND) || [];
  groepen.delete(ONBEKEND);
  return [...[...groepen.values()].flat(), ...onbekend];
}

/** Naam in de lijst: {traject}_{dijkvak} als beide bekend zijn, anders wat bekend is, anders de bestandsnaam. */
function vakNaam(v) {
  if (v.vak_id) return v.vak_id;
  if (v.dijkvak) return `dijkvak ${v.dijkvak}`;
  return v.bestand ?? "(geen profiel)";
}

function bronTekst(v) {
  const uitNaam = ["traject", "dijkvak"].filter((k) => v.bron?.[k] === "bestandsnaam");
  const onbekend = ["traject", "dijkvak"].filter((k) => !v[k]);
  const delen = [];
  if (uitNaam.length) delen.push(`${uitNaam.join(" en ")} uit de bestandsnaam`);
  if (onbekend.length) delen.push(`${onbekend.join(" en ")} onbekend`);
  return delen.join("; ");
}

function vulLijst() {
  const ul = $("#vakken"), vakken = staat.overzicht?.vakken || [];
  const indices = zichtbareIndices();
  const heeftKoppeling = !!staat.overzicht?.koppeltabel;
  const heeftTrajecten = vakken.some((v) => v.traject);
  let html = "", vorigKopje = null;
  for (const i of indices) {
    const v = vakken[i];
    const kopje = heeftTrajecten ? (v.traject ? `Traject ${v.traject}` : "Traject onbekend") : null;
    if (kopje && kopje !== vorigKopje) html += `<li class="kopje">${escapeHtml(kopje)}</li>`;
    vorigKopje = kopje;

    const versies = v.versies || [];
    const tags = [];
    if (versies.length > 1) tags.push(`<span class="tag-klein aangepast" title="${escapeHtml(versies.map((x) => x.naam).join("\n"))}">${versies.length} VERSIES</span>`);
    else if (versies.length) tags.push(`<span class="tag-klein aangepast" title="${escapeHtml(versies[0].naam)}">AANGEPAST</span>`);
    if (v.ahn_waarschuwingen?.length) tags.push(`<span class="tag-klein waarschuwing" title="${escapeHtml(v.ahn_waarschuwingen.join("\n"))}">AHN ≠</span>`);
    if (versies.some((x) => x.dubbel)) tags.push(`<span class="tag-klein waarschuwing" title="Een bestand in de uitvoermap heeft precies dezelfde naam als het origineel">DUBBELE NAAM</span>`);

    const regels = [];
    if (v.vak_id || v.dijkvak) regels.push(escapeHtml(v.bestand ?? (v.bestaat ? "" : "(geen profiel)")));
    if (v.vak_id && v.profiel_id && v.profiel_id !== v.vak_id) {
      regels.push(`<span class="id-afwijkend" title="ID in het profiel (${escapeHtml(v.profiel_id)}) wijkt af van ${escapeHtml(v.vak_id)}">ID ≠</span>`);
    }
    if (heeftKoppeling && !v.in_koppeltabel) regels.push(`<span class="gedempt">niet in koppeltabel</span>`);
    const bron = bronTekst(v);
    if (bron && v.bestaat && v.vak_id) regels.push(`<span class="gedempt" title="${escapeHtml(bron)}">uit naam</span>`);

    const stip = !v.bestaat ? "ontbreekt" : v.check?.ok ? "ok" : "fout";
    const code = !v.bestaat ? "ontbreekt" : v.check?.ok ? "ok" : v.check?.code;
    const ahnTekst = staat.overzicht?.ahn && v.bestaat ? `AHN-lijnen: ${v.ahn ?? 0}` : "";
    const titel = [!v.bestaat ? v.reden ?? "Profiel niet gevonden" : v.check?.omschrijving ?? "", bron, ahnTekst]
      .filter(Boolean).join("\n");
    html += `<li class="vak ${i === staat.vakIndex ? "actief" : ""}" data-i="${i}" title="${escapeHtml(titel)}">
      <span class="stip ${stip}"></span>
      <span class="namen"><div class="naam">${escapeHtml(vakNaam(v))}${tags.join("")}</div>
      ${regels.length ? `<div class="bestand">${regels.join(" · ")}</div>` : ""}</span>
      <span class="code ${stip === "ok" ? "" : "fout"}">${escapeHtml(code ?? "")}</span></li>`;
  }
  ul.innerHTML = html || `<li class="kopje">Geen profielen</li>`;
  const totaal = vakken.length, fouten = vakken.filter((v) => !v.bestaat || !v.check?.ok).length;
  const aangepast = vakken.filter((v) => v.aangepast).length;
  $("#lijst-teller").textContent = totaal
    ? `${indices.length} van ${totaal} · ${fouten} met fout · ${aangepast} aangepast` : "";
  ul.querySelector(".vak.actief")?.scrollIntoView({ block: "nearest" });
}

$("#vakken").addEventListener("click", (e) => {
  const li = e.target.closest(".vak");
  if (li) kiesVak(+li.dataset.i);
});
$("#zoek").addEventListener("input", vulLijst);
$("#filter-traject").addEventListener("change", vulLijst);

function kopNaam(vak) {
  const traject = vak.traject ? `Traject ${vak.traject}` : "Traject onbekend";
  const dijkvak = vak.dijkvak ? `dijkvak ${vak.dijkvak}` : "dijkvak onbekend";
  return `${traject} · ${dijkvak}`;
}

function vulTrajectfilter() {
  const select = $("#filter-traject"), huidig = select.value, vakken = staat.overzicht?.vakken || [];
  const trajecten = [...new Set(vakken.map((v) => v.traject).filter(Boolean))];
  const metOnbekend = trajecten.length && vakken.some((v) => !v.traject);
  select.hidden = trajecten.length + (metOnbekend ? 1 : 0) < 2;
  select.innerHTML = `<option value="">Alle trajecten (${trajecten.length})</option>`
    + trajecten.map((t) => `<option value="${escapeHtml(t)}">Traject ${escapeHtml(t)}</option>`).join("")
    + (metOnbekend ? `<option value="${ONBEKEND}">Traject onbekend</option>` : "");
  select.value = [...select.options].some((o) => o.value === huidig) ? huidig : "";
}
document.querySelectorAll(".filter").forEach((knop) => knop.addEventListener("click", () => {
  document.querySelectorAll(".filter").forEach((k) => k.classList.toggle("actief", k === knop));
  staat.filter = knop.dataset.filter;
  vulLijst();
}));

function stap(richting) {
  const indices = zichtbareIndices();
  if (!indices.length) return;
  const pos = indices.indexOf(staat.vakIndex);
  const nieuw = pos < 0 ? indices[0] : indices[Math.max(0, Math.min(indices.length - 1, pos + richting))];
  if (nieuw !== staat.vakIndex) kiesVak(nieuw);
}

let laadVolgnummer = 0;   // alleen het antwoord op de laatst gekozen vak wordt getoond
async function kiesVak(i, { bron = "auto", vraag = true } = {}) {
  const vak = staat.overzicht.vakken[i];
  if (vraag && isGewijzigd() && !confirm("Het huidige profiel heeft niet-opgeslagen wijzigingen. Toch doorgaan?")) return;
  const nummer = ++laadVolgnummer;
  staat.vakIndex = i;
  vulLijst();
  if (!vak.bestaat) {
    staat.data = null; staat.profiel = null; staat.selectie = null; staat.ahn = null; toonAhnMelding();
    $("#kop-dijkvak").textContent = kopNaam(vak);
    $("#kop-bestand").textContent = vak.bestand ? `${vak.reden}: ${vak.bestand}` : vak.reden;
    $("#kies-versie").hidden = true;
    toonCheck(null); vulTabel(); vulPuntvelden(); vulMeta(); vulVakInfo(); werkKnoppenBij(); teken();
    return;
  }
  try {
    const data = await api(`/api/profiel?bestand=${encodeURIComponent(vak.bestand)}&bron=${encodeURIComponent(bron)}`);
    if (nummer !== laadVolgnummer) return;   // intussen een ander vak gekozen
    laadProfiel(data, vak);
    history.replaceState(null, "", `#${encodeURIComponent(vak.bestand)}`);
  } catch (e) {
    if (nummer === laadVolgnummer) toast(`Laden mislukt: ${e.message}`, 5000);
  }
}

function laadProfiel(data, vak) {
  staat.data = data;
  staat.profiel = kloon(data.profiel);
  staat.opgeslagenJson = JSON.stringify(staat.profiel);
  staat.historie = []; staat.toekomst = [];
  staat.selectie = staat.profiel.punten.length ? 0 : null;
  $("#kop-dijkvak").textContent = kopNaam(vak);
  $("#kop-bestand").textContent = data.is_aangepast ? `Origineel: ${data.bestand}` : data.geladen;
  vulVersiekeuze();
  $("#opslaan-naam").value = data.uitvoernaam;
  $("#opslaan-map").textContent = staat.overzicht.doelmap;
  $("#geladen-uit").textContent = data.is_aangepast
    ? `Geladen: aangepaste versie ${data.geladen}. Origineel: ${data.bestand}.`
    : `Geladen: origineel ${data.bestand}.`;
  $("#opslaan-melding").hidden = true;
  if (data.profiel.invoerfouten?.length) toast(`Leesproblemen: ${data.profiel.invoerfouten.join("; ")}`, 6000);
  toonCheck(data.check);
  vulTabel(); vulPuntvelden(); vulMeta(); vulVakInfo(); werkKnoppenBij();
  passend();
  laadAhn(data.bestand);
}

/** AHN-lijnen van een profiel ophalen en tonen (als er een shapefile is ingesteld). */
async function laadAhn(bestand) {
  staat.ahn = null;
  toonAhnMelding();
  if (!staat.overzicht?.ahn) { tekenLegenda(); teken(); return; }
  try {
    const res = await api(`/api/ahn?bestand=${encodeURIComponent(bestand)}`);
    if (staat.data?.bestand !== bestand) return;   // intussen een ander profiel gekozen
    staat.ahn = res;
  } catch (e) {
    staat.ahn = { lijnen: [], melding: `AHN laden mislukt: ${e.message}`, waarschuwingen: [] };
  }
  toonAhnMelding(); tekenLegenda(); teken();
}

function toonAhnMelding() {
  const el = $("#ahn-melding"), ahn = staat.ahn;
  const heeftShape = !!staat.overzicht?.ahn;
  $("#schakel-ahn").hidden = !heeftShape;
  $("#schakel-spiegel").hidden = !heeftShape;
  $("#spiegel-ahn").checked = staat.spiegel.has(staat.data?.bestand);
  const regels = [];
  if (ahn && $("#toon-ahn").checked) {
    if (ahn.melding) regels.push(`<div>${escapeHtml(ahn.melding)}</div>`);
    for (const w of ahn.waarschuwingen || []) regels.push(`<div class="waarschuwing">⚠ ${escapeHtml(w)}</div>`);
  }
  el.innerHTML = regels.join("");
  el.hidden = !regels.length;
}

function toonAhnStatus() {
  const el = $("#ahn-status"), info = staat.overzicht?.ahn;
  el.hidden = !info;
  if (!info) return;
  el.className = "klein ahn-status" + (info.fout || info.niet_gekoppeld ? " waarschuwing" : "");
  el.textContent = info.fout ? `AHN: ${info.fout}` : `AHN: ${info.samenvatting}`;
}

/** Keuzelijst met de aangepaste versies en het origineel; verborgen als er geen aangepaste versie is. */
function vulVersiekeuze() {
  const select = $("#kies-versie"), data = staat.data;
  const versies = data?.versies || [];
  select.hidden = !versies.length;
  if (!versies.length) return;
  const datum = (v) => (v.gewijzigd ? ` · ${v.gewijzigd.replace("T", " ").slice(0, 16)}` : "");
  select.innerHTML = versies.map((v) => `<option value="${escapeHtml(v.naam)}">${escapeHtml(v.naam)}${v.dubbel
    ? " · dubbele naam" : ""}${datum(v)}</option>`).join("")
    + `<option value="origineel">Origineel: ${escapeHtml(data.bestand)}</option>`;
  select.value = data.versie?.naam ?? "origineel";
}

$("#kies-versie").addEventListener("change", (e) => {
  if (isGewijzigd() && !confirm("Het huidige profiel heeft niet-opgeslagen wijzigingen. Toch doorgaan?")) {
    vulVersiekeuze();
    return;
  }
  kiesVak(staat.vakIndex, { bron: e.target.value, vraag: false });
});

/** Overzicht opnieuw ophalen (na opslaan) zonder het geopende profiel opnieuw te laden. */
async function vernieuwOverzicht() {
  const bestand = staat.data?.bestand;
  try {
    staat.overzicht = await api("/api/overzicht");
  } catch (e) {
    toast(`Overzicht bijwerken mislukt: ${e.message}`, 5000);
    return;
  }
  staat.vakIndex = staat.overzicht.vakken.findIndex((v) => v.bestand === bestand);
  const vak = staat.overzicht.vakken[staat.vakIndex];
  if (vak && staat.data) staat.data.versies = vak.versies;
  vulTrajectfilter(); toonAhnStatus(); vulLijst(); vulVersiekeuze();
}

async function laadOverzicht({ behoud = true } = {}) {
  const huidig = staat.data?.bestand ?? decodeURIComponent(location.hash.slice(1));
  try {
    staat.overzicht = await api("/api/overzicht");
  } catch (e) {
    staat.overzicht = { vakken: [] };
    vulLijst();
    toast(`Overzicht laden mislukt: ${e.message}`, 6000);
    return;
  }
  const vakken = staat.overzicht.vakken;
  let i = behoud && huidig ? vakken.findIndex((v) => v.bestand === huidig) : -1;
  if (i < 0) i = vakken.findIndex((v) => v.bestaat);
  staat.vakIndex = -1;
  vulTrajectfilter();
  toonAhnStatus();
  vulLijst();
  if (i >= 0) await kiesVak(i, { vraag: false });
  else { staat.data = null; staat.profiel = null; teken(); }
}

// ── Opslaan ───────────────────────────────────────────────────────────────────
async function opslaan(overschrijven = false) {
  if (!staat.profiel) return;
  const melding = $("#opslaan-melding");
  const verzoek = { profiel: staat.profiel, bestandsnaam: $("#opslaan-naam").value.trim(),
    versie: +$("#opslaan-versie").value, overschrijven };
  // De toestand zoals verstuurd: wijzigingen tijdens het opslaan blijven als niet-opgeslagen gemarkeerd
  const verstuurd = JSON.stringify(staat.profiel), data = staat.data;
  try {
    const res = await api("/api/opslaan", verzoek);
    if (res.bestaat) {
      if (confirm(`${res.pad} bestaat al. Overschrijven?`)) return opslaan(true);
      return;
    }
    if (staat.data !== data) {   // intussen een ander profiel geopend
      toast(`Opgeslagen: ${res.pad}`);
      await vernieuwOverzicht();
      return;
    }
    staat.opgeslagenJson = verstuurd;
    melding.hidden = false;
    melding.className = "melding " + (res.check.ok ? "ok" : "fout");
    melding.textContent = `Opgeslagen: ${res.pad}` + (res.check.ok ? "" : ` – let op: ${res.check.naam}`);
    toast("Profiel opgeslagen");
    await vernieuwOverzicht();
    const versie = (staat.data.versies || []).find((v) => v.naam === verzoek.bestandsnaam);
    if (versie) {
      Object.assign(staat.data, { versie, is_aangepast: true, geladen: versie.naam, uitvoernaam: versie.naam });
      vulVersiekeuze(); vulVakInfo();
      $("#kop-bestand").textContent = `Origineel: ${staat.data.bestand}`;
    } else {
      toast(`Opgeslagen, maar ${verzoek.bestandsnaam} wordt niet herkend als versie van ${staat.data.bestand}`, 6000);
    }
    werkKnoppenBij();
  } catch (e) {
    melding.hidden = false;
    melding.className = "melding fout";
    melding.textContent = `Opslaan mislukt: ${e.message}`;
  }
}

async function prflTekst() {
  return (await api("/api/tekst", { profiel: staat.profiel, versie: +$("#opslaan-versie").value })).tekst;
}

async function download() {
  try {
    const tekst = await prflTekst();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([tekst], { type: "text/plain;charset=utf-8" }));
    a.download = $("#opslaan-naam").value.trim() || "profiel.prfl";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast(`Download mislukt: ${e.message}`, 5000); }
}

async function voorbeeld() {
  try {
    $("#voorbeeld-titel").textContent = `${$("#opslaan-naam").value} (versie ${$("#opslaan-versie").value})`;
    $("#voorbeeld-tekst").textContent = await prflTekst();
    $("#dlg-voorbeeld").showModal();
  } catch (e) { toast(e.message, 5000); }
}

// ── Instellingen ──────────────────────────────────────────────────────────────
const dlgInstellingen = $("#dlg-instellingen");
const formInstellingen = $("#form-instellingen");

function openInstellingen() {
  for (const [k, v] of Object.entries(staat.instellingen || {})) {
    if (formInstellingen.elements[k]) formInstellingen.elements[k].value = v ?? "";
  }
  $("#instellingen-fout").hidden = true;
  const ini = staat.instellingen?.ini;
  $("#instellingen-ini").textContent = ini
    ? `Wijzigingen worden bewaard in ${ini}.`
    : "Er is geen .ini-bestand opgegeven: wijzigingen gelden alleen tot de server stopt.";
  const ahn = staat.overzicht?.ahn;
  $("#ahn-velden").textContent = ahn?.velden
    ? `Kolommen in de shapefile: ${ahn.velden.join(", ")}. Nu gebruikt: ${Object.entries(ahn.kolommen)
      .map(([doel, kolom]) => `${doel} = ${kolom ?? "–"}`).join(", ")}. Waarden worden exact vergeleken.`
    : ahn?.fout ? `AHN: ${ahn.fout}` : "";
  dlgInstellingen.showModal();
}

formInstellingen.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isGewijzigd() && !confirm("Het huidige profiel heeft niet-opgeslagen wijzigingen. Toch doorgaan?")) return;
  const data = Object.fromEntries(new FormData(formInstellingen));
  data.versie = +data.versie;
  try {
    staat.instellingen = await api("/api/instellingen", data);
    $("#opslaan-versie").value = staat.instellingen.versie;
    dlgInstellingen.close();
    staat.opgeslagenJson = JSON.stringify(staat.profiel);
    await laadOverzicht({ behoud: false });
  } catch (err) {
    const el = $("#instellingen-fout");
    el.hidden = false;
    el.textContent = err.message;
  }
});
$("#btn-instellingen-annuleer").addEventListener("click", () => dlgInstellingen.close());
formInstellingen.querySelectorAll("[data-kies]").forEach((knop) => knop.addEventListener("click", async () => {
  const veld = formInstellingen.elements[knop.dataset.veld];
  knop.disabled = true;
  try {
    const { pad } = await api(`/api/kies?soort=${knop.dataset.kies}&start=${encodeURIComponent(veld.value)}`);
    if (pad) veld.value = pad;
  } catch (e) { toast(e.message, 5000); }
  finally { knop.disabled = false; }
}));

// ── Invoervelden ──────────────────────────────────────────────────────────────
function getal(waarde) {
  const v = parseFloat(String(waarde).replace(",", "."));
  return Number.isFinite(v) ? v : null;
}

[["#punt-x", 0], ["#punt-z", 1], ["#punt-r", 2]].forEach(([id, k]) => {
  $(id).addEventListener("change", (e) => {
    const v = getal(e.target.value), i = staat.selectie;
    if (v === null || i === null) return vulPuntvelden();
    bewaarHistorie();
    staat.profiel.punten[i][k] = afronden(v);
    gewijzigd();
  });
});

$("#tabel-punten").addEventListener("change", (e) => {
  const el = e.target, tr = el.closest("tr");
  if (!el.dataset.k || !tr) return;
  const v = getal(el.value), i = +tr.dataset.i;
  if (v === null) return vulTabel();
  bewaarHistorie();
  staat.profiel.punten[i][+el.dataset.k] = afronden(v);
  staat.selectie = i;
  gewijzigd({ tabel: false });
  vulPuntvelden();
});
$("#tabel-punten").addEventListener("focusin", (e) => {
  const tr = e.target.closest("tr");
  if (tr && +tr.dataset.i !== staat.selectie) selecteer(+tr.dataset.i);
});
$("#tabel-punten").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-i]");
  if (tr) selecteer(+tr.dataset.i);
});

const metaVelden = { "#m-id": "id", "#m-kruinhoogte": "kruinhoogte", "#m-richting": "richting",
  "#m-damtype": "damtype", "#m-damhoogte": "damhoogte", "#m-damwand": "damwand", "#m-memo": "memo" };
for (const [id, sleutel] of Object.entries(metaVelden)) {
  $(id).addEventListener("change", (e) => {
    if (!staat.profiel) return;
    let v = e.target.value;
    if (["kruinhoogte", "richting", "damhoogte"].includes(sleutel)) v = getal(v);
    if (["damtype", "damwand"].includes(sleutel)) v = +v;
    bewaarHistorie();
    staat.profiel[sleutel] = v;
    gewijzigd({ tabel: false });
  });
}
$("#m-voorland").addEventListener("change", (e) => zetVoorland(+e.target.value));

// ── Knoppen en sneltoetsen ────────────────────────────────────────────────────
$("#btn-instellingen").addEventListener("click", openInstellingen);
$("#btn-vorige").addEventListener("click", () => stap(-1));
$("#btn-volgende").addEventListener("click", () => stap(1));
$("#btn-undo").addEventListener("click", ongedaanMaken);
$("#btn-redo").addEventListener("click", opnieuw);
$("#btn-toevoegen").addEventListener("click", puntToevoegen);
$("#btn-voorland").addEventListener("click", voorlandpuntToevoegen);
$("#btn-verwijderen").addEventListener("click", puntVerwijderen);
$("#btn-teen").addEventListener("click", teenHier);
$("#btn-herstel").addEventListener("click", herstelOrigineel);
$("#btn-passend").addEventListener("click", passend);
$("#btn-opslaan").addEventListener("click", () => opslaan());
$("#btn-download").addEventListener("click", download);
$("#btn-voorbeeld").addEventListener("click", voorbeeld);
$("#toon-origineel").addEventListener("change", teken);
$("#toon-hellingen").addEventListener("change", teken);
$("#toon-ahn").addEventListener("change", () => { toonAhnMelding(); teken(); });
$("#spiegel-ahn").addEventListener("change", (e) => {
  const bestand = staat.data?.bestand;
  if (!bestand) return;
  if (e.target.checked) staat.spiegel.add(bestand); else staat.spiegel.delete(bestand);
  teken();
});

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("actief", t === tab));
  document.querySelectorAll(".tabblad").forEach((b) => (b.hidden = b.id !== `tab-${tab.dataset.tab}`));
}));

document.addEventListener("keydown", (e) => {
  const inInvoer = e.target.closest("input, textarea, select");
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === "s") { e.preventDefault(); opslaan(); return; }
  if (inInvoer || document.querySelector("dialog[open]")) return;
  if (ctrl && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? opnieuw() : ongedaanMaken(); return; }
  if (ctrl && e.key.toLowerCase() === "y") { e.preventDefault(); opnieuw(); return; }
  if (ctrl) return;
  const stapgrootte = e.shiftKey ? 0.1 : e.altKey ? 0.001 : 0.01;
  switch (e.key) {
    case "Delete": case "Backspace": puntVerwijderen(); break;
    case "Insert": case "+": puntToevoegen(); break;
    case "PageUp": stap(-1); break;
    case "PageDown": stap(1); break;
    case "f": case "F": passend(); break;
    case "ArrowLeft": verschuif(-stapgrootte, 0); break;
    case "ArrowRight": verschuif(stapgrootte, 0); break;
    case "ArrowUp": verschuif(0, stapgrootte); break;
    case "ArrowDown": verschuif(0, -stapgrootte); break;
    case "Tab":
      if (staat.profiel?.punten.length) {
        const n = staat.profiel.punten.length;
        selecteer(((staat.selectie ?? -1) + (e.shiftKey ? n - 1 : 1)) % n);
        break;
      }
      return;
    default: return;
  }
  e.preventDefault();
});

window.addEventListener("beforeunload", (e) => {
  if (isGewijzigd()) { e.preventDefault(); e.returnValue = ""; }
});

// ── Start ─────────────────────────────────────────────────────────────────────
(async function start() {
  leesKleuren();
  tekenLegenda();
  werkKnoppenBij(); vulPuntvelden(); vulMeta(); teken();
  try {
    staat.instellingen = await api("/api/instellingen");
  } catch (e) {
    toast(`Server niet bereikbaar: ${e.message}`, 8000);
    return;
  }
  $("#opslaan-versie").value = staat.instellingen.versie;
  if (!staat.instellingen.prfl_map) openInstellingen();
  else await laadOverzicht();
})();
