# scrapers/basic_info.py
# 比赛页面基础信息爬取逻辑

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 直接从对战统计页 (stats) 抓取并返回所有参赛选手的字典集合 {player_id: player_name}
def get_players_from_stats_page(driver, stats_url):
    driver.get(stats_url)

    # 等待包含选手的表格元素加载完毕
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.stats-table td.st-player"))
        )
    except Exception:
        print(f">>> 选手名单加载超时: {stats_url}")
        return {}

    # 停止页面加载
    try:
        driver.execute_script("window.stop();")
    except Exception:
        pass

    # 解析 DOM，提取所有的 player_id 和 player_name
    soup = BeautifulSoup(driver.page_source, "html.parser")
    players = {}

    # 查找所有的选手单元格
    for td in soup.find_all("td", class_="st-player"):
        a_tag = td.find("a")
        if a_tag and "href" in a_tag.attrs:
            # 链接格式在 stats 页面为 /stats/players/{id}/{name}
            href = a_tag["href"]
            parts = href.strip("/").split("/")
            
            # 确保切分后的路径是期望的格式
            if len(parts) >= 4 and parts[0] == "stats" and parts[1] == "players":
                player_id = parts[2]
                player_name = parts[3]
                players[player_id] = player_name

    return players