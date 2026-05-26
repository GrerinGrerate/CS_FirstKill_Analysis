# scrapers/kills.py
# 处理单场比赛的首杀数据，基于首杀独立且不重叠的前提进行极速坐标和武器映射

from scrapers.heatmap_utils import (
    get_heatmap_coords,
    get_paired_cross_coords,
    get_player_weapons_list
)


# 检查序列中是否所有的 count 都是 1
def check_all_ones(coords_data):
    if not coords_data: return False
    return all(int(item.get("count", 1)) == 1 for item in coords_data)


# 获取本场所有回合的首杀事件
def get_match_kills(driver, map_id, match_name, player_dict):
    base_url = f"https://www.hltv.org/stats/matches/heatmap/mapstatsid/{map_id}/{match_name}"
    all_p = "&".join([f"players={pid}" for pid in player_dict.keys()])
    all_w = "&".join([f"weapons={pid}-All" for pid in player_dict.keys()])
    
    # 仅限定首杀过滤条件
    base_first = "sides=COUNTER_TERRORIST&sides=TERRORIST&firstKillsOnly=true&allowEmpty=true"

    # 仅获取全局首杀和首死坐标点
    fk_raw = get_heatmap_coords(driver, f"{base_url}?{all_p}&{all_w}&{base_first}&showKills=true&showDeaths=false&showKillDataset=true&showDeathDataset=false")
    fd_raw = get_heatmap_coords(driver, f"{base_url}?{all_p}&{all_w}&{base_first}&showKills=false&showDeaths=true&showKillDataset=false&showDeathDataset=true")
    
    # 一旦出现重叠 (count > 1) 或长度不匹配，立刻放弃该场比赛
    if not fk_raw or not fd_raw:
        return None
    if not check_all_ones(fk_raw) or not check_all_ones(fd_raw):
        return None
    if len(fk_raw) != len(fd_raw):
        return None

    # 初始化事件流骨架
    events = []
    for i in range(len(fk_raw)):
        events.append({
            "k": fk_raw[i]['pos'],
            "v": fd_raw[i]['pos'],
            "killer_id": None,
            "victim_id": None,
            "weapon": "Unknown"
        })

    # 身份映射：直接获取选手在首杀条件下的交叉坐标
    for pid in player_dict.keys():
        # 获取该选手作为首杀者的坐标配对
        k_cross = get_paired_cross_coords(driver, pid, True, base_first, base_url)
        for k_item, v_item in zip(k_cross.get('killer_coords', []), k_cross.get('victim_coords', [])):
            pair = (k_item['pos'], v_item['pos'])
            for ev in events:
                if (ev['k'], ev['v']) == pair:
                    ev['killer_id'] = pid
                    break

        # 获取该选手作为首死者的坐标配对
        v_cross = get_paired_cross_coords(driver, pid, False, base_first, base_url)
        for k_item, v_item in zip(v_cross.get('killer_coords', []), v_cross.get('victim_coords', [])):
            pair = (k_item['pos'], v_item['pos'])
            for ev in events:
                if (ev['k'], ev['v']) == pair:
                    ev['victim_id'] = pid
                    break

    # 挂载武器信息
    for pid in player_dict.keys():
        weapons = get_player_weapons_list(driver, pid, base_first, base_url)
        for w in weapons:
            w_raw = get_heatmap_coords(driver, f"{base_url}?players={pid}&weapons={pid}-{w}&{base_first}&showKills=true&showDeaths=false&showKillDataset=true&showDeathDataset=false")
            w_poses = {x['pos'] for x in w_raw}
            
            for ev in events:
                if ev['k'] in w_poses:
                    ev['weapon'] = w

    # 组装结果输出
    final_output = {}
    for idx, ev in enumerate(events):
        r = idx + 1
        k_name = player_dict.get(ev["killer_id"], "Unknown") if ev["killer_id"] else "Unknown"
        v_name = player_dict.get(ev["victim_id"], "Unknown") if ev["victim_id"] else "Unknown"
        
        final_output[r] = [{
            "kill_id": 1,
            "killer": k_name,
            "killer_pos": ev["k"],
            "weapon": ev["weapon"],
            "victim": v_name,
            "victim_pos": ev["v"],
            "is_first_kill": True
        }]

    return final_output