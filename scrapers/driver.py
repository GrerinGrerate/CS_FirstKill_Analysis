# scrapers/driver.py
# 所有爬虫都需要用到的 selenium 驱动配置

import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 启动 Chrome 浏览器，返回 driver 对象，对目前运行环境做了对于适配
def setup_driver():
    chrome_options = Options()
    # 设置页面加载策略为 eager，不用等待图片和广告加载
    chrome_options.page_load_strategy = 'eager'
    # 关掉图片和通知
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2
    }
    chrome_options.add_experimental_option("prefs", prefs)
    # 反自动化检测
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # WSL 环境下需要的稳定性参数
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3")
    # 每次随机一个调试端口
    port = random.randint(9200, 9999)
    chrome_options.add_argument(f"--remote-debugging-port={port}")
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    # 注入脚本，把 navigator.webdriver 属性隐藏掉
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver
