import json
from config import DATA_PATH

def read_jsonl(path=None):
    if path is None:
        path = DATA_PATH
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    print(f"读取到 {len(rows)} 条原始记录")
    return rows

def clean_name(x):
    if x is None:
        return ""
    return str(x).lower().replace(" ", "").replace("_", "").strip()

def clean_text(x):
    if x is None:
        return ""
    return str(x).lower().replace("_", " ").strip()

def same_team(a, b):
    a = clean_name(a)
    b = clean_name(b)
    if not a or not b:
        return False
    return a == b or a in b or b in a