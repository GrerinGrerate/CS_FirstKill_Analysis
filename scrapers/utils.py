# scrapers/utils.py
# 爬虫项目通用的工具函数，包括配置文件加载、JSONL 读写和缓存状态解析

import json
from pathlib import Path


# 读取 JSON 配置文件
def load_config(config_path):
    return json.loads(Path(config_path).read_text(encoding="utf-8"))


# 向 JSONL 文件追加单行 JSON 数据
def append_jsonl(output_path, obj):
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# 通用的缓存读取函数
def load_completed_ids(cache_path, id_key):
    p = Path(cache_path)
    done = set()
    if not p.exists():
        return done

    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                item_id = obj.get(id_key)
                # 只有明确存在 ID 且 status 为 ok 才算抓取完成
                if item_id and obj.get("status") == "ok":
                    done.add(str(item_id))
            except Exception:
                continue
    return done

# 遍历配置文件，生成待爬取的比赛任务字典
def iter_matches(config_data):
    for series in config_data:
        yield {
            "series_id": str(series.get("series_id", "")),
            "event_name": series.get("event_name", ""),
            "map_id": str(series.get("map_id", "")),
             "match_name": series.get("teams_name")
        }