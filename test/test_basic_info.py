# test/test_basic_info.py
# 用于对 basic_info.jsonl 数据集进行自动化检查，筛查异常与缺漏数据

import json
from pathlib import Path
from collections import defaultdict

def check_basic_info(file_path):
    p = Path(file_path)
    if not p.exists():
        print(f">>> 找不到文件: {file_path}")
        return

    # 统计数据
    total_lines = 0
    failed_scrapes = 0
    
    # 使用字典归类各类异常，格式： { "异常类型": ["map_id (match_name)", ...] }
    anomalies = defaultdict(list)

    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            total_lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                anomalies["JSON 解析失败"].append(f"Line {total_lines}")
                continue

            metadata = obj.get("metadata", {})
            map_id = metadata.get("map_id", "Unknown_Map_ID")
            match_name = metadata.get("match_name", "Unknown_Match")
            identifier = f"{map_id} ({match_name})"

            # 检查抓取状态
            if obj.get("status") != "ok":
                failed_scrapes += 1
                continue

            data = obj.get("data", {})
            players = data.get("players", {})
            economy = data.get("economy", {})

            # 检查选手数量
            if len(players) != 10:
                anomalies[f"选手人数异常 (当前 {len(players)} 人)"].append(identifier)
            for p_id, p_name in players.items():
                if not p_id or not p_name:
                    anomalies["选手ID或名称为空"].append(identifier)

            # 如果没有经济数据，记录后直接跳过后续经济校验
            if not economy:
                anomalies["完全没有经济数据"].append(identifier)
                continue

            # 提取所有回合数并转为整数排序
            try:
                round_nums = sorted([int(r) for r in economy.keys()])
            except ValueError:
                anomalies["回合数格式异常 (非整数)"].append(identifier)
                continue

            max_round = round_nums[-1]

            # 检查回合数合法性
            if max_round < 13:
                anomalies[f"总回合数过少 (<13，当前 {max_round} 局)"].append(identifier)
            elif max_round > 24:
                anomalies[f"包含加时赛经济 (当前 {max_round} 局)"].append(identifier)

            # 检查回合连续性
            expected_rounds = list(range(1, max_round + 1))
            if round_nums != expected_rounds:
                anomalies["回合数不连续 (存在跳局)"].append(identifier)

            # 经济与队伍细节检查
            global_teams = set()
            for r_num_str, r_data in economy.items():
                teams_in_round = list(r_data.keys())
                
                if len(teams_in_round) != 2:
                    anomalies["单回合队伍数量异常"].append(f"{identifier} - Round {r_num_str}")
                
                for t_name, t_eco in r_data.items():
                    global_teams.add(t_name)
                    
                    if t_name == "Unknown":
                        anomalies["包含 'Unknown' 未知队伍名"].append(identifier)

                    val = t_eco.get("value", 0)
                    
                    if val == 0:
                        anomalies["经济数值为 0 (解析可能失效)"].append(f"{identifier} - Round {r_num_str}")
                    elif val > 50000:
                        anomalies["单边经济太高 (>50000)"].append(f"{identifier} - Round {r_num_str}")

                    # 手枪局判定：第1回合 和 第13回合
                    if r_num_str in ["1", "13"]:
                        if val > 6000:
                            anomalies[f"手枪局(Round {r_num_str})经济过高 ({val})，疑为错位"].append(identifier)

            if len(global_teams) > 2:
                anomalies["队伍名称全局不一致"].append(identifier)


    # 报告错误
    print(f">>> 扫描总行数: {total_lines}")
    print(f">>> 抓取状态为 failed 的比赛数: {failed_scrapes}")
    
    if not anomalies:
        print("\n>>> 目前未检测到任何不合理的脏数据。")
    else:
        print(f"\n>>> 发现 {len(anomalies)} 种类型的数据异常：\n")
        for anomaly_type, matches in anomalies.items():
            # 对同一类异常的比赛进行去重处理
            unique_matches = list(set(matches))
            print(f">>> 【{anomaly_type}】 (共 {len(unique_matches)} 场)")

            for m in unique_matches:
                print(f"    - {m}")

if __name__ == "__main__":
    data_file = Path(__file__).parent.parent / "dataset" / "basic_info.jsonl"
    check_basic_info(data_file)