# generate_config.py
# 用于爬取生成所有比赛信息的配置文件

import os
import json
import time
import re
from selenium.webdriver.common.by import By
from scrapers import setup_driver

# 全局配置
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CONFIG_FILE = os.path.join(WORKSPACE_DIR, "dataset/matches_config.json")

# 筛选条件
PRIZE_MIN = 98751
PRIZE_MAX = 2000000
MAX_PAGES = 2

# 提取 URL 中的 ID 和名称。
def extract_id_and_slug(url, url_type):
    if not url:
        return None, None
    if url_type == "event":
        # 匹配 /events/数字/赛事名称
        match = re.search(r'/events/(\d+)/([^/?]+)', url)
    elif url_type == "match":
        # 匹配 /matches/数字/队伍名称
        match = re.search(r'/matches/(\d+)/([^/?]+)', url)
    elif url_type == "mapstats":
        # 匹配 /stats/matches/mapstatsid/数字/
        match = re.search(r'/mapstatsid/(\d+)/', url)
        if match:
            return match.group(1), None 
    if match:
        return match.group(1), match.group(2)
    return None, None

# 主函数，生成比赛配置文件
def generate_config():
    # 拉取一个 Chrome 以爬取
    driver = setup_driver()
    all_series_config = []
    driver.get("https://www.hltv.org")
    input(">>>")
    # 计划爬取 2024-2026 的所有大赛，在实际的页面显示中确实只有两页
    for page in range(MAX_PAGES):
        offset = page * 50
        archive_url = f"https://www.hltv.org/events/archive?offset={offset}&prizeMin={PRIZE_MIN}&prizeMax={PRIZE_MAX}"
        print(f"\n>>> 正在访问: offset={offset}")
        driver.get(archive_url)
        time.sleep(0.1)
        # 获取所有赛事链接
        event_elements = driver.find_elements(By.CSS_SELECTOR, "a.a-reset.small-event.standard-box")
        event_urls = [el.get_attribute("href") for el in event_elements]       
        for event_url in event_urls:
            event_id, event_name = extract_id_and_slug(event_url, "event")
            if not event_id:
                continue
            print(f">>> 检查赛事: {event_name} ({event_id})")
            driver.get(event_url)
            time.sleep(0.1)
            # 大赛标准：1. 奖金是否符合范围 2. 是否颁发 MVP
            # 奖金已经编码在 URL 里，这里检查是否在比赛页有 MVP
            mvp_elements = driver.find_elements(By.ID, "Mvp")
            if not mvp_elements:
                print(">>> 非大赛，跳过")
                continue
            print(">>> 大赛，进入 Results 页面")
            results_url = f"https://www.hltv.org/results?event={event_id}"
            driver.get(results_url)
            time.sleep(1)
            # 获取赛事下的所有比赛链接
            match_elements = driver.find_elements(By.CSS_SELECTOR, "div.result-con a.a-reset")
            match_urls = [el.get_attribute("href") for el in match_elements]        
            for match_url in match_urls:
                series_id, teams_name = extract_id_and_slug(match_url, "match")
                if not series_id:
                    continue          
                print(f">>> 正在分析比赛: {teams_name}")
                driver.get(match_url)
                time.sleep(0.1)    
                # 查找地图信息
                map_holders = driver.find_elements(By.CSS_SELECTOR, "div.mapholder")
                for holder in map_holders:
                    try:
                        map_name_el = holder.find_element(By.CSS_SELECTOR, "div.mapname")
                        # 检查是否为 Mirage
                        if "Mirage" in map_name_el.text:
                            stats_link_el = holder.find_element(By.CSS_SELECTOR, "a.results-stats")
                            stats_href = stats_link_el.get_attribute("href")          
                            map_id, _ = extract_id_and_slug(stats_href, "mapstats")
                            if map_id:
                                print(f">>> Map ID: {map_id}")
                                # 组装配置项
                                series_entry = {
                                    "series_id": series_id,
                                    "event_name": event_name,
                                    "map_id": map_id,
                                    "teams_name": teams_name
                                }
                                all_series_config.append(series_entry)
                    except Exception:
                        continue
    # 保存配置
    with open(OUTPUT_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_series_config, f, indent=4, ensure_ascii=False) 
    print("\n>>> 爬取结束")
    print(f">>> 共收集到 {len(all_series_config)} 场比赛")
    driver.quit()

if __name__ == "__main__":
    generate_config()