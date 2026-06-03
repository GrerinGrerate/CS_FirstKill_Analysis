# test/test_first_kills.py
# 用于对 first_kills.jsonl 数据集进行自动化检查，筛查异常与缺漏数据

import json
from pathlib import Path
from collections import defaultdict

# 尝试解析 'x,y' 格式坐标，失败返回 None
def parse_coord(pos_str):
    try:
        x, y = pos_str.split(",")
        return int(x.strip()), int(y.strip())
    except (ValueError, AttributeError):
        return None

def check_first_kills(file_path):
    p = Path(file_path)
    if not p.exists():
        print(f">>> 找不到文件: {file_path}")
        return
    total_lines = 0
    failed_scrapes = 0
    seen_map_ids = set()
    anomalies = defaultdict(list)
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_lines += 1
            obj = json.loads(line)
            metadata = obj.get("metadata", {})
            map_id = metadata.get("map_id", "Unknown")
            match_name = metadata.get("match_name", "Unknown")
            identifier = f"{map_id} ({match_name})"
            # 检查重复 map_id
            if map_id in seen_map_ids:
                anomalies["重复的 map_id"].append(identifier)
            else:
                seen_map_ids.add(map_id)
            # 检查抓取状态
            if obj.get("status") != "ok":
                failed_scrapes += 1
                continue
            data = obj.get("data", {})
            players = data.get("players", {})
            rounds = data.get("rounds", [])
            player_names = set(players.values())
            # 选手数量检查
            if len(players) != 10:
                anomalies[f"选手人数异常 (当前 {len(players)} 人)"].append(identifier)
            # 无回合数据
            if not rounds:
                anomalies["完全没有回合数据"].append(identifier)
                continue
            # 回合数合法性与连续性检查
            round_nums = sorted(r["round_num"] for r in rounds)
            max_round = round_nums[-1]
            if max_round < 13:
                anomalies[f"总回合数过少 (<13，当前 {max_round} 局)"].append(identifier)
            if round_nums != list(range(1, max_round + 1)):
                anomalies["回合数不连续 (存在跳局)"].append(identifier)
            # 逐回合内容检查
            for r in rounds:
                r_num = r["round_num"]
                r_id = f"{identifier} - R{r_num:02d}"
                kills = r.get("kills", [])
                # 每回合首杀数量应恰好为 1
                if len(kills) != 1:
                    anomalies[f"首杀条目数量异常 (非1，当前 {len(kills)} 条)"].append(r_id)
                    continue
                k = kills[0]
                killer = k.get("killer", "")
                victim = k.get("victim", "")
                killer_pos = k.get("killer_pos", "")
                victim_pos = k.get("victim_pos", "")
                # 击杀者与受害者名称异常
                if killer == "Unknown":
                    anomalies["击杀者名称为 Unknown"].append(r_id)
                if victim == "Unknown":
                    anomalies["受害者名称为 Unknown"].append(r_id)
                # 击杀者或受害者不在本场选手名单中
                if killer not in player_names and killer != "Unknown":
                    anomalies["击杀者不在本场选手名单"].append(r_id)
                if victim not in player_names and victim != "Unknown":
                    anomalies["受害者不在本场选手名单"].append(r_id)
                # 坐标为 Unknown
                if killer_pos == "Unknown":
                    anomalies["击杀者坐标为 Unknown"].append(r_id)
                if victim_pos == "Unknown":
                    anomalies["受害者坐标为 Unknown"].append(r_id)
                # 坐标格式与范围校验
                for label, pos in [("击杀者", killer_pos), ("受害者", victim_pos)]:
                    if pos == "Unknown":
                        continue
                    coord = parse_coord(pos)
                    if coord is None:
                        anomalies[f"{label}坐标格式异常 (非 'x,y')"].append(r_id)
                    else:
                        x, y = coord
                        if not (0 <= x <= 700 and 0 <= y <= 700):
                            anomalies[f"{label}坐标超出合理范围 (0~700)"].append(r_id)
                # is_first_kill 标记异常
                if not k.get("is_first_kill"):
                    anomalies["is_first_kill 标记不为 true"].append(r_id)
    # 报告结果
    print(f">>> 扫描总行数: {total_lines}")
    print(f">>> 抓取状态为 failed 的比赛数: {failed_scrapes}")
    if not anomalies:
        print("\n>>> 目前未检测到任何不合理的脏数据。")
    else:
        print(f"\n>>> 发现 {len(anomalies)} 种类型的数据异常：\n")
        for anomaly_type, items in anomalies.items():
            unique_items = list(set(items))
            print(f">>> 【{anomaly_type}】 (共 {len(unique_items)} 条)")
            for it in unique_items:
                print(f"    - {it}")

if __name__ == "__main__":
    data_file = Path(__file__).parent.parent / "dataset" / "first_kills.jsonl"
    check_first_kills(data_file)
