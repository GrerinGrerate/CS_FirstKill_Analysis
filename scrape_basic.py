# scrape_basic.py
# 基础信息与经济数据爬虫的主入口程序

from scrapers import setup_driver, get_players_from_stats_page, get_economy_data, load_config, append_jsonl, load_completed_ids, iter_matches

# 主爬虫逻辑，依次处理每场比赛，抓取选手信息和经济数据，并记录成功或失败状态
def main():
    # 文件路径和读取配置
    output_path = "dataset/basic_info.jsonl"
    cache_path = "cache/completed_basic.jsonl"

    config_data = load_config("dataset/matches_config.json")
    pending_matches = list(iter_matches(config_data))
    
    completed = load_completed_ids(cache_path)

    print(f">>> 待处理比赛总数: {len(pending_matches)}")
    print(f">>> 已完成比赛总数: {len(completed)}")

    driver = setup_driver()
    try:
        driver.get("https://www.hltv.org")
        input(">>>")

        for idx, match in enumerate(pending_matches, 1):
            map_id = match["map_id"]
            match_name = match["match_name"]
            
            if map_id in completed:
                print(f">>> [{idx}/{len(pending_matches)}] 跳过已完成: {match_name}")
                continue

            stats_url = f"https://www.hltv.org/stats/matches/mapstatsid/{map_id}/{match_name}"
            print(f"\n>>> [{idx}/{len(pending_matches)}] 开始爬取: {match_name}")

            metadata = {
                "series_id": match["series_id"],
                "event_name": match["event_name"],
                "map_id": map_id,
                "match_name": match_name,
                "stats_page_url": stats_url
            }
            try:
                # 抓取选手信息
                players = get_players_from_stats_page(driver, stats_url)

                # 抓取经济信息
                economy = get_economy_data(driver, map_id, match_name)

                # 组装合理的数据输出结构
                record = {
                    "metadata": metadata,
                    "status": "ok",
                    "data": {
                        "players": players,
                        "economy": economy
                    }
                }

                # 将完整数据写入数据集
                append_jsonl(output_path, record)
                # 将 map_id 和成功状态写入 cache，供后续运行检查
                append_jsonl(cache_path, {"map_id": map_id, "status": "ok"})
                
                completed.add(map_id)
                print(">>> 抓取成功，已保存")

            except Exception as e:
                # 记录失败状态，保留 metadata 以备排查
                record = {
                    "metadata": metadata,
                    "status": "failed",
                    "error": str(e)
                }
                append_jsonl(output_path, record)
                print(">>> 抓取异常")

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()