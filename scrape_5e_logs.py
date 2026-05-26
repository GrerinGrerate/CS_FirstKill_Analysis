# scrape_5e_logs.py
# 从 event.5eplay.com 爬取 CS2 Mirage 地图的逐局 kill/action 日志。

import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from scrapers import setup_driver, load_config, load_completed_ids, append_jsonl

# 5E 赛事对战页面的 URL 模板
MATCH_URL = "https://event.5eplay.com/csgo/matches/csgo_mc_{series_id}"

# 中文局数与阿拉伯数字映射字典
CHINESE_NUMS = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9,
}

# 回合胜利条件的关键字列表
WIN_CONDITIONS = ["歼灭敌人", "炸弹爆炸", "超时获胜", "拆弹获胜"]

# 全局武器映射字典
WEAPON_MAPPING = {}
WEAPON_MAP_FILE = Path("dataset/weapon_names.json")

# 初始化加载武器字典
if WEAPON_MAP_FILE.exists():
    try:
        weapon_data = json.loads(WEAPON_MAP_FILE.read_text(encoding="utf-8"))
        for item in weapon_data:
            WEAPON_MAPPING[item["weapon"]] = item["real_name"]
    except Exception as e:
        print(f">>> 武器配置文件加载失败: {e}")

# 将中文数字转化为 int
def _cn_to_int(s):
    if s in CHINESE_NUMS:
        return CHINESE_NUMS[s]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None

# 根据日志文本匹配并提取当前对局索引
def _parse_map_index(text):   
    m = re.search(r'第([一二三四五六七八九\d]+)局', text)
    if m:
        return _cn_to_int(m.group(1))
        
    return None


# 匹配并提取武器真实名称
def _weapon_from_src(src):
    if not src:
        return ""
        
    # 提取 URL 尾部的特征码
    m = re.search(r'/equipment/([^/?#]+?)(?:\.[a-zA-Z]+)?$', src)
    if m:
        # 去除前缀
        hash_str = re.sub(r'(?i)^equipment', '', m.group(1)).strip()
        hash_str = hash_str if hash_str else src.rsplit('/', 1)[-1]
        # 查询映射字典，查不到则回退到 hash 字符串
        return WEAPON_MAPPING.get(hash_str, hash_str)
        
    fallback_str = src.rsplit('/', 1)[-1]
    return WEAPON_MAPPING.get(fallback_str, fallback_str)


# 提取 HTML 标签中的数字文本内容
def _safe_span_int(span):
    try:
        return int(span.get_text(strip=True)) if span else None
    except ValueError:
        return None


# 处理回合开始信息
def _parse_round_start(tag, raw_text):
    uppercase = tag.find("span", class_="uppercase")
    map_name = uppercase.get_text(strip=True) if uppercase else None
    
    return {
        "type":      "round_start",
        "map_index": _parse_map_index(raw_text),
        "map_name":  map_name,
        "raw":       raw_text,
    }


# 处理回合结束信息
def _parse_round_end(tag, raw_text):
    if "T获胜" in raw_text:
        winner_side = "T"
    elif "CT获胜" in raw_text:
        winner_side = "CT"
    else:
        winner_side = None
        
    winner_score = _safe_span_int(tag.find("span", class_="green"))
    loser_score  = _safe_span_int(tag.find("span", class_="red"))

    # 根据胜方反推哪边是 T 的得分，哪边是 CT 的得分
    if winner_side == "T":
        t_score, ct_score = winner_score, loser_score
    elif winner_side == "CT":
        ct_score, t_score = winner_score, loser_score
    else:
        t_score = ct_score = None

    return {
        "type":          "round_end",
        "winner_side":   winner_side,
        "t_score":       t_score,
        "ct_score":      ct_score,
        "win_condition": next((c for c in WIN_CONDITIONS if c in raw_text), None),
        "raw":           raw_text,
    }


# 处理击杀信息
def _parse_kill(tag, raw_text, imgs):
    all_spans = tag.find_all("span", class_=re.compile(r"^(T|CT)-color$"))
    attacker = attacker_side = victim = victim_side = None
    
    if all_spans:
        a = all_spans[0]
        attacker      = a.get_text(strip=True)
        attacker_side = "T" if "T-color" in (a.get("class") or []) else "CT"
        
    if len(all_spans) >= 2:
        v = all_spans[-1]
        victim      = v.get_text(strip=True)
        victim_side = "T" if "T-color" in (v.get("class") or []) else "CT"
        
    src = imgs[0].get("src", "")
    
    return {
        "type":          "kill",
        "attacker":      attacker,
        "attacker_side": attacker_side,
        "weapon":        _weapon_from_src(src),
        "weapon_src":    src,
        "victim":        victim,
        "victim_side":   victim_side,
        "raw":           raw_text,
    }


# 处理放置炸弹信息
def _parse_bomb_plant(raw_text, t_names, ct_names):
    planter = (t_names + ct_names)[:1]
    alive_m = re.search(r'当前\s*(\d+)\s*v\s*(\d+)', raw_text)
    
    return {
        "type":     "bomb_plant",
        "planter":  planter[0] if planter else None,
        "ct_alive": int(alive_m.group(1)) if alive_m else None,
        "t_alive":  int(alive_m.group(2)) if alive_m else None,
        "raw":      raw_text,
    }


# 处理回合内常规动作记录分发
def _parse_action(tag, raw_text):
    if "加入比赛" in raw_text:
        player = raw_text.replace("加入比赛", "").strip()
        return {"type": "player_join", "player": player, "raw": raw_text}
        
    if "退出了游戏" in raw_text:
        player = raw_text.replace("退出了游戏", "").strip()
        return {"type": "player_leave", "player": player, "raw": raw_text}

    t_names  = [s.get_text(strip=True) for s in tag.find_all("span", class_="T-color")]
    ct_names = [s.get_text(strip=True) for s in tag.find_all("span", class_="CT-color")]
    imgs     = tag.find_all("img")

    if "放置了炸弹" in raw_text:
        return _parse_bomb_plant(raw_text, t_names, ct_names)    
    if imgs:
        return _parse_kill(tag, raw_text, imgs)
        
    return {"type": "other", "raw": raw_text}


# DOM 元素解析的主入口，按照 css class 将行数据派发给对应子函数
def parse_log_item(tag):
    classes  = tag.get("class", [])
    raw_text = " ".join(tag.get_text(separator=" ").split())
    
    if not raw_text.strip():
        return None
    if "start" in classes:
        return _parse_round_start(tag, raw_text)
    if "end" in classes:
        return _parse_round_end(tag, raw_text)
        
    return _parse_action(tag, raw_text)


# 强制 JS 点击
def _js_click(driver, elem):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", elem
    )

# 解析 DOM 中的单张地图选项卡数据
def _parse_round_tab_li(li, selenium_tabs, idx):
    bout_text_div = li.find("div", class_="bout-text")
    if not bout_text_div:
        return None
        
    p = bout_text_div.find("p")
    if not p:
        return None
        
    full_text = " ".join(t.strip() for t in p.stripped_strings if t.strip())
    round_num_m = re.search(r'第([一二三四五六七八九\d]+)局', full_text)

    if not round_num_m:
        return None
        
    round_num = _cn_to_int(round_num_m.group(1))
    if round_num is None or idx >= len(selenium_tabs):
        return None
        
    map_m = re.search(r'/\s*(.+)', full_text)
    
    return {
        "index":     idx,
        "round_num": round_num,
        "map_name":  map_m.group(1).strip() if map_m else None,
        "full_text": full_text,
    }


# 获取当前页面中包含所有切局 Tab 的列表
def get_round_tabs(driver):
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.bout-list-box"))
        )
    except TimeoutException:
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    ul   = soup.find("ul", class_="bout-list-box")
    if not ul:
        return []

    selenium_tabs = driver.find_elements(By.CSS_SELECTOR, "ul.bout-list-box > li")
    result = []
    
    for idx, li in enumerate(ul.find_all("li")):
        tab = _parse_round_tab_li(li, selenium_tabs, idx)
        if tab is not None:
            result.append(tab)
            
    return result


# 点击开启 5E 页面的赛事日志浮窗
def open_log_modal(driver):
    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div.game-logs-show"))
        )
        _js_click(driver, btn)
        time.sleep(1)  
        return True
    except (TimeoutException, NoSuchElementException):
        return False

# 通过轮询点击关闭按钮或按 ESC 键的方式，确保弹窗被彻底关闭
def close_log_modal(driver):
    close_selectors = [
        "div.game-logs-modal .game-logs-title .close",
        "div.game-logs-modal .close",
        "div.game-logs-modal .game-logs-title > div:last-child",
    ]
    for sel in close_selectors:
        try:
            _js_click(driver, driver.find_element(By.CSS_SELECTOR, sel))
            time.sleep(0.5)
            return
        except (NoSuchElementException, ElementClickInterceptedException):
            continue
            
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)


# 读取并过滤提取出当前弹窗内的所有比赛日志条目
def read_modal_logs(driver):
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.live-log-item"))
        )
    except TimeoutException:
        pass

    soup  = BeautifulSoup(driver.page_source, "html.parser")
    modal = soup.find("div", class_="game-logs-modal")
    if not modal:
        return []
        
    log_div = modal.find("div", class_="matches-detail-live-log")
    if not log_div:
        return []
        
    return [
        item
        for d in log_div.find_all("div", class_="live-log-item")
        if (item := parse_log_item(d)) is not None
    ]


# 判定是否为 Mirage 地图
def _is_mirage(map_name):
    return bool(map_name and "mirage" in map_name.lower())

# 处理具体对局页的抓取主流程
def scrape_mirage(driver, series_id, event_name):
    url = MATCH_URL.format(series_id=series_id)
    driver.get(url)
    time.sleep(1) 

    round_tabs   = get_round_tabs(driver)
    mirage_tabs  = [t for t in round_tabs if _is_mirage(t.get("map_name"))]
    
    if not mirage_tabs:
        return None

    rt   = mirage_tabs[0]
    tabs = driver.find_elements(By.CSS_SELECTOR, "ul.bout-list-box > li")

    _js_click(driver, tabs[rt["index"]])
    time.sleep(1)

    if not open_log_modal(driver):
        return {
            "series_id":  series_id,
            "event_name": event_name,
            "map_name":   rt["map_name"],
            "round_num":  rt["round_num"],
            "status":     "modal_failed",
            "url":        url,
            "entries":    [],
        }

    entries = read_modal_logs(driver)
    close_log_modal(driver)

    return {
        "series_id":  series_id,
        "event_name": event_name,
        "map_name":   rt["map_name"],
        "round_num":  rt["round_num"],
        "status":     "ok",
        "url":        url,
        "entries":    entries,
    }

# 组装状态报告
def _process_series(driver, series):
    record = scrape_mirage(driver, series["series_id"], series["event_name"])
    if record is None:
        return None, "无 Mirage 局，跳过"
        
    n = len(record.get("entries", []))
    return record, f"成功抓取 {n} 条日志，status={record['status']}"

def main():
    output_path = "dataset/matches_logs.jsonl"
    cache_path = "cache/completed_5e.jsonl"
    config_path = "dataset/matches_config.json"
    
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)

    config_data = load_config(config_path)
    all_series = []
    seen = set()
    for s in config_data:
        sid = str(s.get("series_id", ""))
        if sid and sid not in seen:
            all_series.append({"series_id": sid, "event_name": s.get("event_name", "")})
            seen.add(sid)

    completed = load_completed_ids(cache_path, "series_id")
    pending = [s for s in all_series if s["series_id"] not in completed]

    print(f">>> 配置文件共 {len(all_series)} 场比赛")
    print(f">>> 缓存读取已完成 {len(completed)} 场")
    print(f">>> 当前待爬取 {len(pending)} 场")
    
    if not pending:
        print(">>> 全部任务已完成。")
        return

    print(">>>")
    driver = setup_driver()
    
    try:
        for idx, series in enumerate(pending, 1):
            series_id = series["series_id"]
            print(f"\n>>> [{idx}/{len(pending)}] 开始处理 series_id={series_id}")

            try:
                record, msg = _process_series(driver, series)
                if record is not None:
                    append_jsonl(output_path, record)
                append_jsonl(cache_path, {"series_id": series_id, "status": "ok"})
                print(f">>> {msg}")

            except Exception as e:
                print(f">>> 异常: {series_id} -> {e}")
                driver.current_url
    finally:
        print(">>> 结束爬取")
        driver.quit()
    print("\n>>> 任务结束。")

if __name__ == "__main__":
    main()