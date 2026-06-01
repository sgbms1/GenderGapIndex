#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静岡県 ジェンダーギャップ指数 インタラクティブ・コロプレスマップ生成

shizuoka_ggi_comparison.csv と 静岡県市区町村ポリゴン(GeoJSON, 国土数値情報N03ベース)を
結合し、指標/スコアをプルダウンで切り替えできる自己完結HTML(Leaflet)を出力する。

- 政令市(静岡市22100・浜松市22130)はGeoJSON側が区分割のため、区コードを市コードへ
  マップし、親市のスコアで着色する。
- ベース地図タイルは使わない「白地図」表示。Leaflet本体のみCDNから読み込む。

実行: python3 generate_map.py  ->  index.html（GitHub Pagesのルートで開けるよう index.html を出力）
"""

import json
import os
import math
import pandas as pd

CSV = "shizuoka_ggi_comparison.csv"
GEO_RAW = "geo/shizuoka_raw.json"
OUT_HTML = "index.html"

# 政令市の区コード -> 市コード（whole）への対応
WARD_TO_CITY = {
    "22101": "22100", "22102": "22100", "22103": "22100",                      # 静岡市
    "22131": "22130", "22132": "22130", "22133": "22130", "22134": "22130",    # 浜松市
    "22135": "22130", "22136": "22130", "22137": "22130",
}

# 地図で切り替えられる指標（key=CSV列名, type=配色 seq/div, group=プルダウンの分類）
METRICS = [
    {"key": "4指標版総合スコア",        "label": "総合スコア｜4指標版",        "type": "seq", "group": "総合スコア"},
    {"key": "8指標版総合スコア",        "label": "総合スコア｜8指標版",        "type": "seq", "group": "総合スコア"},
    {"key": "差分(8指標版-4指標版)",     "label": "差分（8指標版 − 4指標版）",   "type": "div", "group": "総合スコア"},
    {"key": "8指標版_政治分野",         "label": "分野｜政治",                "type": "seq", "group": "分野別（8指標版）"},
    {"key": "8指標版_行政分野",         "label": "分野｜行政",                "type": "seq", "group": "分野別（8指標版）"},
    {"key": "8指標版_地域分野",         "label": "分野｜地域",                "type": "seq", "group": "分野別（8指標版）"},
    {"key": "8指標版_経済分野",         "label": "分野｜経済",                "type": "seq", "group": "分野別（8指標版）"},
    {"key": "①議員",     "label": "① 議会の女性議員比率",       "type": "seq", "group": "個別指数"},
    {"key": "②管理職",   "label": "② 女性管理職比率",          "type": "seq", "group": "個別指数"},
    {"key": "③審議会",   "label": "③ 審議会委員の女性比率",     "type": "seq", "group": "個別指数"},
    {"key": "④男性育休", "label": "④ 男性職員の育休取得率",     "type": "seq", "group": "個別指数"},
    {"key": "⑤首長",     "label": "⑤ 首長・副首長の女性",       "type": "seq", "group": "個別指数"},
    {"key": "⑥防災",     "label": "⑥ 防災会議の女性比率",       "type": "seq", "group": "個別指数"},
    {"key": "⑦自治会長", "label": "⑦ 自治会長の女性比率",       "type": "seq", "group": "個別指数"},
    {"key": "⑧給与",     "label": "⑧ 給与の男女差異",          "type": "seq", "group": "個別指数"},
]


def round_coords(obj, ndigits=4):
    """GeoJSON座標を丸めてサイズ削減（約11m精度。コロプレスには十分）。"""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(obj[0]), ndigits), round(float(obj[1]), ndigits)]
        return [round_coords(x, ndigits) for x in obj]
    return obj


def build_geo(names):
    raw = json.load(open(GEO_RAW, encoding="utf-8"))
    feats = []
    for f in raw["features"]:
        p = f["properties"]
        code = p.get("N03_007")
        if code is None:
            continue
        city_code = WARD_TO_CITY.get(code, code)
        if city_code not in names:
            continue  # 静岡県内35市区町村以外は除外
        ward = p.get("N03_004") if code in WARD_TO_CITY else None
        feats.append({
            "type": "Feature",
            "properties": {
                "code": city_code,           # データ結合キー（市レベル）
                "name": names[city_code],    # 表示名（市区町村名）
                "ward": ward,                # 政令市の区名（あれば）
            },
            "geometry": {
                "type": f["geometry"]["type"],
                "coordinates": round_coords(f["geometry"]["coordinates"]),
            },
        })
    return {"type": "FeatureCollection", "features": feats}


def build_data(df):
    """code -> {metric_key: value or None} の辞書。"""
    data = {}
    for _, row in df.iterrows():
        code = str(row["自治体コード"]).zfill(5)
        rec = {}
        for m in METRICS:
            v = row[m["key"]]
            if pd.isna(v) or v == "":
                rec[m["key"]] = None
            else:
                rec[m["key"]] = round(float(v), 4)
        data[code] = rec
    return data


def main():
    df = pd.read_csv(CSV, dtype={"自治体コード": str})
    df["自治体コード"] = df["自治体コード"].str.zfill(5)
    names = dict(zip(df["自治体コード"], df["市区町村名"]))

    geo = build_geo(names)
    data = build_data(df)
    print(f"GeoJSON: {len(geo['features'])} features / データ: {len(data)} 自治体")

    html = HTML_TEMPLATE
    html = html.replace("__GEO__", json.dumps(geo, ensure_ascii=False))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__METRICS__", json.dumps(METRICS, ensure_ascii=False))
    html = html.replace("__NAMES__", json.dumps(names, ensure_ascii=False))
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"出力: {OUT_HTML}（{os.path.getsize(OUT_HTML)//1024} KB）")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>静岡県 市町村版ジェンダーギャップ指数マップ</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin: 0; height: 100%; font-family: system-ui, "Hiragino Sans", "Noto Sans JP", sans-serif; }
  #map { position: absolute; top: 0; bottom: 0; left: 0; right: 0; background: #ffffff; }
  .leaflet-interactive:focus { outline: none; }  /* クリック時のフォーカス枠（四角）を抑制 */
  .panel { background: rgba(255,255,255,0.95); padding: 12px 14px; border-radius: 8px;
           box-shadow: 0 1px 6px rgba(0,0,0,0.25); }
  #controls { position: absolute; top: 12px; left: 12px; z-index: 1000; max-width: 320px; }
  #controls h1 { font-size: 15px; margin: 0 0 8px; }
  #controls select { width: 100%; padding: 6px; font-size: 13px; }
  #controls .note { font-size: 11px; color: #555; margin-top: 8px; line-height: 1.4; }
  #controls details { margin-top: 8px; font-size: 11px; }
  #controls summary { cursor: pointer; color: #15803d; font-weight: 600; }
  #controls .bd p { margin: 6px 0 0; line-height: 1.5; color: #333; }
  #controls .bd-note { color: #666; }
  #info { position: absolute; top: 12px; right: 12px; z-index: 1000; width: 230px; font-size: 13px; }
  #info h2 { font-size: 14px; margin: 0 0 6px; }
  #info table { width: 100%; border-collapse: collapse; font-size: 12px; }
  #info td { padding: 1px 2px; }
  #info td.v { text-align: right; font-variant-numeric: tabular-nums; }
  #info .big { font-size: 20px; font-weight: bold; }
  .legend { position: absolute; bottom: 18px; left: 12px; z-index: 1000; font-size: 12px; }
  .legend .bar { height: 12px; width: 220px; border: 1px solid #999; border-radius: 2px; }
  .legend .ticks { display: flex; justify-content: space-between; width: 222px; margin-top: 2px; }
  .legend .na { margin-top: 6px; color: #555; }
  .legend .na i { display: inline-block; width: 12px; height: 12px; background: #e8e8e8;
                  border: 1px solid #999; vertical-align: -2px; margin-right: 4px; }
</style>
</head>
<body>
<div id="map"></div>

<div id="controls" class="panel">
  <h1>静岡県 ジェンダーギャップ指数マップ</h1>
  <select id="metric"></select>
  <div class="note" id="metricNote"></div>
  <div class="note">指数は 0.00〜1.00（1.00で男女均等）。色が濃いほど均等。地図をホバーで詳細表示。</div>
  <details id="breakdown">
    <summary>4指標版・8指標版の内訳を見る</summary>
    <div class="bd">
      <p><b>4指標版（基本4指標）</b><br>
        ① 議会の女性議員比率〔政治〕<br>
        ② 女性管理職比率〔行政〕<br>
        ③ 審議会委員の女性比率〔行政〕<br>
        ④ 男性職員の育休取得率〔経済〕</p>
      <p><b>8指標版（基本4＋追加4）</b><br>
        上記①〜④ に加えて<br>
        ⑤ 首長・副首長の女性〔政治〕<br>
        ⑥ 防災会議の女性比率〔行政〕<br>
        ⑦ 自治会長の女性比率〔地域〕<br>
        ⑧ 給与の男女差異〔経済〕</p>
      <p class="bd-note">〔 〕は分野。総合スコアは「分野内を逆標準偏差で加重平均 → 分野間を均等平均」。
        4指標版は政治・行政・経済の3分野、8指標版は地域を加えた4分野。</p>
    </div>
  </details>
</div>

<div id="info" class="panel">
  <h2 id="infoName">自治体を選択</h2>
  <div><span class="big" id="infoVal">—</span> <span id="infoLabel" style="font-size:12px;color:#555"></span></div>
  <table id="infoTable"></table>
</div>

<div id="legend" class="legend panel">
  <div id="legendTitle" style="margin-bottom:4px;font-weight:bold;"></div>
  <div class="bar" id="legendBar"></div>
  <div class="ticks" id="legendTicks"></div>
  <div class="na"><i></i>データなし（未公表/欠損）</div>
</div>

<script>
const GEO = __GEO__;
const DATA = __DATA__;
const METRICS = __METRICS__;
const NAMES = __NAMES__;

// 配色（seq=緑系シーケンシャル, div=赤白青ダイバージング）
const SEQ = ['#f7fcf5','#c7e9c0','#74c476','#238b45','#00441b'];
const DIV = ['#b2182b','#ef8a62','#f7f7f7','#67a9cf','#2166ac'];
const NA_COLOR = '#e8e8e8';

function hex2rgb(h){ return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]; }
function rgb2css(c){ return 'rgb('+c.map(x=>Math.round(x)).join(',')+')'; }
function ramp(stops, t){
  t = Math.max(0, Math.min(1, t));
  const seg = (stops.length - 1);
  const i = Math.min(seg - 1, Math.floor(t * seg));
  const lt = (t * seg) - i;
  const a = hex2rgb(stops[i]), b = hex2rgb(stops[i+1]);
  return rgb2css(a.map((av,k)=> av + (b[k]-av)*lt));
}
function metricByKey(k){ return METRICS.find(m=>m.key===k); }
function valuesFor(key){
  return Object.values(DATA).map(d=>d[key]).filter(v=>v!==null && v!==undefined);
}
function domainFor(m){
  const vs = valuesFor(m.key);
  if(vs.length===0) return [0,1];
  if(m.type==='div'){ const a = Math.max(...vs.map(v=>Math.abs(v)), 1e-6); return [-a, a]; }
  let mn = Math.min(...vs), mx = Math.max(...vs);
  if(mx===mn) mx = mn + 1e-6;
  return [mn, mx];
}
function colorFor(m, v){
  if(v===null || v===undefined) return NA_COLOR;
  const [lo,hi] = domainFor(m);
  const t = (v - lo) / (hi - lo);
  return ramp(m.type==='div'?DIV:SEQ, t);
}
function fmt(v){ return (v===null||v===undefined) ? '—' : v.toFixed(2); }

let current = METRICS[0].key;

const map = L.map('map', { zoomControl: true, attributionControl: false });

function styleFn(f){
  const v = (DATA[f.properties.code]||{})[current];
  return { fillColor: colorFor(metricByKey(current), v), weight: 0.8,
           color: '#777', fillOpacity: 0.85 };
}
function highlight(e){
  const l = e.target;
  l.setStyle({ weight: 2.5, color: '#222', fillOpacity: 0.95 });
  l.bringToFront();
  showInfo(l.feature.properties.code);
}
function reset(e){ geoLayer.resetStyle(e.target); }

function tooltipHTML(code){
  const m = metricByKey(current);
  const v = (DATA[code]||{})[current];
  return '<b>'+NAMES[code]+'</b><br>'+m.label+': '+fmt(v);
}

let geoLayer = L.geoJSON(GEO, {
  style: styleFn,
  onEachFeature: (f, l) => {
    l.bindTooltip(tooltipHTML(f.properties.code), {sticky:true});
    l.on({ mouseover: highlight, mouseout: reset });
  }
}).addTo(map);
map.fitBounds(geoLayer.getBounds(), { padding: [20,20] });

function showInfo(code){
  const d = DATA[code] || {};
  document.getElementById('infoName').textContent = NAMES[code];
  const m = metricByKey(current);
  document.getElementById('infoVal').textContent = fmt(d[current]);
  document.getElementById('infoLabel').textContent = m.label;
  let rows = '';
  for(const mm of METRICS){
    const hi = (mm.key===current) ? ' style="background:#fff3cd"' : '';
    rows += '<tr'+hi+'><td>'+mm.label+'</td><td class="v">'+fmt(d[mm.key])+'</td></tr>';
  }
  document.getElementById('infoTable').innerHTML = rows;
}

function updateLegend(){
  const m = metricByKey(current);
  const stops = (m.type==='div'?DIV:SEQ);
  const grad = stops.map((c,i)=> c+' '+(i/(stops.length-1)*100).toFixed(0)+'%').join(', ');
  document.getElementById('legendBar').style.background = 'linear-gradient(to right, '+grad+')';
  document.getElementById('legendTitle').textContent = m.label;
  const [lo,hi] = domainFor(m);
  const mid = (lo+hi)/2;
  document.getElementById('legendTicks').innerHTML =
    '<span>'+lo.toFixed(2)+'</span><span>'+mid.toFixed(2)+'</span><span>'+hi.toFixed(2)+'</span>';
}

function updateMap(){
  geoLayer.setStyle(styleFn);
  geoLayer.eachLayer(l => l.setTooltipContent(tooltipHTML(l.feature.properties.code)));
  updateLegend();
  // info欄の選択中metric表示を更新（自治体選択済みなら維持）
  const cur = document.getElementById('infoName').textContent;
  const code = Object.keys(NAMES).find(c=>NAMES[c]===cur);
  if(code) showInfo(code);
}

// プルダウン構築（group別optgroup）
const sel = document.getElementById('metric');
const groups = {};
for(const m of METRICS){ (groups[m.group]=groups[m.group]||[]).push(m); }
for(const g of Object.keys(groups)){
  const og = document.createElement('optgroup'); og.label = g;
  for(const m of groups[g]){
    const o = document.createElement('option'); o.value = m.key; o.textContent = m.label;
    og.appendChild(o);
  }
  sel.appendChild(og);
}
const NOTES = {
  '4指標版総合スコア': '基本4指標＝①議員・②管理職・③審議会・④男性育休（政治/行政/経済）。',
  '8指標版総合スコア': '8指標＝基本4＋⑤首長・⑥防災・⑦自治会長・⑧給与（政治/行政/地域/経済）。',
  '差分(8指標版-4指標版)': '青=8指標版が高い / 赤=低い（0が中心）。指標を増やした影響を表す。',
  '⑧給与': '女性活躍推進法の未公表5町は「データなし」。',
  '⑦自治会長': '全自治体で女性比率が極端に低く、分散が小さい指標。',
};
sel.addEventListener('change', e => {
  current = e.target.value;
  document.getElementById('metricNote').textContent = NOTES[current] || '';
  updateMap();
});

updateLegend();
document.getElementById('metricNote').textContent = NOTES[current] || '';
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
