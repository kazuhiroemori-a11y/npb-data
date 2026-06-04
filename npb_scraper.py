#!/usr/bin/env python3
"""
NPB Sabermetrics Data Scraper
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
baseballdata.jp からNPBデータを取得してJSONとして保存します。
ダッシュボードのArtifact（Anthropic Artifact persistent storage）に
データをセットする前段として使用してください。

【セットアップ】
  pip install requests beautifulsoup4

【実行方法】
  # 今年度（デフォルト）
  python3 npb_scraper.py

  # 特定年度
  python3 npb_scraper.py --year 2025

  # 2025・2026 両年度を取得
  python3 npb_scraper.py --both

  # 出力先を指定
  python3 npb_scraper.py --output /var/www/html/npb_data.json

【深夜0時のcron設定例】
  # 試合がある日の翌日0時30分に自動実行（3〜10月の毎日）
  30 0 3-10 * * /usr/bin/python3 /home/user/npb_scraper.py >> /var/log/npb_scraper.log 2>&1

  # 年間を通じて毎日実行（オフシーズンはデータが変わらないが安全側）
  30 0 * * * /usr/bin/python3 /home/user/npb_scraper.py >> /var/log/npb_scraper.log 2>&1
"""

import json
import datetime
import time
import re
import sys
import argparse
from pathlib import Path
from typing import Optional, Any

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("依存パッケージがインストールされていません:")
    print("  pip install requests beautifulsoup4")
    sys.exit(1)

# ─── 設定 ──────────────────────────────────────────────────────────────────────

BASE_URL = "https://baseballdata.jp"
OUTPUT_FILE = Path(__file__).parent / "npb_data.json"
REQUEST_INTERVAL = 1.5  # リクエスト間隔（秒）。サーバー負荷軽減のため

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
}

# チーム名の正規化マップ（サイトの表記ゆれ対応）
TEAM_NORMALIZE = {
    "巨人": "G", "読売": "G", "ジャイアンツ": "G",
    "ヤクルト": "S", "スワローズ": "S",
    "DeNA": "DB", "ＤｅＮＡ": "DB", "横浜": "DB", "ベイスターズ": "DB",
    "中日": "D", "ドラゴンズ": "D",
    "阪神": "T", "タイガース": "T",
    "広島": "C", "カープ": "C",
    "西武": "L", "ライオンズ": "L",
    "日本ハム": "F", "ファイターズ": "F",
    "ロッテ": "M", "マリーンズ": "M",
    "オリックス": "Bu", "バファローズ": "Bu",
    "ソフトバンク": "H", "ホークス": "H",
    "楽天": "E", "イーグルス": "E",
}


# ─── ユーティリティ ────────────────────────────────────────────────────────────

def safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(re.sub(r"[^\d\-]", "", str(val).strip()) or "0") or None
    except Exception:
        return None


def safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.\-]", "", str(val).strip())
        return float(cleaned) if cleaned and cleaned != "." else None
    except Exception:
        return None


def normalize_team(name: str) -> str:
    """チーム名を統一IDに変換。不明なものはそのまま返す。"""
    name = name.strip()
    for key, val in TEAM_NORMALIZE.items():
        if key in name:
            return val
    return name


def fetch_page(url: str, retries: int = 3) -> Optional[BeautifulSoup]:
    """指定URLをフェッチしてBeautifulSoupを返す。失敗時はNone。"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            # 文字コード検出
            if resp.encoding and resp.encoding.lower() in ("utf-8", "utf8"):
                text = resp.text
            else:
                text = resp.content.decode("utf-8", errors="replace")
            return BeautifulSoup(text, "html.parser")
        except requests.RequestException as e:
            print(f"  [警告] {url} (試行{attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(3)
    return None


def extract_table_data(table) -> tuple[list[str], list[list[str]]]:
    """tableタグからヘッダーとデータ行を抽出する"""
    rows = table.find_all("tr")
    if not rows:
        return [], []

    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    data = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        row_data = [c.get_text(strip=True) for c in cells]
        row_links = [c.find("a") for c in cells]
        # リンクテキストを優先（チーム名・選手名のため）
        row_data_with_links = []
        for i, (text, link) in enumerate(zip(row_data, row_links)):
            row_data_with_links.append(link.get_text(strip=True) if link else text)
        data.append(row_data_with_links)

    return headers, data


# ─── 順位表パーサー ────────────────────────────────────────────────────────────

def parse_standings_from_page(soup: BeautifulSoup) -> dict:
    """トップページから順位表を解析する"""
    result = {"central": [], "pacific": []}

    tables = soup.find_all("table")
    league_tables = []

    for table in tables:
        headers, data = extract_table_data(table)
        header_text = " ".join(headers)

        # 順位表判定: 勝・敗・率が含まれているか
        if not all(k in header_text for k in ["勝", "敗", "率"]):
            continue
        if len(data) < 3:  # 最低3チーム以上
            continue

        league_tables.append((headers, data))

    for idx, (headers, data) in enumerate(league_tables[:2]):  # セ・パ最大2テーブル
        league_key = "central" if idx == 0 else "pacific"
        entries = []

        for row in data:
            if len(row) < 6:
                continue
            # 順位が数字かチェック
            rank_str = re.sub(r"[^\d]", "", row[0])
            if not rank_str:
                continue

            entry = {
                "rank":  safe_int(row[0]),
                "team":  row[1],
                "teamId": normalize_team(row[1]),
                "g":     safe_int(row[2]),
                "w":     safe_int(row[3]),
                "l":     safe_int(row[4]),
                "d":     safe_int(row[5]),
                "pct":   safe_float(row[6]),
                "era":   safe_float(row[9])  if len(row) > 9  else None,
                "avg":   safe_float(row[10]) if len(row) > 10 else None,
                "hr":    safe_int(row[11])   if len(row) > 11 else None,
                "sb":    safe_int(row[12])   if len(row) > 12 else None,
                "rs":    safe_int(row[13])   if len(row) > 13 else None,
                "ra":    safe_int(row[14])   if len(row) > 14 else None,
            }

            if entry["team"] and entry["rank"]:
                entries.append(entry)

        result[league_key] = entries

    return result


# ─── 打撃セイバーメトリクスパーサー ──────────────────────────────────────────────

def parse_batting_sabr(soup: BeautifulSoup, league: str) -> list:
    """打撃セイバーメトリクスページを解析する"""
    result = []
    tables = soup.find_all("table")

    for table in tables:
        headers, data = extract_table_data(table)
        header_text = " ".join(headers)

        # セイバー打撃テーブル判定
        if not any(k in header_text for k in ["NOI", "GPA", "BABIP", "IsoD"]):
            continue

        for i, row in enumerate(data):
            if len(row) < 5:
                continue

            # 選手名（"1:佐藤 輝明" → "佐藤 輝明"）
            name_raw = row[0]
            name = re.sub(r"^\d+[:：]?\s*", "", name_raw).strip()
            if not name:
                continue

            entry = {
                "id":     i + 1,
                "name":   name,
                "team":   row[1],
                "teamId": normalize_team(row[1]),
                "league": league,
                "avg":    safe_float(row[2]) if len(row) > 2 else None,
                "hr":     safe_int(row[3])   if len(row) > 3 else None,
                "rbi":    safe_int(row[4])   if len(row) > 4 else None,
            }

            # ヘッダーに対応する値を全て取得
            for j, h in enumerate(headers):
                if j >= len(row):
                    break
                if h not in ("選手名", "球　団", "球団", "率", "本", "点"):
                    val = safe_float(row[j])
                    if val is not None:
                        entry[h] = val

            result.append(entry)

    return result


# ─── 投手セイバーメトリクスパーサー ──────────────────────────────────────────────

def parse_pitching_sabr(soup: BeautifulSoup, league: str) -> list:
    """投手セイバーメトリクスページを解析する"""
    result = []
    tables = soup.find_all("table")

    for table in tables:
        headers, data = extract_table_data(table)
        header_text = " ".join(headers)

        # セイバー投手テーブル判定
        if not any(k in header_text for k in ["WHIP", "防御率", "ERA", "FIP", "K/BB"]):
            continue

        for i, row in enumerate(data):
            if len(row) < 5:
                continue

            name_raw = row[0]
            name = re.sub(r"^\d+[:：]?\s*", "", name_raw).strip()
            if not name:
                continue

            entry = {
                "id":     i + 1,
                "name":   name,
                "team":   row[1],
                "teamId": normalize_team(row[1]),
                "league": league,
            }

            for j, h in enumerate(headers):
                if j >= len(row):
                    break
                if h not in ("選手名", "球　団", "球団"):
                    val = safe_float(row[j])
                    if val is not None:
                        entry[h] = val

            result.append(entry)

    return result


# ─── URLビルダー ───────────────────────────────────────────────────────────────

def build_urls(year: int) -> dict:
    """年度に対応したURLを生成する"""
    current_year = datetime.datetime.now().year
    if year == current_year:
        base = BASE_URL
    else:
        base = f"{BASE_URL}/{year}"

    return {
        "home":         f"{base}/index.html",
        "sabr_c_bat":   f"{base}/sabr/cNOI.html",
        "sabr_p_bat":   f"{base}/sabr/pNOI.html",
        "sabr_c_pitch": f"{base}/sabr/cHIDARITU.html",
        "sabr_p_pitch": f"{base}/sabr/pHIDARITU.html",
        "basic_c_bat":  f"{base}/ctop.html",
        "basic_p_bat":  f"{base}/ptop.html",
    }


# ─── メインスクレイプ関数 ─────────────────────────────────────────────────────

def scrape_year(year: int) -> dict:
    """指定年度のデータを全ページから取得する"""
    print(f"\n[{year}年度] スクレイピング開始")
    urls = build_urls(year)

    result = {
        "year":       year,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "standings":  {"central": [], "pacific": []},
        "batters":    [],
        "pitchers":   [],
        "meta": {
            "source": BASE_URL,
            "pages_fetched": 0,
            "errors": [],
        }
    }

    pages = [
        ("home",         "順位表"),
        ("sabr_c_bat",   "セ・リーグ打撃SABR"),
        ("sabr_p_bat",   "パ・リーグ打撃SABR"),
        ("sabr_c_pitch", "セ・リーグ投手SABR"),
        ("sabr_p_pitch", "パ・リーグ投手SABR"),
    ]

    for key, label in pages:
        url = urls[key]
        print(f"  取得中: {label} ... ", end="", flush=True)

        soup = fetch_page(url)
        if soup is None:
            print("失敗")
            result["meta"]["errors"].append({"page": key, "url": url})
            time.sleep(REQUEST_INTERVAL)
            continue

        result["meta"]["pages_fetched"] += 1

        if key == "home":
            standings = parse_standings_from_page(soup)
            result["standings"] = standings
            c = len(standings["central"])
            p = len(standings["pacific"])
            print(f"OK（セ{c}チーム, パ{p}チーム）")

        elif key in ("sabr_c_bat", "sabr_p_bat"):
            league = "セ" if key == "sabr_c_bat" else "パ"
            batters = parse_batting_sabr(soup, league)
            result["batters"].extend(batters)
            print(f"OK（{len(batters)}名）")

        elif key in ("sabr_c_pitch", "sabr_p_pitch"):
            league = "セ" if key == "sabr_c_pitch" else "パ"
            pitchers = parse_pitching_sabr(soup, league)
            result["pitchers"].extend(pitchers)
            print(f"OK（{len(pitchers)}名）")

        time.sleep(REQUEST_INTERVAL)

    return result


# ─── エントリーポイント ────────────────────────────────────────────────────────

def get_current_season_year() -> int:
    """現在のNPBシーズン年度を返す（1〜2月は前年扱い）"""
    now = datetime.datetime.now()
    return now.year if now.month >= 3 else now.year - 1


def main():
    parser = argparse.ArgumentParser(
        description="NPBセイバーメトリクス データスクレイパー"
    )
    parser.add_argument(
        "--year", type=int, default=None,
        help="取得年度（デフォルト: 現在のシーズン年度）"
    )
    parser.add_argument(
        "--both", action="store_true",
        help="2025・2026 両年度を取得"
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help=f"出力JSONファイルパス（デフォルト: {OUTPUT_FILE}）"
    )
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_FILE

    # 取得年度を決定
    if args.both:
        years = [2025, 2026]
    elif args.year:
        years = [args.year]
    else:
        years = [get_current_season_year()]

    # 既存データを読み込み（年度別に保持）
    all_data: dict = {}
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
            print(f"既存データを読み込みました: {output_path}")
        except Exception as e:
            print(f"[警告] 既存データの読み込みに失敗: {e}")

    # スクレイピング実行
    start = datetime.datetime.now()
    for year in years:
        data = scrape_year(year)
        all_data[str(year)] = data
        print(f"\n  [{year}年度] 完了: "
              f"打者{len(data['batters'])}名, "
              f"投手{len(data['pitchers'])}名, "
              f"エラー{len(data['meta']['errors'])}件")

    # JSON出力
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    elapsed = (datetime.datetime.now() - start).total_seconds()
    print(f"\n━━━ 完了 ━━━")
    print(f"保存先: {output_path}")
    print(f"所要時間: {elapsed:.1f}秒")
    print(f"\n次のステップ:")
    print(f"  生成された {output_path.name} の内容をダッシュボードの")
    print(f"  「データをインポート」機能からペーストしてください。")


if __name__ == "__main__":
    main()
