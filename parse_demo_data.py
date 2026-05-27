# 批量解析指定目录下所有的 CS2 Demo 文件，提取击杀者与阵亡者信息，输出至单个 JSONL 文件。

import json
from pathlib import Path
from demoparser2 import DemoParser
from scrapers import append_jsonl   # 保留原有导入

#  配置路径  
demo_dir = Path("dataset/demos")
output_file = Path("dataset/demo_kills.jsonl")

output_file.parent.mkdir(parents=True, exist_ok=True)
if output_file.exists():
    output_file.unlink()
# 查找所有Demo文件 
demo_files = list(demo_dir.glob("*.dem"))
if not demo_files:
    print(">>> [-] 目录中未找到任何 .dem 文件，请检查路径。")
    exit(0)

print(f">>> [*] 扫描到 {len(demo_files)} 个 Demo 文件，开始批量解析...\n")

success_count = 0

# 逐个处理Demo 
for idx, demo_path in enumerate(demo_files, 1):
    map_id = demo_path.stem
    print(f">>> [{idx}/{len(demo_files)}] 开始解析: map_id={map_id}")

    try:
        parser = DemoParser(str(demo_path))

        #  回合边界 
        round_starts = parser.parse_event("round_start").sort_values("tick")
        round_starts = round_starts.iloc[1:].reset_index(drop=True)   # 跳过热身
        round_starts["custom_round"] = range(1, len(round_starts) + 1)

        def assign_round(tick):
            rows = round_starts[round_starts["tick"] <= tick]
            return rows.iloc[-1]["custom_round"] if not rows.empty else None

        #  击杀事件 
        deaths = parser.parse_event("player_death")

        # 统一受害者列名 
        if "user_name" in deaths.columns:
            deaths = deaths.rename(columns={"user_name": "victim_name"})

        required_cols = ["attacker_name", "victim_name", "tick"]
        for col in required_cols:
            if col not in deaths.columns:
                raise KeyError(f"击杀事件缺失必要列: {col}")

        # 分配回合编号
        deaths["round"] = deaths["tick"].apply(assign_round)
        deaths = deaths.dropna(subset=["round"])
        deaths["round"] = deaths["round"].astype(int)

        # 按回合和tick排序
        deaths = deaths.sort_values(["round", "tick"])

        # 构建击杀列表
        kills_list = []
        for _, row in deaths.iterrows():
            kills_list.append({
                "round": int(row["round"]),
                "killer": str(row["attacker_name"]),
                "victim": str(row["victim_name"])
            })

        # 写入成功记录
        match_record = {
            "map_id": map_id,
            "status": "ok",
            "kills": kills_list
        }
        append_jsonl(output_file, match_record)
        print(f"    [+] 解析成功，共提取 {len(kills_list)} 条击杀记录。")
        success_count += 1

    except Exception as e:
        print(f"    [-] 解析异常: {e}")
        fail_record = {
            "map_id": map_id,
            "status": "failed",
            "error": str(e)
        }
        append_jsonl(output_file, fail_record)

# ========== 汇总输出 ==========
print("\n" + "=" * 50)
print(f">>> 任务结束！成功解析 {success_count}/{len(demo_files)} 场比赛。")
print(f">>> 数据保存位置: {output_file}")
print("=" * 50)