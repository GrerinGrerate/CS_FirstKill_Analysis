# test/test_matches.py
# 用于对 matches.jsonl 数据集进行自动化检查，筛查异常与缺漏数据

import json
from pathlib import Path
from collections import defaultdict, Counter

VALID_SIDES = {"T", "CT"}

# win_condition 与获胜方的逻辑约束
WIN_CONDITION_VALID_SIDE = {
    "炸弹爆炸": {"T"},       # 炸弹爆炸只有 T 可能获胜
    "拆弹获胜": {"CT"},      # 拆弹只有 CT 可能获胜
    "超时获胜": {"CT"},      # 超时只有 CT 可能获胜
    "歼灭敌人": {"T", "CT"}, # 歼灭敌人双方均可
}

def parse_coord(pos_str):
    x, y = pos_str.split(",")
    return int(x.strip()), int(y.strip())

def _check_pos(anomalies, r_id, label, pos):
    if pos in (None, "Unknown"):
        anomalies[f"首杀{label}坐标缺失"].append(r_id)
        return
    coord = parse_coord(pos)
    if coord is None:
        anomalies[f"首杀{label}坐标格式异常 (非 'x,y')"].append(r_id)
    elif not (0 <= coord[0] <= 700 and 0 <= coord[1] <= 700):
        anomalies[f"首杀{label}坐标超出合理范围 (0~700)"].append(r_id)

# 检查单次击杀的阵营字段合法性
def _check_kill_sides(anomalies, r_id, killer_side, victim_side, label):
    if not killer_side:
        anomalies[f"{label}击杀者阵营缺失"].append(r_id)
    elif killer_side not in VALID_SIDES:
        anomalies[f"{label}击杀者阵营非法值"].append(r_id)
    if not victim_side:
        anomalies[f"{label}受害者阵营缺失"].append(r_id)
    elif victim_side not in VALID_SIDES:
        anomalies[f"{label}受害者阵营非法值"].append(r_id)
    if killer_side and victim_side and killer_side == victim_side:
        anomalies[f"{label}友伤击杀（killer_side == victim_side）"].append(r_id)

def _check_first_kill(anomalies, r_id, fk):
    _check_kill_sides(anomalies, r_id, fk.get("killer_side"), fk.get("victim_side"), "首杀")
    _check_pos(anomalies, r_id, "击杀者", fk.get("killer_pos"))
    _check_pos(anomalies, r_id, "受害者", fk.get("victim_pos"))
    if not fk.get("weapon"):
        anomalies["首杀武器字段为空"].append(r_id)

# 检查单回合的获胜方与胜利条件字段
def _check_round_result(anomalies, r_id, winner_side, win_cond, first_kill, other_kills):
    if winner_side is not None and winner_side not in VALID_SIDES:
        anomalies["非法获胜方 (非 T/CT)"].append(r_id)
    if winner_side is None and (first_kill or other_kills):
        anomalies["有击杀但回合结果缺失"].append(r_id)
    if winner_side and not win_cond:
        anomalies["获胜方存在但 win_condition 缺失"].append(r_id)
    if winner_side and win_cond and win_cond in WIN_CONDITION_VALID_SIDE:
        if winner_side not in WIN_CONDITION_VALID_SIDE[win_cond]:
            anomalies[f"逻辑矛盾: {win_cond} 不应由 {winner_side} 获胜"].append(r_id)

# 检查相邻两局的分数变化合法性。
# 不论换边与否，有合法获胜方时 dt+dc 恒等于 1。
# 换边时（R13/OT 第一局）一侧分数合理下降，但两侧不会同时下降。
def _check_score_delta(anomalies, r_id, winner_side, t_score, ct_score, prev_t, prev_ct):
    if winner_side not in VALID_SIDES:
        return
    dt = t_score - prev_t
    dc = ct_score - prev_ct
    total = dt + dc
    if total == 0:
        anomalies["分数异常: 有获胜方但双方分数均未变化（疑似分数未写入）"].append(r_id)
    elif total < 0:
        anomalies["分数异常: 分数总量下降（疑似数据覆盖错误）"].append(f"{r_id} [dt={dt:+}, dc={dc:+}]")
    elif total > 1:
        anomalies["分数异常: 分数总量涨幅>1（疑似中间回合数据缺失）"].append(f"{r_id} [dt={dt:+}, dc={dc:+}]")
    if dt < 0 and dc < 0:
        anomalies["分数异常: T分与CT分同时下降（不可能发生）"].append(f"{r_id} [dt={dt:+}, dc={dc:+}]")

# 检查单回合内所有击杀条目的合法性
def _check_kills_in_round(anomalies, r_id, first_kill, other_kills):
    if first_kill is None and other_kills:
        anomalies["存在非首杀击杀但首杀为空"].append(r_id)
    if first_kill:
        _check_first_kill(anomalies, r_id, first_kill)
    for i, k in enumerate(other_kills):
        k_id = f"{r_id} kill#{i + 2}"
        _check_kill_sides(anomalies, k_id,k.get("killer_side"), k.get("victim_side"),"非首杀")

def _track_map_id(anomalies, seen_map_ids, map_id):
    if map_id in seen_map_ids:
        anomalies["重复的 map_id"].append(map_id)
    else:
        seen_map_ids.add(map_id)

# 对单场比赛执行所有回合级检查，返回该场比赛的 winner_side 计数。
def _check_match(anomalies, obj):
    metadata = obj.get("metadata", {})
    map_id = metadata.get("map_id", "Unknown")
    match_name = metadata.get("match_name", "Unknown")
    identifier = f"{map_id} ({match_name})"
    local_ws = Counter()
    players = obj.get("players", {})
    rounds = obj.get("rounds", [])
    if len(players) != 10:
        anomalies[f"选手人数异常 (当前 {len(players)} 人)"].append(identifier)
    if not rounds:
        anomalies["完全没有回合数据"].append(identifier)
        return local_ws
    round_nums = sorted(r["round_num"] for r in rounds)
    max_round  = round_nums[-1]
    if max_round < 13:
        anomalies[f"总回合数过少 (<13，当前 {max_round} 局)"].append(identifier)
    if round_nums != list(range(1, max_round + 1)):
        anomalies["回合数不连续 (存在跳局)"].append(identifier)
    prev_t, prev_ct = 0, 0
    for r in sorted(rounds, key=lambda x: x["round_num"]):
        rnum = r["round_num"]
        r_id = f"{identifier} - R{rnum:02d}"
        winner_side = r.get("winner_side")
        win_cond = r.get("win_condition")
        t_score = r.get("t_score") or 0
        ct_score = r.get("ct_score") or 0
        first_kill = r.get("first_kill")
        other_kills = r.get("other_kills", [])
        if winner_side:
            local_ws[winner_side] += 1
        if r.get("economy") is None:
            anomalies["回合经济数据缺失"].append(r_id)
        _check_round_result(anomalies, r_id, winner_side, win_cond, first_kill, other_kills)
        _check_score_delta(anomalies, r_id, winner_side, t_score, ct_score, prev_t, prev_ct)
        _check_kills_in_round(anomalies, r_id, first_kill, other_kills)
        prev_t, prev_ct = t_score, ct_score

    return local_ws

def check_matches(file_path):
    p = Path(file_path)
    if not p.exists():
        print(f">>> 找不到文件: {file_path}")
        return
    total_lines = 0
    seen_map_ids = set()
    anomalies = defaultdict(list)
    global_winner_side = Counter()
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            total_lines += 1
            obj = json.loads(line)
            map_id = obj.get("metadata", {}).get("map_id", "Unknown")
            _track_map_id(anomalies, seen_map_ids, map_id)
            global_winner_side += _check_match(anomalies, obj)
    # 全局：winner_side 分布检查
    for side in ("T", "CT"):
        if global_winner_side[side] == 0:
            anomalies[f"全局: winner_side 从未出现 '{side}'，疑似解析器固定写死"].append(f"全数据集 (T={global_winner_side['T']}, CT={global_winner_side['CT']})")
    print(f">>> 扫描总行数: {total_lines}")
    print(f">>> 全局 winner_side 分布: {dict(global_winner_side)}")
    if not anomalies:
        print("\n>>> 目前未检测到任何不合理的脏数据。")
        return
    print(f"\n>>> 发现 {len(anomalies)} 种类型的数据异常：\n")
    for anomaly_type, items in anomalies.items():
        unique_items = list(dict.fromkeys(items))
        print(f">>> 【{anomaly_type}】 (共 {len(unique_items)} 条)")
        for it in unique_items[:5]:
            print(f"    - {it}")

if __name__ == "__main__":
    data_file = Path(__file__).parent.parent / "dataset" / "matches.jsonl"
    check_matches(data_file)
