# parse_demo_data.py
# 批量解析指定目录下所有的 CS2 Demo 文件，提取击杀者与阵亡者信息，输出至单个 JSONL 文件。

import json
from pathlib import Path
from demoparser2 import DemoParser
from scrapers import append_jsonl


# 解析单个 Demo 的击杀数据，提取回合数、击杀者和受害者
def extract_kills_from_demo(demo_path):
    parser = DemoParser(str(demo_path))

    # 划分回合边界
    round_starts = parser.parse_event("round_start").sort_values("tick")
    round_starts = round_starts.iloc[1:].reset_index(drop=True)
    round_starts["custom_round"] = range(1, len(round_starts) + 1)

    # 辅助函数：根据 tick 分配所属的实际回合
    def _assign_round(tick):
        rows = round_starts[round_starts["tick"] <= tick]
        return rows.iloc[-1]["custom_round"] if not rows.empty else None

    # 解析击杀事件
    deaths = parser.parse_event("player_death")
    
    # 统一受害者列名
    if "user_name" in deaths.columns:
        deaths = deaths.rename(columns={"user_name": "victim_name"})
        
    for col in ["attacker_name", "victim_name", "tick"]:
        if col not in deaths.columns:
            raise KeyError(f"击杀事件缺失必要列: {col}")

    # 映射实际回合数，丢弃无法分配回合的数据
    deaths["round"] = deaths["tick"].apply(_assign_round)
    deaths = deaths.dropna(subset=["round"])
    deaths["round"] = deaths["round"].astype(int)

    # 构造纯净的击杀列表
    kills_list = []
    
    # 按照回合数和击杀发生的时间(tick)进行排序，保证时序正确
    deaths = deaths.sort_values(["round", "tick"])
    
    for _, row in deaths.iterrows():
        kills_list.append({
            "round": int(row["round"]),
            "killer": str(row["attacker_name"]),
            "victim": str(row["victim_name"])
        })
        
    return kills_list

# 主调度逻辑：遍历文件夹解析所有 demo
def main():
    # 路径配置
    demo_dir = Path("dataset/demos")
    output_file = Path("dataset/demo_kills.jsonl")
    
    # 确保输出目录存在，每次运行前可选择清空旧文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    # 查找目录下所有的 .dem 文件
    demo_files = list(demo_dir.glob("*.dem"))
    if not demo_files:
        print(">>> [-] 目录中未找到任何 .dem 文件，请检查路径。")
        return

    print(f">>> [*] 扫描到 {len(demo_files)} 个 Demo 文件，开始批量解析...\n")

    success_count = 0
    
    for idx, demo_path in enumerate(demo_files, 1):
        # 提取文件名作为 map_id
        map_id = demo_path.stem
        print(f">>> [{idx}/{len(demo_files)}] 开始解析: map_id={map_id}")

        try:
            kills_data = extract_kills_from_demo(demo_path)
            
            match_record = {
                "map_id": map_id,
                "status": "ok",
                "kills": kills_data
            }
            
            append_jsonl(output_file, match_record)
            print(f"    [+] 解析成功，共提取 {len(kills_data)} 条击杀记录。")
            success_count += 1
            
        except Exception as e:
            # 记录解析失败的文件
            print(f"    [-] 解析异常: {e}")
            fail_record = {
                "map_id": map_id,
                "status": "failed",
                "error": str(e)
            }
            append_jsonl(output_file, fail_record)

    print("\n" + "="*50)
    print(f">>> 任务结束！成功解析 {success_count}/{len(demo_files)} 场比赛。")
    print(f">>> 数据保存位置: {output_file}")
    print("="*50)


if __name__ == "__main__":
    main()