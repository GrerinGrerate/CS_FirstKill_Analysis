import json
from config import DATA_PATH, OUT_DIR, FIG_DIR
from utils import read_jsonl
from extract import (build_analysis_table,summarize_by_econ_type,summarize_next_round)
from stats_bayes import (summarize_by_group,run_bayes_analysis,save_bayes_result,chi2_analysis,bayes_compare_by_econ_type)
from viz import (make_group_rate_plot,make_bayes_diff_plot,plot_posterior_distributions,plot_posterior_diff_distribution,make_econ_type_plot,plot_next_round_econ_dist)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    #读取数据
    records = read_jsonl(DATA_PATH)

    #构建回合级分析表
    df = build_analysis_table(records)
    if df.empty:
        print("没有构建出有效样本，请检查数据字段")
        return

    print("样本表前5行：")
    print(df.head())

    detail_path = OUT_DIR / "analysis_round_level.csv"
    df.to_csv(detail_path, index=False, encoding="utf-8-sig")
    print(f"已保存明细表: {detail_path}")

    #英雄武器分组统计
    summary_df = summarize_by_group(df, group_col="hero_weapon")
    print("\n英雄武器分组统计：")
    print(summary_df)

    summary_path = OUT_DIR / "summary_by_hero_weapon.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"已保存英雄武器分组统计: {summary_path}")

    #基础贝叶斯比较：英雄武器 vs 非英雄武器
    bayes_result = run_bayes_analysis(df)
    print("\n基础贝叶斯比较结果：")
    print(bayes_result)

    #按经济类型分组统计
    econ_summary = summarize_by_econ_type(df)
    print("\n按经济类型分组统计：")
    print(econ_summary)

    econ_summary_path = OUT_DIR / "summary_by_econ_type.csv"
    econ_summary.to_csv(econ_summary_path, index=False, encoding="utf-8-sig")
    print(f"已保存按经济类型分组统计: {econ_summary_path}")

    #按经济类型进行贝叶斯比较
    bayes_by_econ = bayes_compare_by_econ_type(df)
    print("\n按经济类型贝叶斯比较结果：")
    print(bayes_by_econ)

    #合并贝叶斯输出
    bayes_results = {
        "hero_weapon_overall": bayes_result,
        "by_econ_type": bayes_by_econ,
    }

    bayes_results_path = OUT_DIR / "bayes_results.json"
    save_json(bayes_results_path, bayes_results)
    print(f"已保存合并后的贝叶斯结果: {bayes_results_path}")

    #卡方检验
    chi2_result_path = OUT_DIR / "chi2_analysis.csv"
    chi2_analysis(df, chi2_result_path)
    print(f"已保存卡方检验结果: {chi2_result_path}")

    #下一回合经济情况汇总
    next_round_summary = summarize_next_round(df)
    print("\n下一回合经济情况汇总：")
    print(f"  - 下一回合存在经济劣势队伍的比例: {next_round_summary['any_disadv_rate']:.4f}")
    print(f"  - 原劣势方仍然处于劣势的比例: {next_round_summary['same_disadv_rate']:.4f}")
    print("  - 原劣势方下一回合经济类型分布:")

    for econ_type, rate in next_round_summary["econ_type_distribution"].items():
        print(f"    {econ_type}: {rate:.4f}")

    next_round_summary_path = OUT_DIR / "next_round_summary.json"
    save_json(next_round_summary_path, next_round_summary)
    print(f"已保存下一回合经济情况汇总: {next_round_summary_path}")

    #可视化
    make_group_rate_plot(summary_df, FIG_DIR / "group_rate_compare.png")
    make_bayes_diff_plot(bayes_result, FIG_DIR / "bayes_diff_compare.png")

    plot_posterior_distributions(
        bayes_result,
        FIG_DIR / "posterior_densities.png",
    )
    plot_posterior_diff_distribution(
        bayes_result,
        FIG_DIR / "posterior_diff.png",
    )

    make_econ_type_plot(
        econ_summary,
        FIG_DIR / "econ_type_compare.png",
    )
    plot_next_round_econ_dist(
        next_round_summary,
        FIG_DIR / "next_round_econ_dist.png",
    )

    print("\n全部分析完成。")

if __name__ == "__main__":
    main()