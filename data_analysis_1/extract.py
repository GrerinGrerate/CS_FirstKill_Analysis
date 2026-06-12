import numpy as np
import pandas as pd

from config import (DISADV_RATIO, WEAPON_PRICES, DEFAULT_WEAPON_PRICE)
from utils import clean_text, same_team

#根据武器名称返回价格，无法识别时返回默认价格
def get_weapon_price(weapon):
    if not weapon:
        return DEFAULT_WEAPON_PRICE

    weapon_str = str(weapon)
    cleaned = clean_text(weapon_str).replace("-", "")

    if cleaned in WEAPON_PRICES:
        return WEAPON_PRICES[cleaned]

    for key, price in WEAPON_PRICES.items():
        normalized_key = key.replace("-", "")
        if normalized_key in cleaned or cleaned in normalized_key:
            return price

    return DEFAULT_WEAPON_PRICE
#根据装备总价值判断经济类型（Full buy / Semi_buy / Semi_Eco / Eco）
def get_econ_type(equip_value):
    if equip_value >= 20050:
        return "Full buy"
    if equip_value >= 10050:
        return "Semi_buy"
    if equip_value >= 5050:
        return "Semi_Eco"
    return "Eco"
#从回合数据中收集所有击杀事件（首杀 + 其他击杀）
def collect_kill_events(round_data):
    kills = []
    first_kill = round_data["first_kill"]
    if first_kill is not None:
        kills.append(first_kill)
    kills.extend(round_data["other_kills"])
    return kills
#判断单次击杀是否属于“英雄武器击杀”
def is_hero_kill_single(kill, round_economy, player_to_team):
    weapon = kill["weapon"]
    weapon_value = get_weapon_price(weapon)
    if weapon_value == 0:
        return False

    killer = kill["killer"]
    victim = kill["victim"]

    killer_team = player_to_team.get(clean_text(killer))
    victim_team = player_to_team.get(clean_text(victim))
    if killer_team is None or victim_team is None:
        return False

    killer_info = round_economy[killer_team]
    victim_info = round_economy[victim_team]

    killer_team_value = float(killer_info["value"])
    victim_team_value = float(victim_info["value"])
    killer_team_type = killer_info["type"]

    #条件1：武器价值超过自身队伍装备价值的 24%
    if not (weapon_value > killer_team_value * 0.24):
        return False

    #条件2：击杀者队伍必须处于经济劣势类型
    allowed_types = {"eco", "semi-eco", "semi-buy", "semieco", "semibuy"}
    if clean_text(killer_team_type) not in allowed_types:
        return False

    #条件3：击杀者队伍相对受害者队伍处于装备劣势（低于80%）
    if not (killer_team_value < victim_team_value * 0.8):
        return False

    return True

#检查整个回合是否存在英雄武器击杀
def check_hero_weapon_in_round(round_data, player_to_team):
    round_economy = round_data["economy"]
    for kill in collect_kill_events(round_data):
        if is_hero_kill_single(kill, round_economy, player_to_team):
            return True
    return False
#从回合经济数据中识别劣势方和优势方,返回 (劣势方字典, 优势方字典)，若不满足劣势条件则返回 None
def get_team_economy(round_data):
    teams = []
    for team_name, economy_info in round_data["economy"].items():
        equip_value = float(economy_info["value"])
        teams.append({
            "team_name": clean_text(team_name),
            "equip_value": equip_value,
            "money": 0.0,
            "buy_type": str(economy_info["type"]),
            "weapons": [],
        })

    if len(teams) < 2:
        return None

    teams.sort(key=lambda item: item["equip_value"])
    disadv_team = teams[0]
    advant_team = teams[1]

    #劣势方的装备价值必须小于优势方的 DISADV_RATIO 倍
    if disadv_team["equip_value"] >= advant_team["equip_value"] * DISADV_RATIO:
        return None

    return disadv_team, advant_team

#返回首杀所属的阵营（T/CT）或队伍名称
def get_first_kill_team_or_side(round_data):
    first_kill = round_data["first_kill"]
    if first_kill is None:
        return None
    return first_kill["killer_side"]

#返回回合胜方的阵营（T/CT）
def get_winner(round_data):
    return round_data["winner_side"].upper()

#通过击杀事件推断每支队伍在本回合的阵营（T或CT）
#返回字典 {team_name: side}
def infer_team_side_map(round_data, team_names, player_to_team):
    kills = collect_kill_events(round_data)
    votes = {team: [] for team in team_names}

    for kill in kills:
        killer = kill["killer"]
        killer_side = kill["killer_side"]
        killer_team = player_to_team.get(clean_text(killer))
        if killer_team in votes:
            votes[killer_team].append(killer_side.upper())

        victim = kill["victim"]
        victim_side = kill["victim_side"]
        victim_team = player_to_team.get(clean_text(victim))
        if victim_team in votes:
            votes[victim_team].append(victim_side.upper())

    team_side = {}
    for team, sides in votes.items():
        if len(sides) < 2:
            team_side[team] = None
            continue
        t_count = sides.count("T")
        ct_count = sides.count("CT")
        if t_count > ct_count:
            team_side[team] = "T"
        elif ct_count > t_count:
            team_side[team] = "CT"
        else:
            team_side[team] = None

    #若只有一队有明确阵营，则给另一队赋相反阵营
    reliable_teams = [team for team, side in team_side.items() if side is not None]
    if len(reliable_teams) == 1:
        reliable_team = reliable_teams[0]
        reliable_side = team_side[reliable_team]
        for team in team_names:
            if team_side[team] is None:
                team_side[team] = "CT" if reliable_side == "T" else "T"

    return team_side
#判断首杀是否发生在指定队伍身上（通过队伍名或阵营）
def team_hit_by_fk(fk_value, team_name, team_side):
    if fk_value is None:
        return False
    fk_text = str(fk_value)
    if same_team(fk_text, team_name):
        return True
    if team_side is not None and fk_text.upper() == team_side.upper():
        return True
    return False
#判断胜方是否为指定队伍（通过队伍名或阵营）
def team_hit_by_winner(winner_value, team_name, team_side):
    if winner_value is None:
        return False
    winner_text = str(winner_value).upper()
    if winner_text in ("T", "CT"):
        return team_side is not None and winner_text == team_side.upper()
    return same_team(winner_text, team_name)

#构建回合号 -> 回合详细信息（包括劣势方/优势方）的映射,只保留有效经济劣势回合
def build_round_data_map(rounds):
    round_data_map = {}
    for round_data in rounds:
        round_num = round_data["round_num"]
        result = get_team_economy(round_data)
        if result is None:
            continue
        disadv_team, advant_team = result
        disadv_team["econ_type"] = get_econ_type(disadv_team["equip_value"])
        advant_team["econ_type"] = get_econ_type(advant_team["equip_value"])
        round_data_map[round_num] = {
            "round_data": round_data,
            "disadv_team": disadv_team,
            "advant_team": advant_team,
        }
    return round_data_map
#主分析函数：从原始比赛记录中提取所有经济劣势回合的分析数据，
#返回包含各项指标的 DataFrame
def build_analysis_table(records):
    rows = []

    for match_index, record in enumerate(records):
        match_id = f"match_{match_index}"
        map_name = ""
        #玩家名 -> 队伍名 映射
        player_to_team = {
            clean_text(player): clean_text(team)
            for player, team in record["players"].items()
        }
        #收集所有经济劣势回合
        round_data_map = build_round_data_map(record["rounds"])

        for round_num, info in round_data_map.items():
            round_data = info["round_data"]
            disadv_team = info["disadv_team"]
            advant_team = info["advant_team"]

            disadv_team_name = disadv_team["team_name"]
            advant_team_name = advant_team["team_name"]

            # 推断双方阵营
            team_names = [disadv_team_name, advant_team_name]
            team_side_map = infer_team_side_map(round_data, team_names, player_to_team)
            disadv_side = team_side_map.get(disadv_team_name)
            if disadv_side is None:
                continue

            # 英雄武器判断
            hero_weapon = check_hero_weapon_in_round(round_data, player_to_team)

            first_kill_value = get_first_kill_team_or_side(round_data)
            winner_value = get_winner(round_data)

            disadv_first_kill = team_hit_by_fk(first_kill_value, disadv_team_name, disadv_side)
            disadv_win = team_hit_by_winner(winner_value, disadv_team_name, disadv_side)

            if advant_team["equip_value"] > 0:
                equip_ratio = disadv_team["equip_value"] / advant_team["equip_value"]
            else:
                equip_ratio = np.nan

            # 下一回合信息（用于经济延续分析）
            next_info = round_data_map.get(round_num + 1)
            next_still_disadv = np.nan
            next_round_econ_type = np.nan
            next_round_any_disadv = np.nan
            next_round_same_disadv = np.nan

            if next_info is not None:
                next_disadv = next_info["disadv_team"]
                next_advant = next_info["advant_team"]
                next_round_any_disadv = 1

                if clean_text(next_disadv["team_name"]) == clean_text(disadv_team_name):
                    next_round_same_disadv = 1
                    next_round_econ_type = next_disadv["econ_type"]
                else:
                    next_round_same_disadv = 0
                    if clean_text(next_advant["team_name"]) == clean_text(disadv_team_name):
                        next_round_econ_type = next_advant["econ_type"]
                    else:
                        next_round_econ_type = "Unknown"

                if not disadv_win:
                    next_still_disadv = 1 if next_round_same_disadv == 1 else 0
            else:
                next_round_any_disadv = 0

            rows.append({
                "match_id": match_id,
                "map_name": map_name,
                "round_num": round_num,
                "disadv_team": disadv_team_name,
                "advant_team": advant_team_name,
                "disadv_equip_value": disadv_team["equip_value"],
                "advant_equip_value": advant_team["equip_value"],
                "equip_ratio": equip_ratio,
                "disadv_econ_type": disadv_team["econ_type"],
                "disadv_buy_type": disadv_team["buy_type"],
                "hero_weapon": int(hero_weapon),
                "disadv_first_kill": int(disadv_first_kill),
                "disadv_win": int(disadv_win),
                "next_still_disadv": next_still_disadv,
                "next_round_econ_type": next_round_econ_type,
                "next_round_any_disadv": next_round_any_disadv,
                "next_round_same_disadv": next_round_same_disadv,
            })

    return pd.DataFrame(rows)