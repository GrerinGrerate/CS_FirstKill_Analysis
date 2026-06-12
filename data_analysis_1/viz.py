import numpy as np
import pandas as pd
from plotnine import *

#绘制英雄组与非英雄组关键比例对比图（柱状图，分面）
def make_group_rate_plot(summary_df, save_path):
    plot_df = summary_df.copy()

    long_rows = []
    for _, row in plot_df.iterrows():
        g = row["hero_weapon"]
        label = "HeroWeapon=1" if int(g) == 1 else "HeroWeapon=0"

        long_rows.append({"group": label, "metric": "first_kill_rate", "rate": row["first_kill_rate"]})
        long_rows.append({"group": label, "metric": "win_rate", "rate": row["win_rate"]})
        long_rows.append({
            "group": label,
            "metric": "next_still_disadv_rate_after_fail",
            "rate": row["next_still_disadv_rate_after_fail"]
        })

    long_df = pd.DataFrame(long_rows)

    p = (
        ggplot(long_df, aes(x="group", y="rate", fill="group"))
        + geom_col(show_legend=False)
        + facet_wrap("~metric", scales="free_y")
        + scale_y_continuous(limits=(0, 1))
        + labs(
            title="经济劣势回合:Hero vs NoHero 关键比例对比",
            x="组别",
            y="比例"
        )
        + theme_bw(base_family='FangSong')#全局字体始终不显示，只能在每个theme里单独设置字体
        + theme(
            figure_size=(10, 4),
            axis_text_x=element_text(rotation=0),
            subplots_adjust={"wspace": 0.25}
        )
    )
    p.save(save_path, dpi=150)
    print(f"已保存图表: {save_path}")
#绘制贝叶斯后验差值及95%区间图
def make_bayes_diff_plot(bayes_result, save_path):
    rows = []
    for k, v in bayes_result.items():
        if v is None:
            continue
        rows.append({
            "metric": k,
            "mean_diff": v["diff_mean"],
            "ci_low": v["diff_ci_2.5"],
            "ci_high": v["diff_ci_97.5"]
        })

    if len(rows) == 0:
        print("贝叶斯结果为空，跳过差值图")
        return

    df = pd.DataFrame(rows)

    p = (
        ggplot(df, aes(x="metric", y="mean_diff"))
        + geom_point(size=2)
        + geom_errorbar(aes(ymin="ci_low", ymax="ci_high"), width=0.15)
        + geom_hline(yintercept=0, linetype="dashed")
        + labs(
            title="后验差值(Hero - NoHero)及95%区间",
            x="指标",
            y="后验差值"
        )
        + theme_bw(base_family='FangSong')
        + theme(
            figure_size=(9, 4),
            axis_text_x=element_text(rotation=20, ha="right")
        )
    )
    p.save(save_path, dpi=150)
    print(f"已保存图表: {save_path}")
#根据bayes_result.json中的计数，绘制后验密度图
def plot_posterior_distributions(bayes_result, save_path):
    if not isinstance(bayes_result, dict):
        print("贝叶斯结果格式不正确，无法绘制后验分布")
        return

    from scipy.stats import beta

    def beta_pdf(x, a, b):
        return beta.pdf(x, a, b)

    rows = []
    for metric, res in bayes_result.items():
        if res is None or 'counts' not in res:
            continue
        counts = res['counts']
        hero_success = counts['hero_success']
        hero_total = counts['hero_total']
        nohero_success = counts['nohero_success']
        nohero_total = counts['nohero_total']

        a_hero = 1 + hero_success
        b_hero = 1 + hero_total - hero_success
        a_no = 1 + nohero_success
        b_no = 1 + nohero_total - nohero_success

        x = np.linspace(0, 1, 500)
        y_hero = beta_pdf(x, a_hero, b_hero)
        y_no = beta_pdf(x, a_no, b_no)

        for xi, yi in zip(x, y_hero):
            rows.append({'metric': metric, 'group': 'hero', 'p': xi, 'density': yi})
        for xi, yi in zip(x, y_no):
            rows.append({'metric': metric, 'group': 'nohero', 'p': xi, 'density': yi})

    if not rows:
        print("无可用的后验分布数据")
        return

    df_plot = pd.DataFrame(rows)

    p = (
        ggplot(df_plot, aes(x='p', y='density', color='group'))
        + geom_density(stat='identity', alpha=0.5)
        + facet_wrap('~metric', scales='free_y')
        + labs(
            title='后验概率密度分布：英雄武器 vs 非英雄武器',
            x='真实概率',
            y='密度',
            color='策略组'
        )
        + theme_bw(base_family='FangSong')
        + theme(
            figure_size=(10, 6),
            axis_text_x=element_text(rotation=0),
            subplots_adjust={'wspace': 0.3}
        )
    )
    p.save(save_path, dpi=150)
    print(f"已保存后验分布图: {save_path}")

#绘制后验差异分布（英雄-非英雄）直方图和密度曲线
def plot_posterior_diff_distribution(bayes_result, save_path, n_samples=20000, seed=42):
    if not isinstance(bayes_result, dict):
        print("贝叶斯结果格式不正确，无法绘制差异分布")
        return

    rows = []
    rng = np.random.default_rng(seed)
    for metric, res in bayes_result.items():
        if res is None or 'counts' not in res:
            continue
        counts = res['counts']
        hero_success = counts['hero_success']
        hero_total = counts['hero_total']
        nohero_success = counts['nohero_success']
        nohero_total = counts['nohero_total']

        a_hero = 1 + hero_success
        b_hero = 1 + hero_total - hero_success
        a_no = 1 + nohero_success
        b_no = 1 + nohero_total - nohero_success

        samples_hero = rng.beta(a_hero, b_hero, n_samples)
        samples_no = rng.beta(a_no, b_no, n_samples)
        diff = samples_hero - samples_no

        rows.extend([{'metric': metric, 'diff': d} for d in diff])

    if not rows:
        print("无可用的差异分布数据")
        return

    df_plot = pd.DataFrame(rows)

    p = (
        ggplot(df_plot, aes(x='diff'))
        + geom_histogram(bins=50, fill='steelblue', alpha=0.7)
        + geom_density(color='darkred', size=1)
        + geom_vline(xintercept=0, linetype='dashed', color='gray')
        + facet_wrap('~metric', scales='free')
        + labs(
            title='后验差异分布（英雄 - 非英雄）及 95% 可信区间',
            x='概率差异',
            y='频数 / 密度'
        )
        + theme_bw(base_family='FangSong')
        + theme(
            figure_size=(10, 4),
            axis_text_x=element_text(rotation=0)
        )
    )
    p.save(save_path, dpi=150)
    print(f"已保存后验差异分布图: {save_path}")
#绘制不同经济类型下，英雄武器 vs 非英雄武器的三项指标对比
def make_econ_type_plot(econ_summary_df, save_path):
    plot_data = []
    for _, row in econ_summary_df.iterrows():
        econ = row["econ_type"]
        hero = "Hero" if row["hero_weapon"] == 1 else "NoHero"
        plot_data.append({"econ_type": econ, "group": hero, "metric": "first_kill_rate", "value": row["first_kill_rate"]})
        plot_data.append({"econ_type": econ, "group": hero, "metric": "win_rate", "value": row["win_rate"]})
        plot_data.append({"econ_type": econ, "group": hero, "metric": "next_still_disadv_after_fail", "value": row["next_still_disadv_rate_after_fail"]})
    plot_df = pd.DataFrame(plot_data)

    p = (ggplot(plot_df, aes(x="econ_type", y="value", fill="group"))
         + geom_col(position="dodge")
         + facet_wrap("~metric", scales="free_y")
         + labs(title="不同经济类型下英雄武器效果对比", x="经济类型", y="比例")
         + theme_bw(base_family='FangSong')
         + theme(figure_size=(12, 5), axis_text_x=element_text(rotation=45, ha="right"))
    )
    p.save(save_path, dpi=150)
    print(f"已保存经济类型对比图: {save_path}")
#绘制劣势方下一回合的经济类型分布（仅针对有下一回合的样本）
def plot_next_round_econ_dist(df, save_path):
    valid = df.dropna(subset=["next_round_econ_type"]).copy()
    if len(valid) == 0:
        print("没有可用的下一回合经济数据，跳过绘图")
        return
    plot_data = []
    for hero_val, sub in valid.groupby("hero_weapon"):
        hero_label = "Hero" if hero_val == 1 else "NoHero"
        counts = sub["next_round_econ_type"].value_counts()
        total = counts.sum()
        for econ_type, cnt in counts.items():
            plot_data.append({"hero_weapon": hero_label, "econ_type": econ_type, "proportion": cnt / total})
    plot_df = pd.DataFrame(plot_data)
    p = (ggplot(plot_df, aes(x="econ_type", y="proportion", fill="hero_weapon"))
         + geom_col(position="dodge")
         + labs(title="劣势方下一回合经济类型分布（按本回合是否英雄武器分组）", x="经济类型", y="比例")
         + theme_bw(base_family='FangSong')
         + theme(figure_size=(8, 4), axis_text_x=element_text(rotation=45, ha="right"))
    )
    p.save(save_path, dpi=150)
    print(f"已保存下一回合经济分布图: {save_path}")