#!/usr/bin/env python3
"""
JR可部線 時刻表スクレイパー
下り(2659): 広島→あき亀山
上り(2660): あき亀山→広島
"""
import re, json, sys
from datetime import date
try:
    import requests
except ImportError:
    print("pip install requests"); sys.exit(1)

# 平日: パラメータなし / 土休日: 土曜日付を指定
DOWN_URL_WD  = "https://timetable.jr-odekake.net/line-timetable/2659"
UP_URL_WD    = "https://timetable.jr-odekake.net/line-timetable/2660"
DOWN_URL_HOL = "https://timetable.jr-odekake.net/line-timetable/2659?year=2026&month=5&day=31"
UP_URL_HOL   = "https://timetable.jr-odekake.net/line-timetable/2660?year=2026&month=5&day=31"

def parse_cells(row_html):
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL)
    result = []
    for c in cells:
        text = re.sub(r'<[^>]+>', '', c).strip()
        result.append(text)
    return result

def to_time(s):
    """時刻文字列をHH:MM形式に。＝や空欄はNone"""
    s = s.strip()
    if not s or s == '＝' or s == '=':
        return None
    m = re.match(r'(\d{1,2}:\d{2})', s)
    return m.group(1) if m else None

def parse_page(url, direction):
    print(f"Fetching {direction}... ", end='', flush=True)
    resp = requests.get(url, timeout=15)
    resp.encoding = 'utf-8'
    content = resp.text
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', content, re.DOTALL)
    print(f"{len(rows)} rows")

    # 各行をラベルでインデックス化
    row_map = {}
    for row in rows:
        cells = parse_cells(row)
        if cells:
            label = cells[0]
            row_map[label] = cells[1:]  # 0番目はラベル

    # 列車番号（最初のセルが空のものはスキップ）
    train_nos = row_map.get('列車番号', [])
    # 運転日注意: 平=平日のみ、空=毎日
    ops = row_map.get('運転日注意', [])
    # 始発(下り)/終着(上り) - through service検出用
    origin_row = row_map.get('始発', [])
    terminal_row = row_map.get('終着', [])

    # 駅名行を取得（下り/上り で station name → cells マッピング）
    station_keys = {
        'down': {
            'hiroshima':   '広島',
            'ryokui':      '緑井',
            'shichiken':   '七軒茶屋',
            'bairin':      '梅林',
            'uwayagi':     '上八木',
            'akikame':     'あき亀山',
        },
        'up': {
            'akikame':     'あき亀山',
            'uwayagi':     '上八木',
            'bairin':      '梅林',
            'shichiken':   '七軒茶屋',
            'ryokui':      '緑井',
            'hiroshima':   '広島',
        }
    }
    sk = station_keys[direction]

    # 駅ごとの時刻リストを取得
    station_times = {}
    for key, jp_name in sk.items():
        # 行ラベルは「○○ 発」「○○ 着」などが付く。「のりば」行は除外
        for label in row_map:
            if jp_name in label and 'のりば' not in label:
                times = [to_time(t) for t in row_map[label]]
                if any(t is not None for t in times):  # 時刻が存在する行のみ
                    station_times[key] = times
                    break
        if key not in station_times:
            station_times[key] = [None] * len(train_nos)

    # Through service の列車番号を特定
    # 下り: 始発行が "坂 07:47 呉 15:28" のような形式
    # → 広島着時刻でマッチング
    through_hiroshima = set()
    if direction == 'down':
        raw_origin = ' '.join(origin_row)
        # "広 06:20 坂 07:47 呉 15:28 坂 19:50" → 坂・呉の時刻を抽出
        pairs = re.findall(r'([^\d\s:]+)\s+(\d{1,2}:\d{2})', raw_origin)
        for sta, t in pairs:
            if sta not in ('広',):
                through_hiroshima.add(t)
    else:
        raw_terminal = ' '.join(terminal_row)
        pairs = re.findall(r'([^\d\s:]+)\s+(\d{1,2}:\d{2})', raw_terminal)
        for sta, t in pairs:
            if sta not in ('広',):
                through_hiroshima.add(t)

    trains = []
    n = len(train_nos)
    for i in range(n):
        no = train_nos[i] if i < len(train_nos) else ''
        if not no:
            continue

        op = ops[i] if i < len(ops) else ''
        # 平=平日のみ、土休=土休日のみ、空=毎日
        if op == '平':
            day_type = 'weekday'
        elif op == '土休':
            day_type = 'holiday'
        else:
            day_type = 'all'
        weekday_only = (day_type == 'weekday')

        t = {}
        for key in sk:
            val = station_times[key][i] if i < len(station_times.get(key, [])) else None
            t[key] = val

        # Through service 判定
        hiroshima_time = t.get('hiroshima')
        through = hiroshima_time in through_hiroshima if through_hiroshima else False

        # 下り: terminal 判定
        # 梅林に時刻あり→梅林行き, なし→緑井行き（七軒茶屋=＝のもの）
        if direction == 'down':
            if t.get('akikame'):
                terminal = 'あき亀山'
            elif t.get('bairin') is not None:
                terminal = '梅林'
            else:
                terminal = '緑井'
        else:
            # 上り: origin 判定
            if t.get('akikame'):
                origin = 'あき亀山'
            elif t.get('bairin') is not None:
                origin = '梅林'
            else:
                origin = '緑井'

        entry = {
            'no': no,
            'weekday_only': weekday_only,
            'day_type': day_type,
            'through': through,
        }
        if direction == 'down':
            entry['terminal'] = terminal
        else:
            entry['origin'] = origin

        for key in sk:
            entry[key] = t[key]

        trains.append(entry)

    return trains

def main():
    # 平日ダイヤ（平日のみ + 毎日）
    down_wd = parse_page(DOWN_URL_WD, 'down')
    up_wd   = parse_page(UP_URL_WD,   'up')
    # 土休日ダイヤ（土休日のみ + 毎日）- 毎日分は重複するのでday_type='holiday'のみ追加
    down_hol = [t for t in parse_page(DOWN_URL_HOL, 'down') if t['day_type'] == 'holiday']
    up_hol   = [t for t in parse_page(UP_URL_HOL,   'up')   if t['day_type'] == 'holiday']

    # マージして広島発時刻でソート
    def sort_key(t):
        return t.get('hiroshima') or '99:99'

    down = sorted(down_wd + down_hol, key=sort_key)
    up   = sorted(up_wd   + up_hol,   key=lambda t: t.get('akikame') or t.get('bairin') or t.get('ryokui') or '99:99')

    data = {
        'generated': str(date.today()),
        'down': down,
        'up': up,
    }

    out = '/home/taka/デスクトップ/ClaudeCode/kabe-line-app/timetable.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved: {out}")
    print(f"  下り: {len(down)} trains")
    print(f"  上り: {len(up)} trains")

    # サマリー
    down_bairin = [t for t in down if t['terminal'] == '梅林']
    up_bairin   = [t for t in up   if t.get('origin') == '梅林']
    print(f"  梅林行き(下り): {len(down_bairin)} trains")
    print(f"  梅林始発(上り): {len(up_bairin)} trains")

if __name__ == '__main__':
    main()
