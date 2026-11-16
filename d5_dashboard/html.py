"""D5 -- the interactive HTML shell: one file, payload embedded, no server."""

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px auto;max-width:1180px;color:#1a202c}
h1{font-size:21px;margin:0 0 2px}
h2{font-size:15px;margin:26px 0 8px;border-bottom:1px solid #e2e8f0;padding-bottom:4px}
.sub{color:#4a5568;font-size:12.5px;margin-bottom:14px;line-height:1.7}
.bar{display:flex;align-items:center;gap:10px;margin:10px 0 4px;padding:10px 12px;background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px}
.bar input{font-size:13px;padding:4px 6px;border:1px solid #cbd5e0;border-radius:4px}
.bar button{font-size:13px;padding:4px 10px;border:1px solid #cbd5e0;background:#fff;border-radius:4px;cursor:pointer}
.bar button:hover{background:#edf2f7}
.bar .asof{margin-left:auto;font-size:12.5px;color:#4a5568}
.bar .asof b{color:#1a202c}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{padding:4px 9px;border-bottom:1px solid #edf2f7;text-align:right}
th{background:#f7fafc;font-weight:600}
td.l,th.l{text-align:left}
.tag{font-family:ui-monospace,Menlo,monospace;font-size:11px;padding:1px 5px;border-radius:3px}
.r1{background:#c6f6d5;color:#22543d}
.r3{background:#fed7d7;color:#742a2a}
.r4{background:#e2e8f0;color:#2d3748}
.r2{background:#fefcbf;color:#744210}
.none{color:#a0aec0}
footer{margin-top:34px;font-size:11px;color:#718096;line-height:1.7;border-top:1px solid #e2e8f0;padding-top:12px}
.legend{font-size:11.5px;color:#4a5568;margin:6px 0 0}
.legend span{display:inline-block;margin-right:12px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:-1px}
"""

JS = r"""
const I = {rank:0,sym:1,last:2,age:3,pc:4,oc:5,fund:6,vol:7,oi24:8,
           a1:9,a3:10,a4:11,fp:12,pc1:13,oc1:14,pc3:15,oc3:16,pc4:17,oc4:18};
const RN = ["R1","R2","R3","R4"];
const FNAME = ["negative","neutral","high","extreme"];
const FCOL = ["#3182ce","#a0aec0","#dd6b20","#c53030"];
let DATA = null, INDEX = {};

function esc(s){ return String(s).replace(/[&<>]/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;"}[c]; }); }
function fAge(a){ return a===null ? "-" : Math.round(a)+"h"; }
function fPc(v){ return v===null ? "-" : (v>=0?"+":"")+Math.round(v)+" bp"; }
function fOc(v){ return v===null ? "-" : (v>=0?"+":"")+v.toFixed(1)+"%"; }
function fPct(v){ return v===null ? "-" : Math.round(v*100)+"%"; }
function td(cls, s){ return "<td"+(cls?" class='"+cls+"'":"")+">"+s+"</td>"; }
function fundName(c){ return c>=0 ? FNAME[c] : "-"; }

function masterTable(day, syms){
  let h = "<table><tr><th>#</th><th class='l'>contract</th><th class='l'>last state</th>"
        + "<th>age</th><th>price chg</th><th>OI chg</th><th>funding</th><th>vol pctile</th></tr>";
  for (const r of day){
    const badge = r[I.last] < 0
      ? "<td class='l none'>-</td>"
      : "<td class='l'><span class='tag r"+(r[I.last]+1)+"'>"+RN[r[I.last]]+"</span></td>";
    h += "<tr>" + td("", r[I.rank])
       + "<td class='l'><b>" + esc(syms[r[I.sym]]) + "</b></td>" + badge
       + td("", fAge(r[I.age])) + td("", fPc(r[I.pc])) + td("", fOc(r[I.oc]))
       + td("", fundName(r[I.fund])) + td("", fPct(r[I.vol])) + "</tr>";
  }
  return h + "</table>";
}

function callout(day, syms, ai, pi, oi, rg){
  const rows = day.filter(r => r[ai] !== null);
  let h = "<table><tr><th>#</th><th class='l'>contract</th><th>age at "+rg+"</th>"
        + "<th>price chg</th><th>OI chg</th><th>funding</th><th>vol pctile</th></tr>";
  for (const r of rows){
    h += "<tr>" + td("", r[I.rank])
       + "<td class='l'><b>" + esc(syms[r[I.sym]]) + "</b></td>"
       + td("", fAge(r[ai])) + td("", fPc(r[pi])) + td("", fOc(r[oi]))
       + td("", fundName(r[I.fund])) + td("", fPct(r[I.vol])) + "</tr>";
  }
  return {html: h + "</table>", n: rows.length};
}

function scatter(day, syms){
  const W=720, H=400, L=52, R=18, T=16, B=38;
  const pts = day.filter(r => r[I.fp] !== null && r[I.oi24] !== null);
  let ymax = 0.02;
  for (const p of pts) ymax = Math.max(ymax, Math.abs(p[I.oi24]));
  ymax = Math.min(0.2, ymax * 1.15);
  const X = v => L + v * (W - L - R);
  const Y = v => (H - B) - ((v + ymax) / (2 * ymax)) * (H - B - T);
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
  const byOi = pts.slice().sort((a,b)=>b[I.oi24]-a[I.oi24]).slice(0,3);
  const byFp = pts.slice().sort((a,b)=>b[I.fp]-a[I.fp]).slice(0,3);
  const seen = new Set();
  for (const p of byOi.concat(byFp)){
    const key = p[I.sym]; if (seen.has(key)) continue; seen.add(key);
    s += "<text x='"+(X(p[I.fp])+6).toFixed(1)+"' y='"+(Y(p[I.oi24])-5).toFixed(1)
       + "' font-size='9' fill='#4a5568'>"+esc(syms[p[I.sym]])+"</text>";
  }
  s += "<text x='"+(L+(W-L-R)/2)+"' y='"+(H-4)+"' font-size='11' fill='#4a5568' text-anchor='middle'>funding percentile (contract's own 90d history)</text>";
  s += "<text x='12' y='"+(T+(H-T-B)/2)+"' font-size='11' fill='#4a5568' transform='rotate(-90 12 "+(T+(H-T-B)/2)+")' text-anchor='middle'>24h OI change</text>";
  return s + "</svg>";
}

function extremeTable(day, syms){
  const rows = day.filter(r => (r[I.fund] === 2 || r[I.fund] === 3) && r[I.oi24] !== null && r[I.oi24] > 0)
                   .sort((a,b)=> b[I.fp]-a[I.fp]).slice(0,10);
  if (!rows.length) return "<div class='sub none'>none</div>";
  let h = "<table><tr><th class='l'>contract</th><th>funding pctile</th><th>24h OI chg</th><th>funding state</th></tr>";
  for (const r of rows){
    h += "<tr><td class='l'><b>"+esc(syms[r[I.sym]])+"</b></td>" + td("", fPct2(r[I.fp]))
       + td("", fOc(r[I.oi24]*100)) + td("", fundName(r[I.fund])) + "</tr>";
  }
  return h + "</table>";
}
function fPct2(v){ return v===null ? "-" : v.toFixed(2); }

function volTable(day, syms){
  const rows = day.filter(r => r[I.vol] !== null).sort((a,b)=> b[I.vol]-a[I.vol]);
  let h = "<table><tr><th>#</th><th class='l'>contract</th><th>vol pctile (own)</th><th>cross-sectional rank</th></tr>";
  rows.forEach(function(r, i){
    h += "<tr>" + td("", r[I.rank]) + "<td class='l'><b>"+esc(syms[r[I.sym]])+"</b></td>"
       + td("", fPct(r[I.vol])) + td("", (i+1)) + "</tr>";
  });
  return h + "</table>";
}

function nearest(dateStr){
  const days = DATA.days;
  if (INDEX[dateStr] !== undefined) return INDEX[dateStr];
  let lo = 0, hi = days.length - 1, ans = 0;
  while (lo <= hi){
    const mid = (lo + hi) >> 1;
    if (days[mid] <= dateStr){ ans = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return ans;
}

function paint(i){
  const day = DATA.rows[i], syms = DATA.symbols;
  const ev = day.filter(r => r[I.last] >= 0).length;
  document.getElementById("asof").innerHTML = "<b>" + DATA.days[i] + " 24:00 UTC</b> (daily close) &middot; market volatility regime <b>"
    + DATA.mkt[i] + "</b> &middot; " + ev + " of " + day.length + " contracts had a regime in the last 24h";
  document.getElementById("m1").innerHTML = masterTable(day, syms);
  const c1 = callout(day, syms, I.a1, I.pc1, I.oc1, "R1");
  const c3 = callout(day, syms, I.a3, I.pc3, I.oc3, "R3");
  const c4 = callout(day, syms, I.a4, I.pc4, I.oc4, "R4");
  document.getElementById("n1").textContent = c1.n; document.getElementById("t1").innerHTML = c1.html;
  document.getElementById("n3").textContent = c3.n; document.getElementById("t3").innerHTML = c3.html;
  document.getElementById("n4").textContent = c4.n; document.getElementById("t4").innerHTML = c4.html;
  document.getElementById("sc").innerHTML = scatter(day, syms);
  document.getElementById("ext").innerHTML = extremeTable(day, syms);
  document.getElementById("vt").innerHTML = volTable(day, syms);
  document.getElementById("d").value = DATA.days[i];
}

function step(n){
  let i = nearest(document.getElementById("d").value) + n;
  i = Math.max(0, Math.min(DATA.rows.length - 1, i));
  paint(i);
}

async function boot(){
  const raw = window.__D5__.payload;
  const bin = Uint8Array.from(atob(raw), c => c.charCodeAt(0));
  const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(stream).text();
  DATA = JSON.parse(text);
  DATA.days.forEach(function(d, i){ INDEX[d] = i; });
  const el = document.getElementById("d");
  el.min = DATA.days[0]; el.max = DATA.days[DATA.days.length - 1];
  paint(nearest(window.__D5__.asof));
  el.addEventListener("change", function(){ paint(nearest(el.value)); });
  document.getElementById("prev").onclick = function(){ step(-1); };
  document.getElementById("next").onclick = function(){ step(1); };
}

if (typeof document !== "undefined") { boot(); }
if (typeof module !== "undefined") {
  module.exports = {I, RN, FNAME, masterTable, callout, scatter, extremeTable, volTable, nearest, setData: function(d, ix){ DATA = d; INDEX = ix; }};
}
"""

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Price/OI Regime Board</title>
<style>__CSS__</style></head>
<body>
<h1>Price / Open-Interest Regime Board</h1>
<div class="bar">
  <label for="d" style="font-size:13px;color:#4a5568">as of</label>
  <input type="date" id="d">
  <button id="prev">&larr; prev day</button>
  <button id="next">next day &rarr;</button>
  <span class="asof" id="asof"></span>
</div>
<div class="sub">Universe: the top 50 contracts by liquidity in that month, ranked 1..50.
Pick any day with the date control (or step a day at a time). Everything is computed
from the frozen dataset &mdash; <b>not live data</b>.</div>

<h2>1. Master table (all 50, by liquidity rank)</h2>
<div class="sub">Each row is one contract; <b>last state</b> is its most recent regime within
the 24h window and <b>age</b> is how long ago it happened. Contracts with nothing in the
window show <span class="none">-</span>.</div>
<div id="m1"></div>

<h2>2. Long buildup (R1: price up + OI up) &mdash; <span id="n1">0</span> contracts</h2>
<div class="sub">Price and open interest both above their rolling 90d thresholds. Age and size
are the R1 event itself, which may not be the contract's most recent state.</div>
<div id="t1"></div>

<h2>3. Short buildup (R3: price down + OI up) &mdash; <span id="n3">0</span> contracts</h2>
<div class="sub">Price below its threshold with open interest above its own.</div>
<div id="t3"></div>

<h2>4. Deleveraging (R4: price down + OI down) &mdash; <span id="n4">0</span> contracts</h2>
<div class="sub">Open interest contracting while price falls &mdash; the note's stress case.
Strictly R4: R2 (price up + OI down) is short covering and is not listed here.</div>
<div id="t4"></div>

<h2>5. Funding-adjusted crowding view</h2>
<div class="sub">x = funding percentile against the contract's own 90d history; y = 24h
open-interest change. Upper-right = high funding with positions still being added.
Dashed line marks the 75th percentile.</div>
<div id="sc"></div>
<div class="legend"><span><i class="dot" style="background:#3182ce"></i>negative</span><span><i class="dot" style="background:#a0aec0"></i>neutral</span><span><i class="dot" style="background:#dd6b20"></i>high</span><span><i class="dot" style="background:#c53030"></i>extreme</span></div>
<div class="sub" style="margin-top:10px">Extreme quadrant: funding state high or extreme
<b>and</b> 24h OI still rising &mdash; crowded longs still being added to.</div>
<div id="ext"></div>

<h2>6. Volatility percentile (own 90d history)</h2>
<div class="sub">24h realised volatility of hourly returns, ranked against the same
contract's own trailing 90 days. This is the one dimension of the price/OI framework that
is statistically robust: forward volatility rises after these events (16/16 cells, Phase 3).
Direction is not.</div>
<div id="vt"></div>

<footer>
<b>Not a trading signal.</b> This board is a state monitor. The strategy test in Phase 5
found no first-moment edge after a 20bp taker round trip: net Sharpe -1.48 (A1) and -0.98
(B1) on the main test window, and the verdict is not passed. The robust finding is the
<i>second</i> moment &mdash; see section 6 and <code>phase3_event/GUIDANCE.md</code>. No
historical return, Sharpe or cost figure appears anywhere on this page by design.
<br><br>Regimes are hourly event flags, not persistent states: at any hour only ~4-8% of
contracts sit in one. Snapshots are taken at each UTC day's last bar; the dataset ends
2026-09-01 00:00 UTC, so the last selectable day is 2026-08-31.
</footer>
<script>window.__D5__={payload:"__PAYLOAD__",asof:"__ASOF__"};</script>
<script>__JS__</script>
</body></html>
"""
