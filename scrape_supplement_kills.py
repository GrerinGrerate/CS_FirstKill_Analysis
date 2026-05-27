# scrape_supplement_kills.py
# 利用 Demo 的时序数据，以个人坐标视角补全全局重叠的残缺首杀信息

import json
import difflib
from pathlib import Path
from scrapers import (
    setup_driver, 
    load_config, 
    append_jsonl,
    get_players_from_stats_page,
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
        # 记录得分最高的选手
        if score > best_score:
            best_score = score
            best_match_id = pid
    # 只要最高相似度超过一个基础阈值，就采纳该结果
    if best_score > 0.3:
        return best_match_id
    return None

# 提取并在纯净视角下挂载首杀坐标
def get_supplement_kills(driver, map_id, match_name, hltv_players, demo_kills):
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
    base_url = f"https://www.hltv.org/stats/matches/heatmap/mapstatsid/{map_id}/{match_name}"
    base_first = "sides=COUNTER_TERRORIST&sides=TERRORIST&firstKillsOnly=true&allowEmpty=true"
    for pid in hltv_players.keys():
        # 获取该选手在 Demo 中作为杀手和被害者的独立事件流
        k_events = [ev for ev in first_kills if ev['killer_id'] == pid]
        d_events = [ev for ev in first_kills if ev['victim_id'] == pid]
        k_count = len(k_events)
        d_count = len(d_events)
        # 视角一 & 视角二：作为击杀者
        if k_count > 0:
            k_cross = get_paired_cross_coords(driver, pid, True, base_first, base_url)
            kk_coords = k_cross.get('killer_coords', [])
            kv_coords = k_cross.get('victim_coords', [])
            # 若自身站位数据纯净
            if check_all_ones(kk_coords) and len(kk_coords) == k_count:
                for i, ev in enumerate(k_events):
                    if not ev['killer_pos']: ev['killer_pos'] = kk_coords[i]['pos']
            # 若猎物站位数据纯净
            if check_all_ones(kv_coords) and len(kv_coords) == k_count:
                for i, ev in enumerate(k_events):
                    if not ev['victim_pos']: ev['victim_pos'] = kv_coords[i]['pos']
        # 视角三 & 视角四：作为受害者
        if d_count > 0:
            v_cross = get_paired_cross_coords(driver, pid, False, base_first, base_url)
            vk_coords = v_cross.get('killer_coords', [])
            vv_coords = v_cross.get('victim_coords', [])
            # 若杀手站位数据纯净
            if check_all_ones(vk_coords) and len(vk_coords) == d_count:
                for i, ev in enumerate(d_events):
                    if not ev['killer_pos']: ev['killer_pos'] = vk_coords[i]['pos']         
            # 若自身站位数据纯净
            if check_all_ones(vv_coords) and len(vv_coords) == d_count:
                for i, ev in enumerate(d_events):
                    if not ev['victim_pos']: ev['victim_pos'] = vv_coords[i]['pos']
        if all(ev['killer_pos'] and ev['victim_pos'] for ev in first_kills):
            break
    # 利用已确定的 killer_pos 去套接使用的武器
    for pid in hltv_players.keys():
        # 仅针对已确定杀手坐标的事件验证武器
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
    # 组装输出
    final_output = {}
    for ev in first_kills:
        r = ev["round_num"]
        k_pos = ev["killer_pos"] or "Unknown"
        v_pos = ev["victim_pos"] or "Unknown"
        # 为了兼容统一格式，将被覆盖的 HLTV 选手名拉取回来
        k_name = hltv_players.get(ev["killer_id"], ev["killer_name"])
        v_name = hltv_players.get(ev["victim_id"], ev["victim_name"])
        final_output[r] = [{
            "kill_id": 1,
            "killer": k_name,
            "killer_pos": k_pos,
            "weapon": ev["weapon"],
            "victim": v_name,
            "victim_pos": v_pos,
            "is_first_kill": True
        }]
    return final_output

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
    output_path = Path("dataset/first_kills.jsonl") 
    config_path = Path("dataset/matches_config.json")
    # 加载配置字典，用于组装 metadata
    config_data = load_config(config_path)
    metadata_lookup = {}
    for series in config_data:
        metadata_lookup[str(series.get("map_id", ""))] = {
            "series_id": str(series.get("series_id", "")),
            "event_name": series.get("event_name", ""),
            "map_id": str(series.get("map_id", "")),
            "match_name": series.get("match_name") or series.get("teams_name", "")
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
        metadata = metadata_lookup.get(map_id) 
        if not metadata:
            print(f"\n>>> [{idx}/{len(pending_demos)}] 跳过 map_id={map_id}")
            continue
        match_name = metadata["match_name"]
        print(f"\n>>> [{idx}/{len(pending_demos)}] 开始补全 map_id={map_id} ({match_name})")
        stats_url = f"https://www.hltv.org/stats/matches/mapstatsid/{map_id}/{match_name}"
        players = get_players_from_stats_page(driver, stats_url)
        # 执行个人纯净视角数据补全
        kills = get_supplement_kills(driver, map_id, match_name, players, demo_obj["kills"]) 
        # 构造符合结构的 JSON
        match_json = construct_match_json(metadata, players, kills)
        append_jsonl(output_path, match_json)
        # 统计成功填入坐标的比例
        filled_coords = sum(1 for r in match_json['data']['rounds'] if r['kills'][0]['killer_pos'] != "Unknown" or r['kills'][0]['victim_pos'] != "Unknown")
        total_rounds = len(match_json['data']['rounds'])       
        print(f">>> 补全完成。共 {total_rounds} 局，成功挂载 {filled_coords} 局的坐标数据。")
    driver.quit()
    print(">>> 任务结束")

if __name__ == "__main__":
    main()