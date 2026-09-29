# -*- coding: utf-8 -*-
"""Figure 1 content: every line is pre-wrapped to fit its box, so no text is
shrunk below its designed point size."""
import sys
sys.path.insert(0, r"D:\Industrial Programme I\_build")
from flowlib import L, INK, SUB  # noqa: E402

S_HEAD, S_SUB = 16.5, 9.0
S_TITLE, S_BODY, S_NOTE = 12.4, 8.6, 8.4

HEAD = [
    L("导师方案：Price + Open Interest Regime Signal", S_HEAD, "bold", INK, 1.45),
    L("用「价格 x 未平仓量」把加密永续的行情切成四种状态，\n"
      "检验这些状态对未来收益 / 波动 / 反转是否具备预测力\n"
      "目标是先搭起一套干净、可解释的研究框架，不是马上产出可上线的策略", 10.2, "normal", INK, 1.7),
    L("Theo Industrial Project Idea Note ｜ First Test Plan 共五个阶段", S_SUB, "normal", SUB, 1.6),
]
UNIV = [
    L("第一版只做 Binance：BTC / ETH 永续 + 流动性前 30-50 的 USDT 永续；\n"
      "剔除稳定币、上市过新、OI 数据不可靠、流动性不足的合约", 8.8, "normal", SUB, 1.6),
]
D1 = [
    L("① 数据 Data", S_TITLE, "bold"),
    L("OHLCV：收益 / 波动 / 动量\nOpen Interest：持仓扩张或收缩\n"
      "Funding：拥挤度与杠杆成本\nVolume：流动性与参与度\n"
      "Mark / Index：定价一致性\nLiquidation（可选）", S_BODY, "normal", INK, 1.62),
    L("频率：1h 为主，4h / 8h / 1d 做稳健性\n全部统一 UTC 时间戳", S_NOTE, "normal", SUB, 1.55),
]
D2 = [
    L("② 信号定义 Signal", S_TITLE, "bold"),
    L("price_change =\nclose_t / close_(t-N) - 1\n\noi_change =\nOI_t / OI_(t-N) - 1", 8.8, "normal", INK, 1.62),
    L("固定回看窗口 N；每个资产、\n每个时点都用同一口径", S_NOTE, "normal", SUB, 1.55),
]
D3 = [
    L("③ 阈值过滤 Threshold", S_TITLE, "bold"),
    L("|price_change| > price_threshold\n|oi_change| > oi_threshold", 8.4, "normal", INK, 1.62),
    L("起点：滚动 60 / 70 分位，\n或 z-score 阈值\n阈值只用于稳健性检验，\n不允许为了回测好看调参", S_NOTE, "normal", SUB, 1.55),
]
D4 = [
    L("④ 资金费率状态 Funding", S_TITLE, "bold"),
    L("负费率    低于滚动 25 分位\n中性        25 - 75 分位\n"
      "高正费率  高于 75 分位\n极端        高于 90 分位", 8.8, "normal", INK, 1.62),
    L("定位：条件变量 conditioning\nvariable，不是主信号", S_NOTE, "normal", SUB, 1.55),
]
REG = [
    L("⑤ 四象限状态分类 Regime", S_TITLE, "bold"),
    L("R1  价涨 + OI 升 = 新多进场\nR2  价涨 + OI 降 = 空头回补\n"
      "R3  价跌 + OI 升 = 新空进场\nR4  价跌 + OI 降 = 平仓 / 去杠杆", 8.8, "normal", INK, 1.62),
]
XTAB = [
    L("⑥ 交叉表格：4 x 4 = 16 个格子", S_TITLE, "bold"),
    L("4 个价格/OI 状态 x 4 档资金费率；\n每一格分别统计前向收益、\n前向波动、反转 / 延续概率", 8.8, "normal", INK, 1.62),
    L("导师给的事前预期（是假设，不是结论）：\n"
      "· 价升 OI 升 + 中性费率 → 延续\n"
      "· 价升 OI 升 + 极端正费率 → 拥挤后反转型风险\n"
      "· 价升 OI 降 → 空头回补，动能可能耗尽\n"
      "· 价跌 OI 升 + 中性费率 → 继续下行\n"
      "· 价跌 OI 升 + 极端负费率 → 逼空风险\n"
      "· 价跌 OI 降 + 高波动压力 → 去杠杆后均值回复", S_NOTE, "normal", SUB, 1.58),
]
OUT = [
    L("⑦ 要检验的四种「未来结果」Forward Outcomes", S_TITLE, "bold"),
    L("A  前向收益：1h / 4h / 8h / 24h 的\n     forward_return(t,h) = close_(t+h) / close_t - 1\n"
      "B  前向波动：某些状态是否预示更高的\n     未来已实现波动\n"
      "C  反转 vs 延续：未来走势是延续原方向、\n     反向，还是完全无关系（no edge）\n"
      "D  路径风险：最大有利偏移 MFE /\n     最大不利偏移 MAE / 持有期内回撤", 8.8, "normal", INK, 1.68),
    L("D 被单独列出，是因为「平均收益为正、但路径很难看」的信号不能算好信号", S_NOTE, "normal", SUB, 1.55),
]
MET = [
    L("⑧ 评价指标 Metrics", S_TITLE, "bold"),
    L("各状态前向收益 · 命中率 hit rate\n反转概率 / 延续概率\n"
      "事件后已实现波动\n最大不利偏移 MAE · 换手率 turnover\n"
      "交易成本敏感性 cost sensitivity\nIC（信号转成排序分数时）\n"
      "分资产表现 · 分市场状态表现", 8.6, "normal", INK, 1.62),
]
BASE = [
    L("⑨ 基线对比 Baseline：框架必须先打败这四个", 12.0, "bold"),
    L("价格动量单独用 ｜ OI 变化单独用 ｜\n资金费率单独用 ｜ 随机时点进场", 9.0, "normal", INK, 1.6),
    L("价格/OI 框架只有在比这四个简单基线都\n解释得更好时，才算真的「有增量」。\n"
      "换句话说：导师把「没有增量」设为默认\n答案，需要被证伪的是这个框架本身。", S_NOTE, "normal", SUB, 1.58),
]
VERD = [
    L("⑩ 结论 Verdict", 12.0, "bold"),
    L("赢过基线 → 价格 + OI 确实提供了\n价格之外的增量信息\n"
      "没赢过 → 零假设成立，如实记录为负结果", 8.8, "normal", INK, 1.6),
    L("两种结果都可以写进报告 —— 这正是\n「先做事件研究、再谈策略」的意义。", S_NOTE, "normal", SUB, 1.58),
]
DELIV = [
    L("交付物 D1 - D6：D1 干净数据管线 / D2 状态分类器 /\n"
      "D3 事件研究报告 / D4 简单策略原型（含成本回测）/\n"
      "D5 看板 / D6 期末报告与答辩", 9.2, "normal", INK, 1.62),
    L("D4 被明确限定为 exploratory backtest，而不是 production strategy；\n"
      "D6 要回答的就是最开始那一句：加入 open interest，\n"
      "是否比只看价格更能理解加密永续的短期行为。", S_NOTE, "normal", SUB, 1.58),
]
