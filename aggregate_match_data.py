# aggregate_match_data.py
# 聚合 basic_info、first_kills、matches_logs 三个数据源，生成每场比赛的完整结构化数据集

import json
import re
from pathlib import Path

MAX_ROUNDS = 24

# 从 round_start 的 raw 字段提取回合编号（"第N回合开始"）
def _extract_round_num(raw):
    m = re.search(r'第(\d+)回合', raw or '')
    return int(m.group(1)) if m else None

# 以下四个函数共享一个 state dict：{'rounds': list, 'cur': dict|None}
def _new_round_dict(rnum):
    return {'round_num': rnum, 'kills': [],
            'winner_side': None, 't_score': None,
            'ct_score': None, 'win_condition': None}

def _finalize_round(state, end_entry=None):
    if state['cur'] is None:
        return
    if end_entry:
        # matches_logs 中 winner_side 字段全部错误存成了 'T'，需从 raw 重新提取
        raw = end_entry.get('raw', '')
        m = re.search(r'(CT|T)获胜', raw)
        winner_side = m.group(1) if m else end_entry.get('winner_side')
        # matches_logs 中分数格式为"获胜方:失败方"，CT获胜时两列互换需纠正
        t_score  = end_entry.get('t_score')
        ct_score = end_entry.get('ct_score')
        if winner_side == 'CT' and t_score is not None and ct_score is not None:
            t_score, ct_score = ct_score, t_score
        state['cur'].update({
            'winner_side':   winner_side,
            't_score':       t_score,
            'ct_score':      ct_score,
            'win_condition': end_entry.get('win_condition'),
        })
    state['rounds'].append(state['cur'])
    state['cur'] = None

def _on_start(state, entry):
    rnum = _extract_round_num(entry.get('raw', ''))
    half_offset = state.get('half_offset', 0)
    max_rnum = state.get('max_rnum', 0)
    max_in_half = max_rnum - half_offset          # 当前半场内见过的最大原始编号
    if rnum is None:
        rnum = max_in_half + 1
    actual = rnum + half_offset
    if state['cur'] is not None:
        if state['cur']['round_num'] == actual:
            state['cur']['kills'] = []      # 同一回合重开（技术暂停），重置击杀
            return
        _finalize_round(state)
    elif rnum < max_in_half:
        if rnum == 1:
            # 第二半/加时从 1 重新开始：叠加半场偏移
            half_offset = max_rnum
            state['half_offset'] = half_offset
            actual = rnum + half_offset
        else:
            # 回合号向前倒退（日志倒放段）：丢弃，不作为新回合
            return
    elif state['rounds'] and state['rounds'][-1]['round_num'] == actual:
        # 已关闭的同编号回合再次出现（重开轮）：替换上一轮
        state['rounds'].pop()
    # 防止重复写入：若该编号已存在于历史回合中（非相邻），直接丢弃
    if actual < max_rnum and any(r['round_num'] == actual for r in state['rounds']):
        return
    state['max_rnum'] = max(max_rnum, actual)
    state['cur'] = _new_round_dict(actual)

def _on_end(state, entry):
    if state['cur'] is None:
        prev = state['rounds'][-1]['round_num'] if state['rounds'] else 0
        actual = prev + 1
        state['max_rnum'] = max(state.get('max_rnum', 0), actual)
        state['cur'] = _new_round_dict(actual)
    _finalize_round(state, entry)

def _on_kill(state, entry):
    kill_data = {
        'killer':      entry.get('attacker', ''),
        'killer_side': entry.get('attacker_side', ''),
        'weapon':      entry.get('weapon', ''),
        'victim':      entry.get('victim', ''),
        'victim_side': entry.get('victim_side', '')
    }
    if state['cur'] is not None:
        state['cur']['kills'].append(kill_data)
    elif state['rounds']:
        state['rounds'][-1]['kills'].append(kill_data)

# 解析已反转的日志条目，输出按回合组织的击杀和结果列表
# 核心规则：
#   round_start → 开启新回合（若上一回合未见 round_end 则合成关闭）
#   round_end   → 关闭当前回合（若无当前回合则基于上一回合编号+1合成开启再关闭）
#   kill        → 属于当前回合；若当前无回合则归属上一回合（end 后 start 前的击杀）
_DISPATCH = {'round_start': _on_start, 'round_end': _on_end, 'kill': _on_kill}

def parse_rounds(entries):
    state = {'rounds': [], 'cur': None}
    for entry in entries:
        handler = _DISPATCH.get(entry.get('type'))
        if handler:
            handler(state, entry)
    _finalize_round(state)
    return state['rounds']

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

# 从 first_kills 对象中提取有序坐标列表（按 round_num 升序，索引对应第几次首杀）
def _build_fk_list(fk_obj):
    if not fk_obj or fk_obj.get('status') != 'ok':
        return []
    result = []
    for r in sorted(fk_obj['data'].get('rounds', []), key=lambda x: x['round_num']):
        kills = r.get('kills', [])
        if kills:
            result.append(kills[0])
    return result

# 将单个已解析回合与 first_kills 坐标及经济数据合并，生成输出字典
# eco_info 来自 basic_info 的 economy 字段，始终返回 dict（不过滤空回合）
def _build_round_output(r, fk_info, eco_info=None):
    kills = r['kills']
    if kills:
        fk_raw = kills[0]
        first_kill = {
            'killer':      fk_raw['killer'],
            'killer_side': fk_raw['killer_side'],
            'killer_pos':  fk_info.get('killer_pos'),
            'weapon':      fk_raw['weapon'] or fk_info.get('weapon', ''),
            'victim':      fk_raw['victim'],
            'victim_side': fk_raw['victim_side'],
            'victim_pos':  fk_info.get('victim_pos')
        }
    else:
        first_kill = None
    # 若 round_end 缺失，从末刀击杀者阵营推断胜方
    winner_side = r['winner_side']
    if winner_side is None and kills:
        winner_side = kills[-1].get('killer_side') or None
    return {
        'round_num':     r['round_num'],
        'economy':       eco_info,
        'first_kill':    first_kill,
        'other_kills':   [
            {
                'killer':      k['killer'],
                'killer_side': k['killer_side'],
                'weapon':      k['weapon'],
                'victim':      k['victim'],
                'victim_side': k['victim_side']
            }
            for k in kills[1:]
        ],
        'winner_side':   winner_side,
        't_score':       r['t_score'],
        'ct_score':      r['ct_score'],
        'win_condition': r['win_condition']
    }

def _extract_round_numbers(raw_entries):
    rnums = []
    for e in raw_entries:
        if e.get('type') != 'round_start':
            continue
        n = _extract_round_num(e.get('raw', ''))
        if n is None:
            continue
        rnums.append(n)
        if len(rnums) >= 8:
            break
    return rnums

def _trim_leading_half_reset(rnums):
    start = 0
    while start < len(rnums) - 1 and rnums[start] <= 3 and rnums[start + 1] > rnums[start] + 5:
        start += 1
    return rnums[start:]

def _needs_reversal(raw_entries):
    rnums = _extract_round_numbers(raw_entries)
    if len(rnums) < 2:
        return True
    effective = _trim_leading_half_reset(rnums)
    if len(effective) < 2:
        return True
    for prev, curr in zip(effective, effective[1:]):
        if prev != curr:
            return prev > curr   # 降序 → 需要反转
    return True   # 全部相同（如全为 1）→ 默认反转

# 为单场比赛合并三个数据源
def _process_match(basic_obj, log_obj, fk_obj):
    meta = basic_obj['metadata']
    raw_entries = log_obj['entries']
    entries = list(reversed(raw_entries)) if _needs_reversal(raw_entries) else raw_entries
    fk_list = _build_fk_list(fk_obj)
    # 解析日志回合（不做间隙填充，由下方 economy 循环负责补全）
    parsed_rounds = parse_rounds(entries)
    # 按 round_num 索引日志回合，供下方查找
    parsed_by_rnum = {r['round_num']: r for r in parsed_rounds if r['round_num'] is not None}
    # 按日志时序顺序为每个有击杀的回合分配 fk_list 条目（保持 HLTV 顺序对齐）
    fk_idx = 0
    fk_by_rnum = {}
    for r in parsed_rounds:
        if r['kills']:
            if fk_idx < len(fk_list):
                fk_by_rnum[r['round_num']] = fk_list[fk_idx]
            fk_idx += 1
    # 以 economy 字典的回合范围（≤MAX_ROUNDS）为权威，逐回合构建输出
    economy_raw = basic_obj['data'].get('economy', {})
    eco_rnums = [int(k) for k in economy_raw if int(k) <= MAX_ROUNDS]
    max_eco_round = max(eco_rnums) if eco_rnums else 0
    rounds_out = []
    for rnum in range(1, max_eco_round + 1):
        eco_info = economy_raw.get(str(rnum))
        r = parsed_by_rnum.get(rnum, _new_round_dict(rnum))
        fk_info = fk_by_rnum.get(rnum, {})
        rounds_out.append(_build_round_output(r, fk_info, eco_info))
    return {
        'metadata': {
            'series_id':  meta['series_id'],
            'event_name': meta['event_name'],
            'map_id':     meta['map_id'],
            'match_name': meta['match_name']
        },
        'players': basic_obj['data']['players'],
        'rounds':  rounds_out
    }

def main():
    basic_info_path = Path('dataset/basic_info.jsonl')
    first_kills_path = Path('dataset/first_kills.jsonl')
    logs_path = Path('dataset/matches_logs.jsonl')
    output_path = Path('dataset/matches.jsonl')
    basic_by_map = _load_jsonl(basic_info_path, lambda o: o.get('metadata', {}).get('map_id'))
    fk_by_map = _load_jsonl(first_kills_path, lambda o: o.get('metadata', {}).get('map_id'))
    logs_by_series = _load_jsonl(logs_path, lambda o: o.get('series_id'))
    print(f'>>> basic_info:   {len(basic_by_map)} 场')
    print(f'>>> first_kills:  {len(fk_by_map)} 场')
    print(f'>>> matches_logs: {len(logs_by_series)} 场')
    matched = skipped = 0
    with output_path.open('w', encoding='utf-8') as out_f:
        for map_id, basic_obj in basic_by_map.items():
            if basic_obj.get('status') != 'ok':
                skipped += 1
                continue
            meta = basic_obj['metadata']
            log_obj = logs_by_series.get(str(meta.get('series_id', '')))
            fk_obj = fk_by_map.get(map_id)
            if not log_obj or log_obj.get('status') != 'ok':
                skipped += 1
                continue
            out_obj = _process_match(basic_obj, log_obj, fk_obj)
            out_f.write(json.dumps(out_obj, ensure_ascii=False) + '\n')
            matched += 1
    print(f'>>> 已生成 {matched} 场，跳过 {skipped} 场')
    print(f'>>> 输出文件：{output_path}')

if __name__ == '__main__':
    main()
