# scrapers/heatmap_utils.py
# 封装用于提取 HLTV 比赛热图坐标及武器数据的通用函数

import json
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 解析对应 URL 下的热图坐标数据
def get_heatmap_coords(driver, url):
    driver.get(url)
    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "worker-ignore.heatmap-data")))
    soup = BeautifulSoup(driver.page_source, "html.parser")
    tag = soup.find("worker-ignore", class_="heatmap-data")
    coords_data = []
    raw_data = json.loads(tag.get("data-heatmap-config", "{}")).get("heatmapData", {}).get("data", [])
    for item in raw_data:
        parts = item.split(",")
        if len(parts) >= 2:
            coord_str = f"{parts[0].strip()},{parts[1].strip()}"
            count = int(parts[2].strip()) if len(parts) >= 3 else 1
            coords_data.append({
                "pos": coord_str,
                "count": count
            })
    return coords_data

# 获取某位选手在本场比赛中产生过击杀的所有武器
def get_player_weapons_list(driver, player_id, base_params, base_url):
    url = f"{base_url}?players={player_id}&{base_params}&showKills=true&showDeaths=false"
    driver.get(url)
    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "select.onchange-action")))
    weapons = []
    select_tag = BeautifulSoup(driver.page_source, "html.parser").find("select", class_="onchange-action")
    if select_tag:
        for option in select_tag.find_all("option"):
            match = re.search(r'weapons=\d+-([\w]+)', option.get("data-select-action", ""))
            if match and match.group(1).lower() != "all":
                weapons.append(match.group(1))
    return weapons

# 获取选手的击杀/阵亡热图数据
def get_paired_cross_coords(driver, player_id, is_kill_view, base_params, base_url):
    if is_kill_view:
        url_k = f"{base_url}?players={player_id}&weapons={player_id}-All&{base_params}&showKills=true&showDeaths=false&showKillDataset=true&showDeathDataset=false"
        url_v = f"{base_url}?players={player_id}&weapons={player_id}-All&{base_params}&showKills=true&showDeaths=false&showKillDataset=false&showDeathDataset=true"
    else:
        url_k = f"{base_url}?players={player_id}&weapons={player_id}-All&{base_params}&showKills=false&showDeaths=true&showKillDataset=true&showDeathDataset=false"
        url_v = f"{base_url}?players={player_id}&weapons={player_id}-All&{base_params}&showKills=false&showDeaths=true&showKillDataset=false&showDeathDataset=true"
    coords_k = get_heatmap_coords(driver, url_k)
    coords_v = get_heatmap_coords(driver, url_v)
    return {
        "killer_coords": coords_k,
        "victim_coords": coords_v
    }