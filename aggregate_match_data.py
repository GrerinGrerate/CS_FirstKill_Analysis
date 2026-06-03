# aggregate_match_data.py
# 聚合 basic_info、first_kills、matches_logs 三个数据源，生成每场比赛的完整结构化数据集

import json
import re
from pathlib import Path

MAX_ROUNDS = 24

# ──────────────────────────────────────────────────────────────
#  武器规范化
# ──────────────────────────────────────────────────────────────

# 从 weapon_src URL 中提取资产 ID（去掉目录、'equipment' 前缀和 '.png' 后缀）
def _weapon_id_from_src(src):
    fn = src.rstrip('/').split('/')[-1]
    if fn.endswith('.png'):
        fn = fn[:-4]
    if fn.startswith('equipment'):
        fn = fn[len('equipment'):]
    return fn

# 构建多键武器名查找表：asset_id / hltv_name → real_name
def build_weapon_lookup(weapon_list):
    lookup = {}
    for w in weapon_list:
        real = w.get('real_name', '')
        if not real:
            continue
        if w.get('weapon'):
            lookup[w['weapon']] = real
        if w.get('hltv_name'):
            lookup[w['hltv_name'].lower()] = real
        lookup[real.lower()] = real
    return lookup

# 将击杀条目的武器字段规范化为 real_name
def normalize_weapon(kill_entry, weapon_lookup):
    src = kill_entry.get('weapon_src', '')
    if src:
        wid = _weapon_id_from_src(src)
        if wid in weapon_lookup:
            return weapon_lookup[wid]
    raw_w = kill_entry.get('weapon', '')
    return weapon_lookup.get(raw_w.lower(), raw_w)

# ──────────────────────────────────────────────────────────────
#  日志回合解析
# ──────────────────────────────────────────────────────────────

# 从 round_start 的 raw 字段提取回合编号（"第N回合开始"）
def _extract_round_num(raw):
    m = re.search(r'第(\d+)回合', raw or '')
    return int(m.group(1)) if m else None

# 解析已反转的日志条目，输出按回合组织的击杀和结果列表
# 核心规则：
#   round_start → 开启新回合（若上一回合未见 round_end 则合成关闭）
#   round_end   → 关闭当前回合（若无当前回合则基于上一回合编号+1合成开启再关闭）
#   kill        → 属于当前回合；若当前无回合（两个标记之间）则归属上一回合
def parse_rounds(entries, weapon_lookup):
    rounds = []
    cur = None       # 当前开放中的回合 dict

    def _open_round(rnum):
        nonlocal cur
        cur = {
            'round_num': rnum,
            'kills': [],
            'winner_side': None,
            't_score': None,
            'ct_score': None,
            'win_condition': None
        }

    def _close_round(end_entry=None):
        nonlocal cur
        if cur is None:
            return
        if end_entry:
            cur['winner_side']  = end_entry.get('winner_side')
            cur['t_score']      = end_entry.get('t_score')
            cur['ct_score']     = end_entry.get('ct_score')
            cur['win_condition']= end_entry.get('win_condition')
        rounds.append(cur)
        cur = None

    for entry in entries:
        etype = entry.get('type')

        if etype == 'round_start':
            # 上一回合若从未收到 round_end，合成关闭
            if cur is not None:
                _close_round()
            rnum = _extract_round_num(entry.get('raw', ''))
            # 若解析失败，按上一回合编号 +1 推断
            if rnum is None:
                rnum = (rounds[-1]['round_num'] + 1) if rounds else 1
            _open_round(rnum)

        elif etype == 'round_end':
            if cur is not None:
                _close_round(entry)
            else:
                # round_end 前没有 round_start：合成一个回合再关闭
                prev_rnum = rounds[-1]['round_num'] if rounds else 0
                _open_round(prev_rnum + 1)
                _close_round(entry)

        elif etype == 'kill':
            kill_data = {
                'killer':       entry.get('attacker', ''),
                'killer_side':  entry.get('attacker_side', ''),
                'weapon':       normalize_weapon(entry, weapon_lookup),
                'victim':       entry.get('victim', ''),
                'victim_side':  entry.get('victim_side', '')
            }
            if cur is not None:
                cur['kills'].append(kill_data)
            elif rounds:
                # round_end 后、round_start 前的击杀归属于上一回合
                rounds[-1]['kills'].append(kill_data)

        # player_join / player_leave 等其余类型忽略

    # 文件末尾未正常关闭的回合合成关闭
    if cur is not None:
        _close_round()

    return rounds

# ──────────────────────────────────────────────────────────────
#  数据加载工具
# ──────────────────────────────────────────────────────────────

def _load_jsonl(path, key_fn):
    lookup = {}
    with Path(path).open('r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            k = key_fn(obj)
            if k is not None:
                lookup[str(k)] = obj
    return lookup

# ──────────────────────────────────────────────────────────────
#  主逻辑
# ──────────────────────────────────────────────────────────────

def main():
    basic_info_path   = Path('dataset/basic_info.jsonl')
    first_kills_path  = Path('dataset/first_kills.jsonl')
    logs_path         = Path('dataset/matches_logs.jsonl')
    weapon_names_path = Path('dataset/weapon_names.json')
    output_path       = Path('dataset/aggregated_matches.jsonl')

    weapon_list   = json.loads(weapon_names_path.read_text(encoding='utf-8'))
    weapon_lookup = build_weapon_lookup(weapon_list)

    basic_by_map    = _load_jsonl(basic_info_path,  lambda o: o.get('metadata', {}).get('map_id'))
    fk_by_map       = _load_jsonl(first_kills_path, lambda o: o.get('metadata', {}).get('map_id'))
    logs_by_series  = _load_jsonl(logs_path,         lambda o: o.get('series_id'))

    print(f'>>> basic_info:   {len(basic_by_map)} 场')
    print(f'>>> first_kills:  {len(fk_by_map)} 场')
    print(f'>>> matches_logs: {len(logs_by_series)} 场')

    matched = skipped = 0

    with output_path.open('w', encoding='utf-8') as out_f:
        for map_id, basic_obj in basic_by_map.items():
            if basic_obj.get('status') != 'ok':
                skipped += 1
                continue

            meta       = basic_obj['metadata']
            series_id  = str(meta.get('series_id', ''))
            log_obj    = logs_by_series.get(series_id)
            fk_obj     = fk_by_map.get(map_id)

            if not log_obj or log_obj.get('status') != 'ok':
                skipped += 1
                continue

            # 反转日志条目，按时序解析回合
            entries      = list(reversed(log_obj['entries']))
            parsed_rounds = parse_rounds(entries, weapon_lookup)

            # round_num → first_kill 坐标查找表（来自 first_kills.jsonl）
            fk_coords = {}
            if fk_obj and fk_obj.get('status') == 'ok':
                for r in fk_obj['data'].get('rounds', []):
                    kills = r.get('kills', [])
                    if kills:
                        fk_coords[r['round_num']] = kills[0]

            # 组装前 MAX_ROUNDS 回合
            rounds_out = []
            for r in parsed_rounds:
                rnum = r['round_num']
                if rnum is None or rnum > MAX_ROUNDS:
                    continue

                kills = r['kills']
                fk_info = fk_coords.get(rnum, {})

                # 首杀：以 matches_logs 为主，补充 first_kills 坐标
                if kills:
                    fk_raw = kills[0]
                    first_kill = {
                        'killer':      fk_raw['killer'],
                        'killer_side': fk_raw['killer_side'],
                        'killer_pos':  fk_info.get('killer_pos'),
                        'weapon':      fk_raw['weapon'],
                        'victim':      fk_raw['victim'],
                        'victim_side': fk_raw['victim_side'],
                        'victim_pos':  fk_info.get('victim_pos')
                    }
                elif fk_info:
                    # 该回合仅 first_kills 有数据（matches_logs 缺失此回合击杀）
                    first_kill = {
                        'killer':      fk_info.get('killer'),
                        'killer_side': None,
                        'killer_pos':  fk_info.get('killer_pos'),
                        'weapon':      fk_info.get('weapon'),
                        'victim':      fk_info.get('victim'),
                        'victim_side': None,
                        'victim_pos':  fk_info.get('victim_pos')
                    }
                else:
                    first_kill = None

                rounds_out.append({
                    'round_num':    rnum,
                    'first_kill':   first_kill,
                    'other_kills':  [
                        {
                            'killer':      k['killer'],
                            'killer_side': k['killer_side'],
                            'weapon':      k['weapon'],
                            'victim':      k['victim'],
                            'victim_side': k['victim_side']
                        }
                        for k in kills[1:]
                    ],
                    'winner_side':  r['winner_side'],
                    't_score':      r['t_score'],
                    'ct_score':     r['ct_score'],
                    'win_condition': r['win_condition']
                })

            # 经济数据裁剪至前 MAX_ROUNDS 回合
            economy_raw = basic_obj['data'].get('economy', {})
            economy = {k: v for k, v in economy_raw.items() if int(k) <= MAX_ROUNDS}

            out_obj = {
                'metadata': {
                    'series_id':  meta['series_id'],
                    'event_name': meta['event_name'],
                    'map_id':     meta['map_id'],
                    'match_name': meta['match_name']
                },
                'players':  basic_obj['data']['players'],
                'economy':  economy,
                'rounds':   rounds_out
            }

            out_f.write(json.dumps(out_obj, ensure_ascii=False) + '\n')
            matched += 1

    print(f'>>> 已生成 {matched} 场，跳过 {skipped} 场')
    print(f'>>> 输出文件：{output_path}')

if __name__ == '__main__':
    main()
