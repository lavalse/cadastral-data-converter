# 登記所備付地図データ ビューアー / Cadastral Map Viewer

法務省 登記所備付地図データ（地図XML）を SpatiaLite・PMTiles に変換し、
MapLibre GL JS でブラウザ表示するツールセットです。

A toolset that converts the Ministry of Justice (MOJ) cadastral map XML
into SpatiaLite and PMTiles for display in a browser via MapLibre GL JS.

---

## プロジェクト概要 / Overview

法務省が公開する「登記所備付地図データ」は独自 XML 形式（地図XML）で配布されています。
本プロジェクトはこの XML を解析し、空間データベース（SpatiaLite）とベクタータイル（PMTiles）
に変換したうえで、インタラクティブな地図ビューアーで表示します。

The MOJ distributes cadastral boundary data in a proprietary XML format called 地図XML.
This project parses that XML, reprojects coordinates to WGS84, writes a SpatiaLite
spatial database and vector tiles (PMTiles), and serves them in an interactive map viewer.

---

## データについて / About the Data

### ソース / Source

| 項目 / Item | 内容 / Value |
|---|---|
| 提供元 / Provider | 法務省 登記所備付地図データ 2025年度版 / MOJ cadastral map data 2025 |
| 地域 / Area | 台東区（東京都） / Taito Ward, Tokyo |
| フォーマット / Format | 地図XML（ルート要素 `日本の境界`） / 地図XML (root `日本の境界`) |

### 統計 / Statistics

| 項目 / Item | 数値 / Value |
|---|---|
| XMLファイル数 / XML files | 144 |
| 精確筆ポリゴン / Precise parcels | 52 筆（4 マップ、JGD2000 平面直角→WGS84） |
| 近似筆ポリゴン / Approximate parcels | 51,788 筆（140 マップ、任意座標系） |
| 地区数 / Unique districts | 34（三ノ輪、浅草、谷中、上野 ほか） |

### 座標系について / Coordinate Systems

| 分類 / Type | 説明 / Description | 処理 / Handling |
|---|---|---|
| 北緯線2000X座標系 | JGD2000 平面直角座標系 → EPSG 2443–2461 | pyproj で WGS84 に変換 / reprojected to WGS84 |
| 任意座標系 | ローカル座標（単位 ≈ 1 m）、絶対位置不明 | GSI ジオコーディングで近似配置 / approximately placed via GSI geocoding |

---

## システム構成 / System Architecture

### パイプライン / Pipeline

```
input/*.zip
   ├─ batch.py ──────────────────► output/cadastral.db       (SpatiaLite、精確筆のみ)
   │                               output/cadastral.pmtiles  (ベクタータイル)
   └─ export_viewer_data.py ──────► output/maps_index.json   (全144マップのメタデータ)
                                    output/maps/*.json       (マップごとの筆データ)

georef_approximate.py ────────────► output/geocoded_districts.json  (GSI キャッシュ)
  (output/maps/*.json を読む)        output/approximate.geojson
                                    output/approximate.pmtiles

viewer/server.py ─────────────────► http://localhost:8765/viewer/index.html
```

### ファイル構成 / File Layout

```
cadastral-data-converter/
├── batch.py                    # ZIP/XML → SpatiaLite + PMTiles（精確筆）
├── export_viewer_data.py       # 全筆データ → JSON（リストビュー用）
├── georef_approximate.py       # 任意座標系 → 近似 WGS84 → PMTiles
├── environment.yml             # conda 環境定義
├── converter/
│   ├── crs.py                  # CRS 名 → EPSG コード変換テーブル
│   ├── parser.py               # 地図XML → ParsedFile
│   ├── geometry.py             # 座標変換（平面直角 → WGS84）
│   ├── db.py                   # SpatiaLiteWriter
│   └── tiles.py                # tippecanoe 呼び出し → PMTiles
├── viewer/
│   ├── index.html              # 地図ビューアー（MapLibre GL JS）
│   ├── list.html               # 筆一覧ビューアー
│   ├── server.py               # Range リクエスト対応 HTTP サーバー
│   └── approximate.pmtiles     # → ../output/approximate.pmtiles へのシンボリックリンク
├── input/                      # 入力 ZIP ファイル置き場
└── output/
    ├── cadastral.db            # SpatiaLite 空間データベース（6.8 MB）
    ├── cadastral.pmtiles       # 精確筆ベクタータイル（29 KB）
    ├── approximate.pmtiles     # 近似筆ベクタータイル（11 MB）
    ├── maps_index.json         # 全マップのメタデータ索引（40 KB）
    ├── geocoded_districts.json # GSI ジオコーディングキャッシュ
    └── maps/                   # マップごとの JSON（144 ファイル）
```

---

## 前提条件 / Prerequisites

### conda / miniforge

[miniforge](https://github.com/conda-forge/miniforge) をインストールしてください。
Miniconda または Anaconda でも動作しますが、`conda-forge` チャンネルが必要です。

Install [miniforge](https://github.com/conda-forge/miniforge) (or Miniconda/Anaconda
with the `conda-forge` channel enabled).

### 環境構築 / Create the environment

```bash
conda env create -f environment.yml
# 環境名: geo  /  Environment name: geo
```

主な依存パッケージ / Key packages:

| パッケージ | バージョン | 用途 |
|---|---|---|
| python | 3.11 | ランタイム |
| pyproj | ≥3.7 | 座標変換 / CRS reprojection |
| shapely | ≥2.0 | ジオメトリ演算 / geometry ops |
| fiona | ≥1.10 | GeoJSON 入出力 |
| lxml | ≥5.0 | XML 解析 / XML parsing |
| gdal | ≥3.8 | 空間データ処理 |
| libspatialite | ≥5.0 | SpatiaLite 拡張 |
| tippecanoe | ≥2.0 | PMTiles 生成 / PMTiles generation |
| click | ≥8.0 | CLI |
| xmltodict | ≥1.0 | XML → dict 変換 |

---

## クイックスタート / Quick Start

以下の手順でデータを変換してビューアーを起動します。
Follow these steps to convert data and launch the viewer.

**0. 環境を有効化 / Activate the environment**

```bash
conda activate geo
```

**1. 入力データを配置 / Place input ZIPs**

法務省または geospatial.jp から取得した ZIP ファイルを `input/` に置いてください。

Download MOJ cadastral ZIP files (e.g. from geospatial.jp) and place them in `input/`.

```bash
ls input/
# 例: 13106-0105-2025.zip  13106-0106-2025.zip  ...
```

**2. 精確筆を変換 / Convert precise parcels**

```bash
/home/red/miniforge3/envs/geo/bin/python3 batch.py input/ -o output/
```

出力 / Outputs:
- `output/cadastral.db` — SpatiaLite データベース
- `output/cadastral.pmtiles` — ベクタータイル（精確筆）

**3. リストビュー用データを書き出し / Export list-view data**

```bash
/home/red/miniforge3/envs/geo/bin/python3 export_viewer_data.py
```

出力 / Outputs:
- `output/maps_index.json`
- `output/maps/*.json`（144 ファイル）

**4. 近似筆を生成 / Generate approximate parcels**

任意座標系のマップを GSI ジオコーディングで近似配置します（初回はAPIアクセスあり）。

Geocodes arbitrary-CRS maps via the GSI API (network access on first run).

```bash
/home/red/miniforge3/envs/geo/bin/python3 georef_approximate.py
```

出力 / Outputs:
- `output/geocoded_districts.json`（キャッシュ / cache）
- `output/approximate.pmtiles`

**5. ビューアーを起動 / Start the viewer**

PMTiles は HTTP Range リクエストが必要なため、付属のサーバーを使います。

PMTiles requires HTTP Range requests; use the bundled server.

```bash
/home/red/miniforge3/envs/geo/bin/python3 viewer/server.py
# → http://localhost:8765/viewer/index.html
```

ブラウザで `http://localhost:8765/viewer/index.html` を開いてください。

Open `http://localhost:8765/viewer/index.html` in your browser.

---

## 地図の見方 / Using the Map

### レイヤー凡例 / Layer Legend

| 表示 / Display | 説明 / Description |
|---|---|
| 青系の塗り（濃淡） / Blue fill (shades) | 精確筆（JGD2000→WGS84 変換済み） / Precise parcels (JGD2000→WGS84) |
| グレー破線 / Gray dashed outline | 近似筆（任意座標系、GSI ジオコーディング配置） / Approximate parcels (arbitrary CRS, GSI-geocoded) |

### 操作方法 / Interactions

- **筆クリック / Click a parcel** — 右上にポップアップが表示されます。地番・地区・丁目・精度クラス・ソースファイルを確認できます。
  Right-side popup shows lot number, district, chome, accuracy class, and source file.
- **近似位置警告 / Approximate warning** — 近似筆のポップアップには ⚠ 近似位置 バナーが表示されます。
  Approximate parcel popups show an ⚠ 近似位置 warning banner.
- **近似レイヤー切替 / Toggle approximate layer** — 画面下部のチェックボックスで近似レイヤーの表示を切り替えられます。
  A checkbox at the bottom toggles the approximate layer on/off.
- **地番ラベル / Lot number labels** — ズームレベル 16 以上で表示されます。
  Lot number labels appear at zoom ≥ 16.

### 一覧ビュー / List View

`http://localhost:8765/viewer/list.html` ではマップ・地区ごとに筆を一覧表示できます。

`http://localhost:8765/viewer/list.html` shows a searchable list of parcels by map and district.

---

## スクリプト詳細 / Scripts Reference

### `batch.py`

ZIP または XML ディレクトリを SpatiaLite + PMTiles に変換します（精確筆のみ）。

Converts ZIP/XML input to SpatiaLite + PMTiles (precise parcels only).

```
Usage: python batch.py [OPTIONS] INPUTS...

Arguments:
  INPUTS          入力 ZIP / XML ファイルまたはディレクトリ

Options:
  -o, --output-dir DIRECTORY   出力ディレクトリ（必須）  [required]
  --db-name TEXT               SpatiaLite ファイル名  [default: cadastral.db]
  --tiles-name TEXT            PMTiles ファイル名  [default: cadastral.pmtiles]
  --no-db                      SpatiaLite 出力をスキップ
  --no-tiles                   PMTiles 出力をスキップ
  --min-zoom INTEGER           PMTiles 最小ズーム  [default: 10]
  --max-zoom INTEGER           PMTiles 最大ズーム  [default: 18]
```

例 / Examples:

```bash
# 単一 ZIP / Single ZIP
python batch.py input/13106-0105-2025.zip -o output/

# ディレクトリ全体 / Entire directory
python batch.py input/ -o output/

# DB のみ（タイル生成スキップ）/ DB only
python batch.py input/ -o output/ --no-tiles

# タイルのみ（DB スキップ）/ Tiles only
python batch.py input/ -o output/ --no-db
```

### `export_viewer_data.py`

`input/` の全 ZIP から全筆（任意座標系を含む）を読み込み、
リストビュー用の JSON を `output/maps/` に書き出します。
引数なし、`input/` と `output/` が作業ディレクトリに必要です。

Reads all ZIPs from `input/` (including arbitrary-CRS files) and writes per-map JSON
to `output/maps/` and a global index to `output/maps_index.json`.
No arguments; must be run from the project root.

```bash
python export_viewer_data.py
```

### `georef_approximate.py`

`output/maps/*.json` を読み込み、任意座標系のマップについて
GSI 住所検索 API で地区の緯度経度を取得し、ローカル座標を近似配置して PMTiles を生成します。
ジオコーディング結果は `output/geocoded_districts.json` にキャッシュされます。

Reads `output/maps/*.json`, geocodes each district via the GSI address-search API,
translates local coordinates (1 unit ≈ 1 m) to WGS84, and writes PMTiles.
Geocoding results are cached in `output/geocoded_districts.json`.

```bash
python georef_approximate.py
```

### `viewer/server.py`

プロジェクトルートからコンテンツを配信する、HTTP Range 対応の簡易サーバーです。
PMTiles クライアントライブラリはバイト範囲リクエストを使用するため必須です。

A minimal HTTP server with Range request support, serving from the project root.
Required because PMTiles clients use byte-range requests.

```bash
python viewer/server.py [PORT]   # デフォルト / default: 8765
```

---

## 既知の制限 / Known Limitations

- **近似配置の精度 / Approximate placement accuracy**
  任意座標系のマップは平行移動のみで配置されます。回転・スケール補正は行っていないため、
  実際の向きと異なる場合があります。
  Arbitrary-CRS maps are placed by translation only (no rotation or scale correction).
  Parcel orientation may differ from reality.

- **同一地区内の重複 / Overlapping parcels in same district**
  同じ地区に複数のマップが存在する場合、全マップが同じジオコーディング点を原点として
  配置されるため、ポリゴンが重なります。
  When multiple maps share the same district, all are anchored to the same geocoded
  point and their polygons overlap.

- **対象地域 / Coverage**
  現在のデータは台東区のみです。`input/` に他の地域の ZIP を追加することで拡張できます。
  The current dataset covers Taito Ward only. Add ZIPs for other areas to `input/` to extend coverage.

- **精確筆の少なさ / Few precise parcels**
  144 マップ中 4 マップのみが JGD2000 平面直角座標系を使用しており、精確に配置できるのは 52 筆です。
  Only 4 of 144 maps use JGD2000 plane rectangular coordinates; only 52 parcels are precisely placed.

---

## SpatiaLite スキーマ / SpatiaLite Schema

テーブル名: `parcels`

| カラム / Column | 型 / Type | 説明 / Description |
|---|---|---|
| `parcel_id` | TEXT | 筆 ID |
| `source_file` | TEXT | 元 XML ファイル名 |
| `city_code` | TEXT | 市区町村コード |
| `city_name` | TEXT | 市区町村名 |
| `map_name` | TEXT | マップ名 |
| `lot_number` | TEXT | 地番 |
| `lot_number_sub` | TEXT | 地番サブ |
| `registered_land_use` | TEXT | 登記地目 |
| `statistical_land_use` | TEXT | 統計地目 |
| `parcel_number` | TEXT | 筆番号 |
| `shape_class` | TEXT | 形状クラス |
| `owner_type` | TEXT | 所有者種別 |
| `geom` | MULTIPOLYGON SRID=4326 | ジオメトリ（WGS84） |

---

## ライセンス / License

変換スクリプト: MIT ライセンス。
元データは法務省の利用規約に従ってください。

Converter scripts: MIT License.
Source data: subject to the MOJ terms of use.
