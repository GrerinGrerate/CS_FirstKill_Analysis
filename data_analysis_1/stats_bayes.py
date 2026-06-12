import json
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

#原有函数保持不变  
def safe_rate(x):
    if len(x) == 0:
        return np.nan
    return np.mean(x)
#按分组统计函数，计算首杀率、胜率和失败后下一回合仍劣势率
def summarize_by_group(df, group_col="hero_weapon"):
    out = []
    for g, sub in df.groupby(group_col):
        n = len(sub)
        first_kill_rate = safe_rate(sub["disadv_first_kill"].dropna().values)
        win_rate = safe_rate(sub["disadv_win"].dropna().values)
        fail_sub = sub[sub["disadv_win"] == 0]
        fail_n = len(fail_sub)
        next_rate = np.nan
        valid_next = fail_sub["next_still_disadv"].dropna()
        if len(valid_next) > 0:
            next_rate = np.mean(valid_next.values)
        out.append({
            group_col: g,
            "n_rounds": n,
            "first_kill_rate": first_kill_rate,
            "win_rate": win_rate,
            "fail_n": fail_n,
            "next_still_disadv_rate_after_fail": next_rate
        })
    return pd.DataFrame(out).sort_values(group_col).reset_index(drop=True)

def beta_posterior_samples(success, total, size=20000, seed=42):
    rng = np.random.default_rng(seed)
    a = 1 + success
    b = 1 + total - success
    return rng.beta(a, b, size=size)
#贝叶斯后验分布比较，返回p值和差异的均值及95%置信区间
def bayes_compare_two_groups(success1, total1, success0, total0, size=20000, seed=42):
    s1 = beta_posterior_samples(success1, total1, size=size, seed=seed)
    s0 = beta_posterior_samples(success0, total0, size=size, seed=seed + 1)
    prob_gt = np.mean(s1 > s0)
    diff = s1 - s0
    return {
        "p_gt": float(prob_gt),
        "diff_mean": float(np.mean(diff)),
        "diff_ci_2.5": float(np.quantile(diff, 0.025)),
        "diff_ci_97.5": float(np.quantile(diff, 0.975)),
        "group1_mean": float(np.mean(s1)),
        "group0_mean": float(np.mean(s0))
    }
#按经济类型分组统计和贝叶斯比较函数
def run_bayes_analysis(df):
    result = {}
    g1 = df[df["hero_weapon"] == 1]
    g0 = df[df["hero_weapon"] == 0]
    #首杀率
    y1_fk = int(g1["disadv_first_kill"].sum())
    n1_fk = int(len(g1))
    y0_fk = int(g0["disadv_first_kill"].sum())
    n0_fk = int(len(g0))
    if n1_fk > 0 and n0_fk > 0:
        result["first_kill"] = bayes_compare_two_groups(y1_fk, n1_fk, y0_fk, n0_fk)
        result["first_kill"]["counts"] = {"hero_success": y1_fk, "hero_total": n1_fk, "nohero_success": y0_fk, "nohero_total": n0_fk}
    else:
        result["first_kill"] = None
    #胜率
    y1_w = int(g1["disadv_win"].sum())
    n1_w = int(len(g1))
    y0_w = int(g0["disadv_win"].sum())
    n0_w = int(len(g0))
    if n1_w > 0 and n0_w > 0:
        result["win_rate"] = bayes_compare_two_groups(y1_w, n1_w, y0_w, n0_w)
        result["win_rate"]["counts"] = {"hero_success": y1_w, "hero_total": n1_w, "nohero_success": y0_w, "nohero_total": n0_w}
    else:
        result["win_rate"] = None
    #失败后下一回合仍劣势率
    g1_fail = g1[g1["disadv_win"] == 0]["next_still_disadv"].dropna()
    g0_fail = g0[g0["disadv_win"] == 0]["next_still_disadv"].dropna()
    y1_n = int(g1_fail.sum()) if len(g1_fail) > 0 else 0
    n1_n = int(len(g1_fail))
    y0_n = int(g0_fail.sum()) if len(g0_fail) > 0 else 0
    n0_n = int(len(g0_fail))
    if n1_n > 0 and n0_n > 0:
        result["next_still_disadv_after_fail"] = bayes_compare_two_groups(y1_n, n1_n, y0_n, n0_n)
        result["next_still_disadv_after_fail"]["counts"] = {"hero_success": y1_n, "hero_total": n1_n, "nohero_success": y0_n, "nohero_total": n0_n}
    else:
        result["next_still_disadv_after_fail"] = None
    return result

def save_bayes_result(path, bayes_result):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bayes_result, f, ensure_ascii=False, indent=2)
#计算Cramér's V值，衡量两个分类变量之间的关联强度
def cramers_v(confusion_matrix):
    chi2 = chi2_contingency(confusion_matrix)[0]
    n = confusion_matrix.sum().sum()
    phi2 = chi2 / n
    r, k = confusion_matrix.shape
    phi2corr = max(0, phi2 - ((k-1)*(r-1))/(n-1))
    rcorr = r - ((r-1)**2)/(n-1)
    kcorr = k - ((k-1)**2)/(n-1)
    return np.sqrt(phi2corr / min((kcorr-1), (rcorr-1)))
#卡方检验分析
def chi2_analysis(df, output_path):
    results = []
    tab_fk = pd.crosstab(df['hero_weapon'], df['disadv_first_kill'])
    chi2_fk, p_fk, _, _ = chi2_contingency(tab_fk)
    v_fk = cramers_v(tab_fk.values)
    results.append({'metric': 'first_kill', 'chi2': chi2_fk, 'p_value': p_fk, 'cramers_v': v_fk, 'n': len(df)})
    tab_win = pd.crosstab(df['hero_weapon'], df['disadv_win'])
    chi2_win, p_win, _, _ = chi2_contingency(tab_win)
    v_win = cramers_v(tab_win.values)
    results.append({'metric': 'win_rate', 'chi2': chi2_win, 'p_value': p_win, 'cramers_v': v_win, 'n': len(df)})
    fail_df = df[df['disadv_win'] == 0].dropna(subset=['next_still_disadv'])
    if len(fail_df) > 0:
        tab_next = pd.crosstab(fail_df['hero_weapon'], fail_df['next_still_disadv'])
        chi2_next, p_next, _, _ = chi2_contingency(tab_next)
        v_next = cramers_v(tab_next.values)
        results.append({'metric': 'next_still_disadv_after_fail', 'chi2': chi2_next, 'p_value': p_next, 'cramers_v': v_next, 'n': len(fail_df)})
    else:
        results.append({'metric': 'next_still_disadv_after_fail', 'chi2': np.nan, 'p_value': np.nan, 'cramers_v': np.nan, 'n': 0})
    result_df = pd.DataFrame(results)
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"已保存卡方检验结果: {output_path}")
    return result_df

#按经济类型分组统计  
def summarize_by_econ_type(df):
    rows = []
    for econ_type, sub in df.groupby("disadv_econ_type"):
        for hero_val, sub2 in sub.groupby("hero_weapon"):
            n = len(sub2)
            fk_rate = safe_rate(sub2["disadv_first_kill"])
            win_rate = safe_rate(sub2["disadv_win"])
            #失败后下一回合仍劣势率
            fail_sub = sub2[sub2["disadv_win"] == 0]
            next_rate = np.nan
            if len(fail_sub) > 0:
                valid_next = fail_sub["next_still_disadv"].dropna()
                if len(valid_next) > 0:
                    next_rate = np.mean(valid_next)
            rows.append({
                "econ_type": econ_type,
                "hero_weapon": hero_val,
                "n_rounds": n,
                "first_kill_rate": fk_rate,
                "win_rate": win_rate,
                "next_still_disadv_rate_after_fail": next_rate
            })
    return pd.DataFrame(rows)
#按经济类型进行贝叶斯比较
def bayes_compare_by_econ_type(df):
    results = {}
    for econ_type, sub in df.groupby("disadv_econ_type"):
        g1 = sub[sub["hero_weapon"] == 1]
        g0 = sub[sub["hero_weapon"] == 0]
        if len(g1) == 0 or len(g0) == 0:
            continue
        econ_res = {}
        #首杀
        y1_fk = int(g1["disadv_first_kill"].sum())
        n1_fk = len(g1)
        y0_fk = int(g0["disadv_first_kill"].sum())
        n0_fk = len(g0)
        if n1_fk > 0 and n0_fk > 0:
            econ_res["first_kill"] = bayes_compare_two_groups(y1_fk, n1_fk, y0_fk, n0_fk)
        #胜率
        y1_w = int(g1["disadv_win"].sum())
        n1_w = len(g1)
        y0_w = int(g0["disadv_win"].sum())
        n0_w = len(g0)
        if n1_w > 0 and n0_w > 0:
            econ_res["win_rate"] = bayes_compare_two_groups(y1_w, n1_w, y0_w, n0_w)
        #失败后下一回合仍劣势率
        g1_fail = g1[g1["disadv_win"] == 0]["next_still_disadv"].dropna()
        g0_fail = g0[g0["disadv_win"] == 0]["next_still_disadv"].dropna()
        if len(g1_fail) > 0 and len(g0_fail) > 0:
            y1_n = int(g1_fail.sum())
            n1_n = len(g1_fail)
            y0_n = int(g0_fail.sum())
            n0_n = len(g0_fail)
            if n1_n > 0 and n0_n > 0:
                econ_res["next_still_disadv_after_fail"] = bayes_compare_two_groups(y1_n, n1_n, y0_n, n0_n)
        results[econ_type] = econ_res
    return results

#下一回合经济情况汇总  
def summarize_next_round(df):
    #下一回合是否有经济劣势队伍 
    any_disadv_rate = safe_rate(df["next_round_any_disadv"].dropna())
    #原劣势方是否仍然劣势
    same_disadv_rate = safe_rate(df["next_round_same_disadv"].dropna())
    #原劣势方下一回合的经济类型分布
    econ_type_counts = df["next_round_econ_type"].value_counts(dropna=False)
    total_valid = df["next_round_econ_type"].notna().sum()
    econ_type_rates = (econ_type_counts / total_valid).to_dict()
    
    return {
        "any_disadv_rate": any_disadv_rate,
        "same_disadv_rate": same_disadv_rate,
        "econ_type_distribution": econ_type_rates,
        "total_rounds": len(df),
        "valid_next_rounds": total_valid
    }