# scrape_first_kills.py
# 用于爬取并构建比赛首杀及坐标记录的主控脚本

from pathlib import Path
from scrapers import (
    setup_driver, 
    load_config, 
    load_completed_ids, 
    append_jsonl,
    get_players_from_stats_page ,
    iter_matches,
    get_match_kills
)

# 组装首杀 JSON 结构
def construct_match_json(match_info, players, kills):
    match_json = {
        "metadata": {
            "series_id": match_info['series_id'],
            "event_name": match_info['event_name'],
            "map_id": match_info['map_id'],
            "match_name": match_info['match_name']
        },
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
    output_path = "dataset/first_kills.jsonl"
    cache_path = "cache/completed_kills.jsonl"
    config_path = "dataset/matches_config.json"
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    config_data = load_config(config_path)
    all_matches = list(iter_matches(config_data))
    completed = load_completed_ids(cache_path, "map_id")
    pending = [m for m in all_matches if m["map_id"] and m["map_id"] not in completed]
    print(f">>> 配置文件共 {len(all_matches)} 场比赛")
    print(f">>> 缓存读取已完成 {len(completed)} 场")
    print(f">>> 当前待爬取 {len(pending)} 场")
    if not pending:
        print(">>> 全部任务已完成")
        return
    # 用于记录因为重叠等原因被跳过、需要人工介入的场次
    skipped_matches = []
    driver = setup_driver()
    driver.get("https://www.hltv.org")
    input(">>>")
    for idx, match in enumerate(pending, 1):
        map_id = match['map_id']
        match_name = match['match_name']
        print(f"\n>>> [{idx}/{len(pending)}] 开始处理 map_id={map_id} ({match_name})")
        stats_url = f"https://www.hltv.org/stats/matches/mapstatsid/{map_id}/{match_name}"
        # 获取选手名单
        players = get_players_from_stats_page(driver, stats_url)
        if not players:
            print(">>> 放弃: 未获取到选手名单")
            append_jsonl(cache_path, {"map_id": map_id, "status": "failed"})
            continue
        # 获取首杀坐标映射数据
        kills = get_match_kills(driver, map_id, match_name, players)  
        if kills is None:
            print(">>> 放弃: 首杀坐标存在重叠，不满足处理条件")
            append_jsonl(cache_path, {"map_id": map_id, "status": "ok", "note": "c_overlap_skipped"})
            skipped_matches.append(f"{map_id} ({match_name})")
            continue
        # 构造数据结构并落盘
        match_json = construct_match_json(match, players, kills)
        append_jsonl(output_path, match_json)
        append_jsonl(cache_path, {"map_id": map_id, "status": "ok"})
        # 打印首杀战报
        print(f">>> 成功解析 {len(kills)} 局首杀数据。")
        for r in match_json['data']['rounds']:
            fk = r['kills'][0]
            print(f"        R{r['round_num']:02d}: {fk['killer']} ({fk['weapon']}) 击杀了 {fk['victim']}")
    driver.quit()
    if skipped_matches:
        print(">>> 需手动补充：")
        for sm in skipped_matches:
            print(f"    - Map ID: {sm}")
    print(">>> 任务结束")

if __name__ == "__main__":
    main()