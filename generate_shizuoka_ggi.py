#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静岡県 市町村版ジェンダーギャップ指数(GGI) 算出スクリプト

「4指標版」と「8指標版」の2パターンの総合スコアを静岡県内の全市区町村について
算出・比較し、shizuoka_ggi_comparison.csv を出力する。

【算出手法】共同通信・上智大監修「都道府県版ジェンダーギャップ指数」(WEF方式)に準拠。
  1段階目: 指標ごとに R̃ = min(1, 女性値/男性値)（育休は男性/女性）を算出（1で平等）。
  2段階目: 各分野(政治/行政/地域/経済)の中で逆標準偏差ウェイト wⱼ=(1/sⱼ)/Σ(1/sₖ) による加重平均。
  3段階目: 分野間を均等平均して総合スコアを算出（公式同様の4分野構造版）。
           （欠損指標は分野内でウェイトを再正規化して除外。）

データ源（すべて内閣府系。Kickoff指定の総務省「勤務条件等調査」は全国集計のみで
市区町村別データが存在しないため、市区町村別が取れる内閣府系データで代替している）:
  ①〜③・⑤⑥⑦ : 内閣府「市区町村女性参画状況見える化マップ」CSV（2024年）
  ④          : 同マップ CSV（男性育休のみ。最新2023年）
  ⑧          : 男女共同参画局・女性活躍推進法 公表情報 Excel（令和6年度）

実行: python3 generate_shizuoka_ggi.py
"""

import os
import sys
import pandas as pd
import requests

# ----------------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------------
DATA_DIR = "data"
OUTPUT_CSV = "shizuoka_ggi_comparison.csv"
UA = {"User-Agent": "Mozilla/5.0 (compatible; shizuoka-ggi/1.0)"}

MAP_BASE = "https://wwwa.cao.go.jp/shichoson_map/data/csv"
GENDER_BASE = "https://www.gender.go.jp/policy/suishin_law/csv_dl/kyuyo_sai"

# 見える化マップ CSV（ファイル名 -> (URL, 保存名)）
MAP_FILES = {
    "giin":               f"{MAP_BASE}/2024/giin.csv",                # ① 議会の女性議員比率
    "kanrishoku":         f"{MAP_BASE}/2024/kanrishoku.csv",          # ② 女性管理職比率
    "shingikai":          f"{MAP_BASE}/2024/shingikai.csv",           # ③ 審議会委員の女性比率
    "dansei_ikujikyugyo": f"{MAP_BASE}/2023/dansei_ikujikyugyo.csv",  # ④ 男性職員の育休取得率(最新2023)
    "shicho":             f"{MAP_BASE}/2024/shicho.csv",              # ⑤ 首長・副首長の女性有無
    "bousai":             f"{MAP_BASE}/2024/bousai.csv",              # ⑥ 防災会議の女性比率
    "jichikaicho":        f"{MAP_BASE}/2024/jichikaicho.csv",         # ⑦ 自治会長の女性比率
}

# ⑧ 給与の男女差異 Excel（静岡県を含むファイルのみ。shichoson1=北海道〜長野は静岡を含まないため不要）
WAGE_FILES = {
    "kyuyo_shichoson2":      f"{GENDER_BASE}/shichoson2.xlsx",        # 岐阜〜沖縄（静岡の市町）
    "kyuyo_seireishiteitoshi": f"{GENDER_BASE}/seireishiteitoshi.xlsx",  # 政令市（静岡市・浜松市）
}

# 静岡県内35市区町村（JISコード22始まり）コード -> 名称
SHIZUOKA = {
    "22100": "静岡市", "22130": "浜松市", "22203": "沼津市", "22205": "熱海市",
    "22206": "三島市", "22207": "富士宮市", "22208": "伊東市", "22209": "島田市",
    "22210": "富士市", "22211": "磐田市", "22212": "焼津市", "22213": "掛川市",
    "22214": "藤枝市", "22215": "御殿場市", "22216": "袋井市", "22219": "下田市",
    "22220": "裾野市", "22221": "湖西市", "22222": "伊豆市", "22223": "御前崎市",
    "22224": "菊川市", "22225": "伊豆の国市", "22226": "牧之原市",
    "22301": "東伊豆町", "22302": "河津町", "22304": "南伊豆町", "22305": "松崎町",
    "22306": "西伊豆町", "22325": "函南町", "22341": "清水町", "22342": "長泉町",
    "22344": "小山町", "22424": "吉田町", "22429": "川根本町", "22461": "森町",
}

# 分野構造（Kickoffの分野タグに準拠）。公式手法と同様に「分野内を逆SD加重→分野間を均等平均」する。
FIELDS_8 = {
    "政治": ["①議員", "⑤首長"],
    "行政": ["②管理職", "③審議会", "⑥防災"],
    "地域": ["⑦自治会長"],
    "経済": ["④男性育休", "⑧給与"],
}
FIELDS_4 = {  # 4指標版(①〜④)に登場する分野のみ
    "政治": ["①議員"],
    "行政": ["②管理職", "③審議会"],
    "経済": ["④男性育休"],
}


# ----------------------------------------------------------------------------
# ダウンロード
# ----------------------------------------------------------------------------
def download_all():
    os.makedirs(DATA_DIR, exist_ok=True)
    targets = {f"{k}.csv": v for k, v in MAP_FILES.items()}
    targets.update({f"{k}.xlsx": v for k, v in WAGE_FILES.items()})
    for fname, url in targets.items():
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path) and os.path.getsize(path) > 0:
            print(f"  [skip] {fname} (取得済み)")
            continue
        print(f"  [get ] {fname} <- {url}")
        r = requests.get(url, headers=UA, timeout=60, allow_redirects=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)


# ----------------------------------------------------------------------------
# 指標の個別指数(0.00〜1.00)を計算するヘルパー
# ----------------------------------------------------------------------------
def cap(x):
    """1.00を超えたら1.00に丸める（負値は0.00）。"""
    if pd.isna(x):
        return float("nan")
    return max(0.0, min(float(x), 1.0))


def ratio_index(female_pct):
    """①②③⑥⑦: 指数 = 女性割合% / 男性割合%（男性割合 = 100 - 女性割合）。1.00超は丸め。"""
    if pd.isna(female_pct):
        return float("nan")
    w = float(female_pct)
    if w <= 0:
        return 0.0
    if w >= 100:          # 男性割合0 → ゼロ除算回避、上限1.00
        return 1.0
    return cap(w / (100.0 - w))


def inv_sd_weights(df):
    """
    公式手法(WEF方式)2段階目の逆標準偏差ウェイト wⱼ = (1/sⱼ) / Σ(1/sₖ)。
    sⱼ は各指標の母標準偏差(ddof=0、欠損は除外して算出)。
    分散が小さい(都道府県間/市区町村間で揃っている)指標ほど重みが大きくなる。
    """
    s = df.std(ddof=0)
    s = s.replace(0, float("nan"))  # 分散0は不定 → ウェイト0扱いで除外
    inv = (1.0 / s).fillna(0.0)
    total = inv.sum()
    if total == 0:
        # 全指標が分散0という退化ケース：均等ウェイトにフォールバック
        return pd.Series(1.0 / len(df.columns), index=df.columns)
    return inv / total


def weighted_score(df, w):
    """
    各自治体について、入手できた指標のみで加重平均を算出（欠損指標はウェイトを再正規化）。
    df: 指標値のDataFrame（行=自治体, 列=指標）, w: 指標ごとのウェイト(Series)。
    """
    def row_score(row):
        avail = row.dropna()
        ws = w[avail.index]
        denom = ws.sum()
        if denom == 0:
            return float("nan")
        return float((avail * ws).sum() / denom)
    return df.apply(row_score, axis=1)


def field_aggregate(idx, fields):
    """
    公式手法の分野構造による集約:
      分野内 … 逆標準偏差ウェイトで加重平均（欠損は再正規化して除外）
      分野間 … 均等平均（NaNの分野は除外）
    返り値: (分野別スコアDataFrame, 総合スコアSeries, 分野内ウェイトdict)
    """
    field_scores, field_weights = {}, {}
    for fname, cols in fields.items():
        w = inv_sd_weights(idx[cols])
        field_weights[fname] = w
        field_scores[fname] = weighted_score(idx[cols], w)
    fdf = pd.DataFrame(field_scores)
    total = fdf.mean(axis=1)  # 分野間は均等ウェイト
    return fdf, total, field_weights


def load_map_csv(name):
    """見える化マップの4列CSVを読み、静岡県分のみ {code: row(list)} で返す。"""
    df = pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"), header=None, dtype={0: str})
    df[0] = df[0].str.strip().str.zfill(5)
    df = df[df[0].str.startswith("22")]
    return {r[0]: list(r[1:]) for r in df.itertuples(index=False, name=None)}


def to_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return float("nan")


# ----------------------------------------------------------------------------
# ⑧ 給与の男女差異（Excel）
# ----------------------------------------------------------------------------
def load_wage_index():
    """
    給与Excel（団体名ベース）から「全職員（％）」列（=女性給与/男性給与の0〜1比率）を読み、
    静岡県の各団体名に厳密突合して {code: index} を返す。突合状況をログ出力する。
    列レイアウト: 0=団体名, 7=全職員（％）, 未公表は 'ー'。
    """
    NAME_COL, RATIO_COL = 0, 7
    # 名称 -> code（'清水町（静岡県）'のような県名付き表記も拾う）
    name_to_code = {}
    for code, nm in SHIZUOKA.items():
        name_to_code[nm] = code
        name_to_code[f"{nm}（静岡県）"] = code

    result, matched_names = {}, set()
    for key in WAGE_FILES:
        path = os.path.join(DATA_DIR, f"{key}.xlsx")
        try:
            df = pd.read_excel(path, header=None)
        except Exception as e:  # パース失敗時も全体は止めない
            print(f"  [warn] {key}.xlsx 読込失敗: {e}")
            continue
        for _, row in df.iterrows():
            nm = str(row[NAME_COL]).strip()
            code = name_to_code.get(nm)
            if code is None or code in result:
                continue
            v = to_float(row[RATIO_COL])  # 0〜1の比率（女性/男性）
            if not pd.isna(v):
                result[code] = cap(v)     # 1.00超は丸め
                matched_names.add(SHIZUOKA[code])

    print(f"  ⑧給与: 静岡県35団体中 {len(result)} 団体で公表データを突合")
    missing = [nm for c, nm in SHIZUOKA.items() if c not in result]
    if missing:
        print(f"  ⑧給与: 未突合(未公表/欠損) {len(missing)}団体: {' '.join(missing)}")
    return result


# ----------------------------------------------------------------------------
# メイン
# ----------------------------------------------------------------------------
def main():
    print("1) データダウンロード ...")
    download_all()

    print("2) 見える化マップCSV 読込（静岡県分） ...")
    giin = load_map_csv("giin")
    kanri = load_map_csv("kanrishoku")
    shingi = load_map_csv("shingikai")
    ikuji = load_map_csv("dansei_ikujikyugyo")
    shicho = load_map_csv("shicho")
    bousai = load_map_csv("bousai")
    jichi = load_map_csv("jichikaicho")

    print("3) 給与Excel 読込（⑧） ...")
    wage = load_wage_index()

    print("4) 1段階目: 指標ごとの個別指数 R̃=min(1, 女性/男性) を計算 ...")
    INDS = ["①議員", "②管理職", "③審議会", "④男性育休",
            "⑤首長", "⑥防災", "⑦自治会長", "⑧給与"]
    recs = []
    for code in sorted(SHIZUOKA):
        name = SHIZUOKA[code]

        # ①②③⑥⑦: 女性割合% から R̃ = min(1, 女性数/男性数)（女性割合% は4列CSVの末尾列）
        i1 = ratio_index(to_float(giin[code][2])) if code in giin else float("nan")
        i2 = ratio_index(to_float(kanri[code][2])) if code in kanri else float("nan")
        i3 = ratio_index(to_float(shingi[code][2])) if code in shingi else float("nan")
        i6 = ratio_index(to_float(bousai[code][2])) if code in bousai else float("nan")
        i7 = ratio_index(to_float(jichi[code][2])) if code in jichi else float("nan")

        # ④ 男性育休取得率%。公式は R=男性/女性。女性取得率の市区町村別データが存在しない(404)ため、
        #    便宜的に女性=100%を分母とみなし R̃ = min(1, 男性取得率%/100)。
        i4 = cap(to_float(ikuji[code][2]) / 100.0) if code in ikuji else float("nan")

        # ⑤ 首長/副首長: ランク重み付き男女比（首長:副首長 = 2:1）を min(1,R) で丸め。
        #    首長は副首長より重い。女性=2×女性首長 + 1×女性副首長数、男性=2×男性首長 + 1×男性副首長数。
        #    shicho列: [女性首長(0/1), 男性副首長数, 女性副首長数, 女性副首長比率%]
        if code in shicho:
            r = shicho[code]
            W_MAYOR, W_DEPUTY = 2.0, 1.0
            f_mayor = 1.0 if to_float(r[0]) == 1 else 0.0
            m_dep = to_float(r[1]); m_dep = 0.0 if pd.isna(m_dep) else m_dep
            f_dep = to_float(r[2]); f_dep = 0.0 if pd.isna(f_dep) else f_dep
            women = W_MAYOR * f_mayor + W_DEPUTY * f_dep
            men = W_MAYOR * (1.0 - f_mayor) + W_DEPUTY * m_dep
            i5 = 1.0 if men <= 0 else cap(women / men)  # 男性ポストが無ければ平等扱い(1.0)
        else:
            i5 = float("nan")

        # ⑧ 給与の男女差異（女性給与/男性給与の0〜1比率, min(1,·)で丸め済み）
        i8 = wage.get(code, float("nan"))

        recs.append({
            "自治体コード": code, "市区町村名": name,
            "①議員": i1, "②管理職": i2, "③審議会": i3, "④男性育休": i4,
            "⑤首長": i5, "⑥防災": i6, "⑦自治会長": i7, "⑧給与": i8,
        })

    idx = pd.DataFrame(recs).set_index("自治体コード")

    print("5) 2段階目・3段階目: 分野内を逆SD加重→分野間を均等平均（4分野構造） ...")
    fdf4, score4, fw4 = field_aggregate(idx, FIELDS_4)
    fdf8, score8, fw8 = field_aggregate(idx, FIELDS_8)
    print(f"  [4指標版] 分野: {dict((f, c) for f, c in FIELDS_4.items())}")
    for f, w in fw8.items():
        print(f"  [8指標版] {f}分野内ウェイト:", {k: round(float(v), 3) for k, v in w.items()})

    rows = []
    for code in idx.index:
        s4 = round(float(score4[code]), 2)
        s8 = round(float(score8[code]), 2)
        diff = round(s8 - s4, 2)
        diff = diff + 0.0 if diff == 0 else diff  # -0.0 を 0.0 に正規化
        rec = {
            "自治体コード": code,
            "市区町村名": idx.loc[code, "市区町村名"],
            "4指標版総合スコア": s4,
            "8指標版総合スコア": s8,
            "差分(8指標版-4指標版)": diff,
            "8指標版_使用指標数": int(idx.loc[code, INDS].notna().sum()),
        }
        for f in FIELDS_8:  # 参考: 8指標版の分野別サブスコア
            v = fdf8.loc[code, f]
            rec[f"8指標版_{f}分野"] = ("" if pd.isna(v) else round(float(v), 2))
        for c in INDS:  # 参考: 個別指数
            v = idx.loc[code, c]
            rec[c] = ("" if pd.isna(v) else round(float(v), 2))
        rows.append(rec)

    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"5) 出力完了: {OUTPUT_CSV}（{len(out)}件）")

    # 簡易サマリ（考察用）
    print("\n=== サマリ ===")
    print(f"4指標版 平均スコア: {out['4指標版総合スコア'].mean():.3f}")
    print(f"8指標版 平均スコア: {out['8指標版総合スコア'].mean():.3f}")
    print(f"差分 平均: {out['差分(8指標版-4指標版)'].mean():.3f}")
    up = (out['差分(8指標版-4指標版)'] > 0).sum()
    down = (out['差分(8指標版-4指標版)'] < 0).sum()
    same = (out['差分(8指標版-4指標版)'] == 0).sum()
    print(f"上昇:{up}  下降:{down}  変化なし:{same}（全{len(out)}自治体）")
    return out


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
