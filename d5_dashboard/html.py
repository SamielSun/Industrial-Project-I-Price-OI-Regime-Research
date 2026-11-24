"""D5 -- the interactive HTML shell: one file, payload embedded, no server."""

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px auto;max-width:1240px;color:#1a202c;font-variant-numeric:tabular-nums}
h1{font-size:21px;margin:0 0 2px}
h2{font-size:15px;margin:26px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px}
.sub{color:#4a5568;font-size:12.5px;margin-bottom:14px;line-height:1.7}
.bar{display:flex;align-items:center;gap:10px;margin:10px 0 4px;padding:10px 12px;background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px;flex-wrap:wrap}
.bar input,.bar select{font-size:13px;padding:4px 6px;border:1px solid #cbd5e0;border-radius:4px}
.bar button{font-size:13px;padding:4px 10px;border:1px solid #cbd5e0;background:#fff;border-radius:4px;cursor:pointer}
.bar button:hover{background:#edf2f7}
.bar .asof{margin-left:auto;font-size:12.5px;color:#4a5568}
.bar .asof b{color:#1a202c}
.bar .hint{font-size:11.5px;color:#a0aec0}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{padding:4px 9px;border-bottom:1px solid #edf2f7;text-align:right;white-space:nowrap}
th{background:#f7fafc;font-weight:600}
td.l,th.l{text-align:left}
.tag{font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:3px}
.r1{background:#c6f6d5;color:#22543d}
.r3{background:#fed7d7;color:#742a2a}
.r4{background:#e2e8f0;color:#2d3748}
.r2{background:#fefcbf;color:#744210}
.quiet{background:#f1f5f9;color:#94a3b8}
.na{background:#fff;color:#cbd5e0;border:1px dashed #e2e8f0}
.none{color:#a0aec0}
tr.quietrow td{color:#a0aec0}
.grid-h{display:grid;grid-template-columns:44px 1fr 76px 92px 92px 92px 80px;gap:0;padding:4px 9px;font-weight:600;background:#f7fafc;font-size:12px;border-bottom:1px solid #edf2f7}
.grid-h span{text-align:right;white-space:nowrap}
.grid-h span:nth-child(2){text-align:left}
details.row{border-bottom:1px solid #edf2f7}
details.row>summary{display:grid;grid-template-columns:44px 1fr 76px 92px 92px 92px 80px;padding:4px 9px;font-size:12px;cursor:pointer;list-style:none;align-items:center}
details.row>summary::-webkit-details-marker{display:none}
details.row>summary:hover{background:#f7fafc}
details.row>summary span{text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
details.row>summary span:nth-child(2){text-align:left}
.evtab{margin:2px 0 10px 48px;width:auto;font-size:11.5px}
.evtab td,.evtab th{padding:2px 10px}
footer{margin-top:34px;font-size:11px;color:#718096;line-height:1.7;border-top:1px solid #e2e8f0;padding-top:12px}
.legend{font-size:11.5px;color:#4a5568;margin:6px 0 0}
.legend span{display:inline-block;margin-right:12px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:-1px}
.banner{background:#fffbea;border:1px solid #f6e05e;color:#744210;padding:7px 12px;border-radius:6px;font-size:12.5px;margin:0 0 12px}
"""

JS = r"""
const I = {rank:0,sym:1,fund:2,vol:3,oi24:4,fp:5,bs:6,bpc:7,boc:8,v24:9,ratio:10};
const RN = ["R1","R2","R3","R4"];
const FNAME = ["negative","neutral","high","extreme"];
const FCOL = ["#3182ce","#a0aec0","#dd6b20","#c53030"];
let DATA = null, SNAPAT = {}, DAYAT = {};

function esc(s){ return String(s).replace(/[&<>]/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c]; }); }
function pad2(n){ return (n<10?"0":"")+n; }
function fAge(a){ return (a===null||a===undefined) ? "-" : Math.round(a)+"h"; }
function fPc(v){ return (v===null||v===undefined) ? "-" : (v>=0?"+":"")+Math.round(v)+" bp"; }
function fOc(v){ return (v===null||v===undefined) ? "-" : (v>=0?"+":"")+v.toFixed(1)+"%"; }
function fPct(v){ return (v===null||v===undefined) ? "-" : Math.round(v*100)+"%"; }
function fundName(c){ return c>=0 ? FNAME[c] : "-"; }
function td(cls, s){ return "<td"+(cls?" class='"+cls+"'":"")+">"+s+"</td>"; }

function barBadge(bs){
  if (bs === -2) return "<span class='tag na'>n/a</span>";
  if (bs === -1) return "<span class='tag quiet'>no regime</span>";
  return "<span class='tag r"+(bs+1)+"'>"+RN[bs]+"</span>";
}

function snapshotIndex(day, hour){
  const key = day + "T" + pad2(hour);
  let lo = 0, hi = DATA.snap.length - 1, ans = 0;
  while (lo <= hi){
    const mid = (lo + hi) >> 1;
    if (DATA.snap[mid] <= key){ ans = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return ans;
}

/* every event inside the 24h window ending at (dayIdx, hour), as absolute hours */
function eventsWindow(dayIdx, hour){
  const A = dayIdx * 24 + hour, lo = A - 23, out = [];
  for (const k of [dayIdx - 1, dayIdx]){
    if (k < 0 || k >= DATA.days.length) continue;
    const list = DATA.ev[k] || [];
    for (let j = 0; j < list.length; j++){
      const e = list[j], a = k * 24 + e[1];
      if (a >= lo && a <= A) out.push({si: e[0], a: a, reg: e[2], pc: e[3], oc: e[4]});
    }
  }
  return out;
}

function indexWindow(list){
  const m = new Map();
  for (const e of list){
    let rec = m.get(e.si);
    if (!rec){ rec = {last: null, byReg: [null,null,null,null], all: []}; m.set(e.si, rec); }
    rec.all.push(e);
    if (!rec.byReg[e.reg] || e.a > rec.byReg[e.reg].a) rec.byReg[e.reg] = e;
    if (!rec.last || e.a > rec.last.a) rec.last = e;
  }
  for (const rec of m.values()) rec.all.sort(function(x,y){ return y.a - x.a; });
  return m;
}

function fmtAbs(a){
  const k = Math.floor(a / 24), h = a - k * 24;
  const d = DATA.days[k] || "?";
  return d.slice(5) + " " + pad2(h) + ":00";
}

function masterTable(day, syms, idx, A){
  let h = "<table><tr><th>#</th><th class='l'>contract</th><th class='l'>state @ bar</th>"
        + "<th>dPrice (1h)</th><th>dOI (1h)</th><th class='l'>last event (24h)</th>"
        + "<th>funding</th><th>vol pctile</th></tr>";
  for (const r of day){
    const m = idx.get(r[I.sym]);
    const last = m ? m.last : null;
    const lastCell = last
      ? "<td class='l'><span class='tag r"+(last.reg+1)+"'>"+RN[last.reg]+"</span> "
        + "<span style='color:#718096'>"+fAge(A - last.a)+"</span></td>"
      : "<td class='l none'>-</td>";
    const cls = r[I.bs] < 0 ? " class='quietrow'" : "";
    h += "<tr"+cls+">" + td("", r[I.rank])
       + "<td class='l'><b>"+esc(syms[r[I.sym]])+"</b></td>"
       + "<td class='l'>"+barBadge(r[I.bs])+"</td>"
       + td("", fPc(r[I.bpc])) + td("", fOc(r[I.boc]))
       + lastCell + td("", fundName(r[I.fund])) + td("", fPct(r[I.vol])) + "</tr>";
  }
  return h + "</table>";
}

function evTable(rec){
  let h = "<table class='evtab'><tr><th>time (UTC)</th><th>regime</th><th>dPrice (1h)</th><th>dOI (1h)</th></tr>";
  for (const x of rec.all){
    h += "<tr><td>"+fmtAbs(x.a)+"</td><td><span class='tag r"+(x.reg+1)+"'>"+RN[x.reg]+"</span></td>"
       + td("", fPc(x.pc)) + td("", fOc(x.oc)) + "</tr>";
  }
  return h + "</table>";
}

function sectionHtml(day, syms, idx, reg, topN, A){
  const rows = [];
  for (const r of day){
    const m = idx.get(r[I.sym]);
    const e = m ? m.byReg[reg] : null;
    if (!e) continue;
    rows.push({r: r, e: e, m: m});
  }
  if (!rows.length) return {html: "<div class='sub none'>none in the window</div>", n: 0};
  rows.sort(function(a,b){ return b.e.a - a.e.a || a.r[I.rank] - b.r[I.rank]; });
  const head = "<div class='grid-h'><span>#</span><span>contract</span><span>age at "+RN[reg]
             + "</span><span>dPrice (1h)</span><span>dOI (1h)</span><span>funding</span><span>vol pctile</span></div>";
  function row(x, i){
    return "<details class='row'><summary><span>"+(i+1)+"</span>"
      + "<span><b>"+esc(syms[x.r[I.sym]])+"</b> <span style='color:#a0aec0;font-weight:400'>"
      + x.m.all.length+" ev</span></span>"
      + "<span>"+fAge(A - x.e.a)+"</span><span>"+fPc(x.e.pc)+"</span><span>"+fOc(x.e.oc)+"</span>"
      + "<span>"+fundName(x.r[I.fund])+"</span><span>"+fPct(x.r[I.vol])+"</span></summary>"
      + evTable(x.m) + "</details>";
  }
  let body = "";
  const top = rows.slice(0, topN), rest = rows.slice(topN);
  top.forEach(function(x,i){ body += row(x,i); });
  if (rest.length){
    body += "<details class='row'><summary style='color:#4a5568'><span></span>"
         + "<span>show all "+rows.length+"</span><span></span><span></span><span></span>"
         + "<span></span><span></span></summary><div style='padding:2px 0 10px'>";
    rest.forEach(function(x,i){ body += row(x, i + topN); });
    body += "</div></details>";
  }
  return {html: head + body, n: rows.length};
}

function scatter(day, syms){
  const W=720, H=400, L=52, R=18, T=16, B=38;
  const pts = day.filter(function(r){ return r[I.fp] !== null && r[I.oi24] !== null; });
  let ymax = 0.02;
  for (const p of pts) ymax = Math.max(ymax, Math.abs(p[I.oi24]));
  ymax = Math.min(0.2, ymax * 1.15);
  const X = function(v){ return L + v * (W - L - R); };
  const Y = function(v){ return (H - B) - ((v + ymax) / (2 * ymax)) * (H - B - T); };
  let s = "<svg width='"+W+"' height='"+H+"' viewBox='0 0 "+W+" "+H+"' style='border:1px solid #e2e8f0;background:#fff'>";
  for (let k = -2; k <= 2; k++){
    const y = Y(k * ymax / 2);
    s += "<line x1='"+L+"' y1='"+y+"' x2='"+(W-R)+"' y2='"+y+"' stroke='#edf2f7'/>";
    s += "<text x='"+(L-6)+"' y='"+(y+3)+"' font-size='10' fill='#718096' text-anchor='end'>"
       + (k*ymax/2*100).toFixed(1) + "%</text>";
  }
  for (let k = 0; k <= 4; k++){
    const x = X(k / 4);
    s += "<line x1='"+x+"' y1='"+T+"' x2='"+x+"' y2='"+(H-B)+"' stroke='#f7fafc'/>";
    s += "<text x='"+x+"' y='"+(H-B+14)+"' font-size='10' fill='#718096' text-anchor='middle'>"
       + (k/4).toFixed(2) + "</text>";
  }
  s += "<line x1='"+L+"' y1='"+Y(0)+"' x2='"+(W-R)+"' y2='"+Y(0)+"' stroke='#a0aec0'/>";
  s += "<line x1='"+X(0.75)+"' y1='"+T+"' x2='"+X(0.75)+"' y2='"+(H-B)+"' stroke='#a0aec0' stroke-dasharray='4 3'/>";
  for (const p of pts){
    s += "<circle cx='"+X(p[I.fp]).toFixed(1)+"' cy='"+Y(p[I.oi24]).toFixed(1)
       + "' r='3.4' fill='"+FCOL[p[I.fund]>=0?p[I.fund]:1]+"' fill-opacity='0.85'/>";
  }
  const byOi = pts.slice().sort(function(a,b){ return b[I.oi24]-a[I.oi24]; }).slice(0,3);
  const byFp = pts.slice().sort(function(a,b){ return b[I.fp]-a[I.fp]; }).slice(0,3);
  const seen = {};
  for (const p of byOi.concat(byFp)){
    if (seen[p[I.sym]]) continue; seen[p[I.sym]] = 1;
    s += "<text x='"+(X(p[I.fp])+6).toFixed(1)+"' y='"+(Y(p[I.oi24])-5).toFixed(1)
       + "' font-size='9' fill='#4a5568'>"+esc(syms[p[I.sym]])+"</text>";
  }
  s += "<text x='"+(L+(W-L-R)/2)+"' y='"+(H-4)+"' font-size='11' fill='#4a5568' text-anchor='middle'>funding percentile (contract's own 90d history)</text>";
  const ym = T+(H-T-B)/2;
  s += "<text x='12' y='"+ym+"' font-size='11' fill='#4a5568' transform='rotate(-90 12 "+ym+")' text-anchor='middle'>24h OI change</text>";
  return s + "</svg>";
}

function extremeTable(day, syms){
  const rows = day.filter(function(r){ return (r[I.fund]===2 || r[I.fund]===3) && r[I.oi24] !== null && r[I.oi24] > 0; })
                   .sort(function(a,b){ return b[I.fp]-a[I.fp]; }).slice(0,10);
  if (!rows.length) return "<div class='sub none'>none</div>";
  let h = "<table><tr><th class='l'>contract</th><th>funding pctile</th><th>24h OI chg</th><th>funding state</th></tr>";
  for (const r of rows){
    h += "<tr><td class='l'><b>"+esc(syms[r[I.sym]])+"</b></td>" + td("", r[I.fp].toFixed(2))
       + td("", fOc(r[I.oi24]*100)) + td("", fundName(r[I.fund])) + "</tr>";
  }
  return h + "</table>";
}

const ANN = Math.sqrt(24 * 365) / 100;   // bp/hour -> annualised %  (93.59 / 100)
function fAnn(v){ return (v===null||v===undefined) ? "-" : (v * ANN).toFixed(1) + "%"; }
function fRatio(v){
  if (v===null||v===undefined) return "-";
  const c = v >= 2.5 ? "color:#c53030;font-weight:700" : (v >= 1.5 ? "color:#dd6b20" : "color:#a0aec0");
  return "<span style='"+c+"'>"+v.toFixed(2)+"x</span>";
}

function volTable(day, syms){
  const rows = day.filter(function(r){ return r[I.vol] !== null; }).sort(function(a,b){ return b[I.vol]-a[I.vol]; });
  let h = "<table><tr><th>#</th><th class='l'>contract</th><th>ann. vol (24h)</th>"
        + "<th>vs own 90d median</th><th>vol pctile (own)</th></tr>";
  rows.forEach(function(r){
    h += "<tr>" + td("", r[I.rank]) + "<td class='l'><b>"+esc(syms[r[I.sym]])+"</b></td>"
       + td("", fAnn(r[I.v24])) + td("", fRatio(r[I.ratio])) + td("", fPct(r[I.vol])) + "</tr>";
  });
  return h + "</table>";
}

function barSummary(day){
  const c = {0:0,1:0,2:0,3:0,q:0,na:0};
  for (const r of day){
    const b = r[I.bs];
    if (b === -2) c.na++; else if (b === -1) c.q++; else c[b]++;
  }
  return "at the bar: R1 "+c[0]+" / R2 "+c[1]+" / R3 "+c[2]+" / R4 "+c[3]
       + " / no regime "+c.q+(c.na ? " / n/a "+c.na : "");
}

function paint(i){
  const day = DATA.rows[i], syms = DATA.symbols;
  const key = DATA.snap[i], dd = key.slice(0, 10), hh = parseInt(key.slice(11), 10);
  const dayIdx = DAYAT[dd];
  const idx = indexWindow(eventsWindow(dayIdx, hh));
  const A = dayIdx * 24 + hh;
  const nEv = day.filter(function(r){ return idx.has(r[I.sym]); }).length;
  document.getElementById("d").value = dd;
  const hs = document.getElementById("h");
  hs.value = String(hh);
  hs.disabled = DATA.kind[i] === 0;
  document.getElementById("asof").innerHTML = "<b>bar " + dd + " " + pad2(hh) + ":00&ndash;"
    + pad2((hh + 1) % 24) + ":00 UTC</b>"
    + (DATA.kind[i] === 0 ? " &middot; <span style='color:#c53030'>daily snapshot</span>" : " &middot; hourly")
    + " &middot; market vol <b>" + DATA.mkt[i] + "</b> &middot; " + nEv + " of " + day.length
    + " had a regime in the trailing 24h";
  document.getElementById("bsum").textContent = barSummary(day);
  document.getElementById("m1").innerHTML = masterTable(day, syms, idx, A);
  const s1 = sectionHtml(day, syms, idx, 0, 10, A);
  const s2 = sectionHtml(day, syms, idx, 1, 10, A);
  const s3 = sectionHtml(day, syms, idx, 2, 10, A);
  const s4 = sectionHtml(day, syms, idx, 3, 10, A);
  document.getElementById("n1").textContent = s1.n; document.getElementById("t1").innerHTML = s1.html;
  document.getElementById("n2").textContent = s2.n; document.getElementById("t2").innerHTML = s2.html;
document.getElementById("n3").textContent = s3.n; document.getElementById("t3").innerHTML = s3.html;
  document.getElementById("n4").textContent = s4.n; document.getElementById("t4").innerHTML = s4.html;
  document.getElementById("sc").innerHTML = scatter(day, syms);
  document.getElementById("ext").innerHTML = extremeTable(day, syms);
  document.getElementById("vt").innerHTML = volTable(day, syms);
}

function go(delta){
  let i = SNAPAT[document.getElementById("d").value + "T" + pad2(+document.getElementById("h").value)];
  if (i === undefined) i = snapshotIndex(document.getElementById("d").value, +document.getElementById("h").value);
  i = Math.max(0, Math.min(DATA.snap.length - 1, i + delta));
  paint(i);
}

function onTimeChange(){
  const dd = document.getElementById("d").value;
  const hs = document.getElementById("h");
  const firstHourly = DATA.snap[DATA.kind.indexOf(1)].slice(0, 10);
  if (dd < firstHourly){ hs.value = "23"; hs.disabled = true; }
  else hs.disabled = false;
  paint(snapshotIndex(dd, +hs.value));
}

async function boot(){
  const raw = window.__D5__.payload;
  const bin = Uint8Array.from(atob(raw), function(c){ return c.charCodeAt(0); });
  const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
  DATA = JSON.parse(await new Response(stream).text());
  DATA.snap.forEach(function(s, i){ SNAPAT[s] = i; });
  DATA.days.forEach(function(d, i){ DAYAT[d] = i; });
  const el = document.getElementById("d"), hs = document.getElementById("h");
  el.min = DATA.snap[0].slice(0, 10);
  el.max = DATA.snap[DATA.snap.length - 1].slice(0, 10);
  for (let k = 0; k < 24; k++){
    const o = document.createElement("option");
    o.value = String(k); o.textContent = pad2(k) + ":00";
    hs.appendChild(o);
  }
  paint(snapshotIndex(el.max, 23));
  el.addEventListener("change", onTimeChange);
  hs.addEventListener("change", onTimeChange);
  document.getElementById("prev").onclick = function(){ go(-1); };
  document.getElementById("next").onclick = function(){ go(1); };
}

if (typeof document !== "undefined") { boot(); }
if (typeof module !== "undefined") {
  module.exports = {I, RN, masterTable, sectionHtml, scatter, extremeTable, volTable,
                    barSummary, snapshotIndex, eventsWindow, indexWindow, fmtAbs,
                    setData: function(d, s, dy){ DATA = d; if (s) SNAPAT = s; if (dy) DAYAT = dy; }};
}
"""

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Price/OI Regime Board</title>
<style>__CSS__</style></head>
<body>
<h1>Price / Open-Interest Regime Board</h1>
<div class="bar">
  <label for="d" style="font-size:13px;color:#4a5568">time</label>
  <input type="date" id="d" style="width:150px">
  <select id="h" style="width:88px"></select>
  <button id="prev">&larr;</button>
  <button id="next">&rarr;</button>
  <span class="hint">hourly for the trailing 180 days; one snapshot per day before that</span>
  <span class="asof" id="asof"></span>
</div>
<div class="banner">Snapshot of a frozen dataset &mdash; the last bar available is
<b>2026-08-31 23:00 UTC</b> (its close). This page does not fetch live data.</div>
<div class="sub">Universe: the top 50 contracts by liquidity in that month, ranked 1..50.
<span id="bsum" style="color:#1a202c;font-weight:600"></span></div>

<h2>1. Master table (all 50, by liquidity rank)</h2>
<div class="sub"><b>state @ bar</b> is the regime label at that hour &mdash; usually
<span class="tag quiet">no regime</span>, because a regime is an hourly event flag, not a persistent
state. <b>last event</b> is the most recent regime inside the 24h window ending at that hour.
Open a contract in sections 2&ndash;5 to see every event inside the window.</div>
<div id="m1"></div>

<h2>2. Long buildup (R1: price up + OI up) &mdash; <span id="n1">0</span> contracts</h2>
<div class="sub">Sorted by recency (freshest first); the first 10 are shown, the rest open
under &ldquo;show all&rdquo;. Price and open interest both above their rolling 90d thresholds.</div>
<div id="t1"></div>

<h2>3. Short covering (R2: price up + OI down) &mdash; <span id="n2">0</span> contracts</h2>
<div class="sub">Sorted by recency; first 10 shown. Price up with open interest falling, the quadrant retail commentary reads as shorts closing.</div>
<div id="t2"></div>

<h2>4. Short buildup (R3: price down + OI up) &mdash; <span id="n3">0</span> contracts</h2>
<div class="sub">Sorted by recency; first 10 shown.</div>
<div id="t3"></div>

<h2>5. Deleveraging (R4: price down + OI down) &mdash; <span id="n4">0</span> contracts</h2>
<div class="sub">Sorted by recency; first 10 shown. Strictly R4; short covering has its own list above.</div>
<div id="t4"></div>

<h2>6. Funding-adjusted crowding view</h2>
<div class="sub">x = funding percentile against the contract's own 90d history; y = 24h
open-interest change. Upper-right = high funding with positions still being added. Dashed
line marks the 75th percentile.</div>
<div id="sc"></div>
<div class="legend"><span><i class="dot" style="background:#3182ce"></i>negative</span><span><i class="dot" style="background:#a0aec0"></i>neutral</span><span><i class="dot" style="background:#dd6b20"></i>high</span><span><i class="dot" style="background:#c53030"></i>extreme</span></div>
<div class="sub" style="margin-top:10px">Extreme quadrant: funding state high or extreme
<b>and</b> 24h OI still rising &mdash; crowded longs still being added to.</div>
<div id="ext"></div>

<h2>7. Realised volatility: level and percentile</h2>
<div class="sub"><b>ann. vol</b> = standard deviation of the last 24 hourly log returns,
annualised by &radic;(24&times;365) = 93.6 &mdash; i.e. "if this day were the year". It is a
one-day estimate, so treat it as a coarse risk gauge, not a forecast.
<b>vs own 90d median</b> is that level divided by the median of the same measure over the
trailing 90 days &mdash; above 2.5x is the practical "abnormal" line.
<b>vol pctile</b> is its rank inside the same 90-day window (own history, not peers).
This is the one dimension of the price/OI framework that is statistically robust: forward
volatility rises after these events (16/16 cells, Phase 3). Direction is not.</div>
<div id="vt"></div>

<script>window.__D5__={payload:"__PAYLOAD__",asof:"__ASOF__"};</script>
<script>__JS__</script>
</body></html>
"""