# scrapers/economy.py
# 用于爬取并解析对局回合经济信息的模块，包括装备价值提取和经济局型分类。

import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 根据队伍单回合装备总价值，对经济局型进行分类
def classify_economy(value):
    if value <= 5000: 
        return "Eco"
    if value <= 10000: 
        return "Semi-Eco"
    if value <= 20000: 
        return "Semi-Buy"
    return "Full Buy"

# 访问指定地图的 economy 页面，抓取双方每回合的装备价值并进行分类评估
def get_economy_data(driver, map_id, match_name):
    url = f"https://www.hltv.org/stats/matches/economy/mapstatsid/{map_id}/{match_name}"
    driver.get(url)
    # 等待经济数据表格加载完毕
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.equipment-categories")))
    driver.execute_script("window.stop();")
    soup = BeautifulSoup(driver.page_source, "html.parser")
    economy_data = {}
    # 获取所有半场的经济表格
    tables = soup.find_all('table', class_='equipment-categories')
    current_global_round = 1
    for table in tables:
        rows = table.find_all('tr', class_='team-categories')
        # 提取双方队伍名称
        team_names = []
        for row in rows[:2]:
            team_td = row.find('td', class_='team')
            img = team_td.find('img') if team_td else None
            team_names.append(img.get('title', 'Unknown') if img else 'Unknown')
        # 解析单个半场的每一回合数据
        for r_idx in range(12):
            # 如果当前索引超出了实际回合数，说明半场结束，跳出当前循环
            if r_idx >= len(rows[0].find_all('td', class_='equipment-category-td')):
                break
            economy_data[current_global_round] = {}
            # 分别处理两支队伍在该回合的经济数据
            for team_idx in range(2):
                tds = rows[team_idx].find_all('td', class_='equipment-category-td')
                if r_idx < len(tds):
                    # 获取悬浮窗的文本内容
                    title_text = tds[r_idx].get('title', '')
                    # 匹配具体数值
                    match = re.search(r'Equipment value:\s*(\d+)', title_text)
                    val = int(match.group(1)) if match else 0
                    economy_data[current_global_round][team_names[team_idx]] = {
                        "value": val,
                        "type": classify_economy(val)
                    }
            current_global_round += 1      
            # 超过 24 回合（加时赛）不统计经济，因为一定是长枪局
            if current_global_round > 24:
                return economy_data
    return economy_data