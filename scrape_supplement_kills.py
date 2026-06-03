# scrape_supplement_kills.py
# 利用 Demo 的时序数据，以个人坐标视角补全全局重叠的残缺首杀信息

import json
import difflib
from pathlib import Path
from scrapers import (
    setup_driver,
    append_jsonl,
    get_heatmap_coords,
    get_paired_cross_coords,
    get_player_weapons_list
)

# 检查坐标序列是否全为 1
def check_all_ones(coords_data):
    if not coords_data: return False
    return all(int(item.get("count", 1)) == 1 for item in coords_data)

# 模糊匹配 Demo 中的昵称与 HLTV 的真实 Player ID
def match_player_id(demo_name, hltv_players):
    d_lower = demo_name.lower().strip()
    best_match_id = None
    best_score = -1.0
    for pid, h_name in hltv_players.items():
        h_lower = h_name.lower().strip()
        # 第一优先级：子串绝对包含
        if d_lower in h_lower or h_lower in d_lower:
            return pid
        # 第二优先级：计算字符相似度打分
        score = difflib.SequenceMatcher(None, d_lower, h_lower).ratio()
        if score > best_score:
            best_score = score
            best_match_id = pid
    if best_score > 0.3:
        return best_match_id
    return None

# 从 Demo 击杀流中提取各局首杀事件骨架
def extract_first_kills(demo_kills, hltv_players):
    first_kills = []
    current_round = 0
    for k in demo_kills:
        if k["round"] > current_round:
            killer, victim = str(k["killer"]), str(k["victim"])
            if killer.lower() != "nan" and victim.lower() != "nan":
                killer_id = match_player_id(killer, hltv_players)
                victim_id = match_player_id(victim, hltv_players)
                first_kills.append({
                    "round_num": k["round"],
                    "killer_name": killer,
                    "victim_name": victim,
                    "killer_id": killer_id,
                    "victim_id": victim_id,
                    "killer_pos": None,
                    "victim_pos": None,
                    "weapon": "Unknown"
                })
                current_round = k["round"]
    return first_kills

# 将全局坐标中已被阶段二消耗的位置扣除后，按时序兜底填入仍缺失的坐标
def apply_global_fallback(first_kills, fk_raw, fd_raw):
    from collections import Counter
    used_k = Counter(ev['killer_pos'] for ev in first_kills if ev['killer_pos'])
    used_v = Counter(ev['victim_pos'] for ev in first_kills if ev['victim_pos'])
    # 按首次出现的时序展开全局列表，扣除已用份额，保留剩余
    fk_remaining = []
    for item in fk_raw:
        pos, count = item['pos'], item.get('count', 1)
        available = count - used_k.pop(pos, 0)
        if available > 0:
            fk_remaining.extend([pos] * available)
    fd_remaining = []
    for item in fd_raw:
        pos, count = item['pos'], item.get('count', 1)
        available = count - used_v.pop(pos, 0)
        if available > 0:
            fd_remaining.extend([pos] * available)
    events_missing_k = [ev for ev in first_kills if not ev['killer_pos']]
    events_missing_v = [ev for ev in first_kills if not ev['victim_pos']]
    for i, ev in enumerate(events_missing_k):
        if i < len(fk_remaining): ev['killer_pos'] = fk_remaining[i]
    for i, ev in enumerate(events_missing_v):
        if i < len(fd_remaining): ev['victim_pos'] = fd_remaining[i]

# 为已确定坐标的击杀者挂载武器信息
def fill_weapons(driver, first_kills, hltv_players, base_first, base_url):
    for pid in hltv_players.keys():
        k_events_with_pos = [ev for ev in first_kills if ev['killer_id'] == pid and ev['killer_pos']]
        if not k_events_with_pos:
            continue
        weapons = get_player_weapons_list(driver, pid, base_first, base_url)
        for w in weapons:
            w_raw = get_heatmap_coords(driver, f"{base_url}?players={pid}&weapons={pid}-{w}&{base_first}&showKills=true&showDeaths=false&showKillDataset=true&showDeathDataset=false")
            w_poses = {x['pos'] for x in w_raw}
            for ev in k_events_with_pos:
                if ev['killer_pos'] in w_poses:
                    ev['weapon'] = w

# 将事件列表组装为 round_num -> kills 的字典输出
def build_kills_output(first_kills, hltv_players):
    final_output = {}
    for ev in first_kills:
        r = ev["round_num"]
        k_name = hltv_players.get(ev["killer_id"], ev["killer_name"])
        v_name = hltv_players.get(ev["victim_id"], ev["victim_name"])
        final_output[r] = [{
            "kill_id": 1,
            "killer": k_name,
            "killer_pos": ev["killer_pos"] or "Unknown",
            "weapon": ev["weapon"],
            "victim": v_name,
            "victim_pos": ev["victim_pos"] or "Unknown",
            "is_first_kill": True
        }]
    return final_output

# 将一套 c 全为 1 的坐标序列按时序写入对应字段
def _apply_if_clean(coords, events, field):
    if check_all_ones(coords) and len(coords) == len(events):
        for i, ev in enumerate(events):
            if not ev[field]: ev[field] = coords[i]['pos']

# 逐选手从纯净视角填充坐标
def fill_per_player(driver, first_kills, hltv_players, base_first, base_url):
    for pid in hltv_players.keys():
        k_events = [ev for ev in first_kills if ev['killer_id'] == pid]
        d_events = [ev for ev in first_kills if ev['victim_id'] == pid]
        # 作为首杀击杀者的双视角
        if k_events:
            k_cross = get_paired_cross_coords(driver, pid, True, base_first, base_url)
            _apply_if_clean(k_cross.get('killer_coords', []), k_events, 'killer_pos')
            _apply_if_clean(k_cross.get('victim_coords', []), k_events, 'victim_pos')
        # 作为首杀受害者的双视角
        if d_events:
            v_cross = get_paired_cross_coords(driver, pid, False, base_first, base_url)
            _apply_if_clean(v_cross.get('killer_coords', []), d_events, 'killer_pos')
            _apply_if_clean(v_cross.get('victim_coords', []), d_events, 'victim_pos')
        if all(ev['killer_pos'] and ev['victim_pos'] for ev in first_kills):
            break

# 分三阶段提取并挂载首杀坐标
def get_supplement_kills(driver, map_id, match_name, hltv_players, demo_kills):
    first_kills = extract_first_kills(demo_kills, hltv_players)
    n = len(first_kills)
    base_url = f"https://www.hltv.org/stats/matches/heatmap/mapstatsid/{map_id}/{match_name}"
    base_first = "sides=COUNTER_TERRORIST&sides=TERRORIST&firstKillsOnly=true&allowEmpty=true"
    all_p = "&".join([f"players={pid}" for pid in hltv_players.keys()])
    all_w = "&".join([f"weapons={pid}-All" for pid in hltv_players.keys()])
    # 拉取全局首杀和首死坐标
    fk_raw = get_heatmap_coords(driver, f"{base_url}?{all_p}&{all_w}&{base_first}&showKills=true&showDeaths=false&showKillDataset=true&showDeathDataset=false")
    fd_raw = get_heatmap_coords(driver, f"{base_url}?{all_p}&{all_w}&{base_first}&showKills=false&showDeaths=true&showKillDataset=false&showDeathDataset=true")
    # 阶段一：全局 c 全为 1 时，直接按时序对齐
    if (fk_raw and fd_raw and
            check_all_ones(fk_raw) and check_all_ones(fd_raw) and
            len(fk_raw) == len(fd_raw) == n):
        for i, ev in enumerate(first_kills):
            ev['killer_pos'] = fk_raw[i]['pos']
            ev['victim_pos'] = fd_raw[i]['pos']
    else:
        # 阶段二：逐选手纯净视角填充
        fill_per_player(driver, first_kills, hltv_players, base_first, base_url)
        # 阶段三：剩余未填充项两侧必同为 c!=1，展开全局多重坐标直接兜底
        if any(not ev['killer_pos'] or not ev['victim_pos'] for ev in first_kills):
            apply_global_fallback(first_kills, fk_raw, fd_raw)
    # 挂载武器信息并组装输出
    fill_weapons(driver, first_kills, hltv_players, base_first, base_url)
    return build_kills_output(first_kills, hltv_players)


def construct_match_json(metadata, players, kills):
    match_json = {
        "metadata": metadata,
        "status": "ok",
        "data": {
            "players": players,
            "rounds": []
        }
    }
    if kills:
        for r_num, k_list in kills.items():
            match_json["data"]["rounds"].append({
                "round_num": r_num,
                "kills": k_list
            })
    return match_json


def main():
    demo_kills_path = Path("dataset/demo_kills.jsonl")
    basic_info_path = Path("dataset/basic_info.jsonl")
    output_path = Path("dataset/first_kills.jsonl")
    info_lookup = {}
    with basic_info_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            obj = json.loads(line)
            if obj.get("status") != "ok": continue
            mid = str(obj["metadata"]["map_id"])
            raw = obj["metadata"]
            info_lookup[mid] = {
                "metadata": {
                    "series_id": raw["series_id"],
                    "event_name": raw["event_name"],
                    "map_id": raw["map_id"],
                    "match_name": raw["match_name"]
                },
                "players": obj["data"]["players"]
            }
    # 加载需要补全的 Demo 数据
    pending_demos = []
    with demo_kills_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            obj = json.loads(line)
            if obj.get("status") == "ok" and obj.get("kills"):
                pending_demos.append(obj)
    print(f">>> 从 Demo 数据中读取到 {len(pending_demos)} 场待补全比赛")
    driver = setup_driver()
    driver.get("https://www.hltv.org")
    input(">>>")
    for idx, demo_obj in enumerate(pending_demos, 1):
        map_id = str(demo_obj["map_id"])
        entry = info_lookup.get(map_id)
        if not entry:
            print(f"\n>>> [{idx}/{len(pending_demos)}] 跳过 map_id={map_id}：basic_info 中无对应记录")
            continue
        metadata = entry["metadata"]
        players = entry["players"]
        match_name = metadata["match_name"]
        print(f"\n>>> [{idx}/{len(pending_demos)}] 开始补全 map_id={map_id} ({match_name})")
        kills = get_supplement_kills(driver, map_id, match_name, players, demo_obj["kills"])
        match_json = construct_match_json(metadata, players, kills)
        append_jsonl(output_path, match_json)
        filled_coords = sum(1 for r in match_json['data']['rounds'] if r['kills'][0]['killer_pos'] != "Unknown" or r['kills'][0]['victim_pos'] != "Unknown")
        total_rounds = len(match_json['data']['rounds'])
        print(f">>> 补全完成。共 {total_rounds} 局，成功挂载 {filled_coords} 局的坐标数据。")
    driver.quit()
    print(">>> 任务结束")


if __name__ == "__main__":
    main()
