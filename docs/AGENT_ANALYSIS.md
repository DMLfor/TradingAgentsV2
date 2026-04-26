# Agent 多维度分析模块使用文档

> 参考 ai-hedge-fund 架构实现的 A 股技术分析 Agent 系统。
> 基于 LangGraph 并行编排 5 个 specialist persona agent → Risk Manager → Portfolio Manager。

---

## 1. 简介

Agent 多维度分析模块对单只股票执行**并行多维度技术分析**，每个分析师都有独立的角色身份和投资哲学，最终由投资总监在风险约束下做出综合决策。

### 1.1 角色体系（7 个角色）

每个角色都有：**独立身份 + System Prompt + 量化打分（Step 1）+ LLM 推理（Step 2）**。

| 角色 | 中文名 | 投资哲学 | 核心指标 | LLM |
|:---|:---|:---|:---|:---:|
| **TrendFollower** | 趋势跟踪者 | "趋势是朋友" | MA 排列、MACD、ADX | **是** |
| **MeanReversionTrader** | 均值回归者 | "物极必反" | RSI、布林带、Stochastic、CCI | **是** |
| **MomentumHunter** | 动量猎人 | "强者恒强" | 价格动量、RSI、CCI、MACD 柱状线 | **是** |
| **VolatilityTrader** | 波动率交易者 | "低波动蓄势，高波动出货" | 布林带带宽、ATR、%B | **是** |
| **VolumeAnalyst** | 量价分析师 | "量为价先" | OBV、MFI、CMF、量比 | **是** |
| **RiskManager** | 风险控制官 | "活着才有输出" | ATR、波动率、回撤、分析师分歧度 | **是** |
| **PortfolioManager** | 投资总监 | "集思广益，果断决策" | 综合 5 维信号 + 风险约束 | **是** |

### 1.2 工作流程

```
数据加载（TdxQuery + 82 个指标）
    |
    v
start_node
    |
    +---> TrendFollower（并行）
    +---> MeanReversionTrader（并行）
    +---> MomentumHunter（并行）
    +---> VolatilityTrader（并行）
    +---> VolumeAnalyst（并行）
    |
    v
RiskManager（串行，等待所有 specialist）
    |
    v
PortfolioManager（串行，等待 RiskManager）
    |
    v
输出 CLI 报告 + 保存文件
```

### 1.3 Two-step 架构

每个 specialist 采用 ai-hedge-fund 风格的 **Two-step** 架构：

1. **Step 1 — 量化打分**：Python 纯算法计算指标得分、生成 facts dict
2. **Step 2 — LLM Persona 推理**：将 facts + system prompt（角色身份/决策 checklist）发送给 LLM，返回带角色的 reasoning

如果 `--no-llm` 或 API 不可用，Step 2 自动退化为算法 fallback。

---

## 2. 安装依赖

首次使用需确保依赖已安装：

```bash
pip install langgraph langchain-core langchain-openai openai pydantic colorama python-dotenv
```

或重新安装项目依赖：

```bash
pip install -e .
```

---

## 3. 快速开始

### 3.1 单股分析（默认模式，优先使用 LLM）

```bash
python scripts/agent_analyze.py 688018
```

### 3.2 纯算法模式（无 LLM token 消耗）

```bash
python scripts/agent_analyze.py 688018 --no-llm
```

### 3.3 指定模型

```bash
python scripts/agent_analyze.py 688018 --model moonshot-v1-8k
```

### 3.4 保存报告

```bash
python scripts/agent_analyze.py 688018 --save
```

---

## 4. CLI 参数详解

### 4.1 `scripts/agent_analyze.py`

| 参数 | 默认值 | 说明 |
|:---|:---:|:---|
| `code` | **必填** | 股票代码，如 `688018`、`515180` |
| `--bars` | `120` | 分析窗口天数 |
| `--save` | `False` | 保存报告到 `results/analysis/YYYY-MM-DD/` |
| `--no-llm` | `False` | 禁用 LLM，所有角色退化为纯算法 |
| `--model` | `None` | LLM 模型名称，覆盖 `KIMI_MODEL` 环境变量 |

### 4.2 统一 CLI 入口 `tdx agent`

```bash
tdx agent -c 688018 --bars 120 --save
tdx agent -c 515180 --no-llm
tdx agent -c 688018 --model moonshot-v1-8k
```

---

## 5. 输出解读

### 5.1 CLI 终端输出示例

```
[1/7] 数据加载 ................ 完成 (242条K线, 82个指标)

[2/7] Specialist Agents 并行计算中 ...
      -> 趋势跟踪者        [偏多] confidence: 90%
         ma_5=14.36, ma_20=14.28, ma_60=14.34, macd=0.00, macd_signal=-0.03, macd_hist=0.03
         均线多头排列，MACD金叉，ADX=40.6确认趋势强度，总分90/100
      -> 均值回归者        [偏空] confidence: 15%
         rsi_14=55.30, bb_pctb=0.86, stoch_k=94.87, stoch_d=91.88, cci_20=112.17
         RSI=55.3超买，布林带%B=0.86接近上轨，共2项指标超买，总分15/100
      -> 动量猎人         [中性] confidence: 75%
         rsi_14=55.30, cci_20=112.17, macd_hist=0.03, close=14.42, ret_5d_pct=1.34
         5日涨幅1.3%，动量一般，RSI=55.3，总分75/100
      -> 波动率交易者       [中性] confidence: 70%
         bb_pctb=0.86, bb_bandwidth=0.03, atr_14=0.15, atr_percentile=10.00
         布林带%B=0.86中位，ATR百分位=10.0%波动中性，总分70/100
      -> 量价分析师        [偏多] confidence: 65%
         obv=4196830508.00, mfi_14=66.49, cmf_20=0.24, volume_ratio=1.12
         OBV创新高，CMF=0.24资金净流入，量比1.1，总分65/100

[5/7] 风险控制评估 ........... 完成

      -> 风险控制官     [低风险] 建议仓位: 80%
         止损位: 14.13, 近20日最大回撤: 3.3%
         风险可控：ATR百分位10.0%，近20日最大回撤3.3%，分析师分歧低

[6/7] 投资总监综合判断 ....... 算法聚合完成
[7/7] 结果生成 ............... 完成

============== Agent 多维度分析报告: 515180 (515180) ==============

[投资总监综合判断] 6.6/10 [中性偏强]  confidence: 64%

 reasoning:
  算法综合评分6.6/10。均值回归偏空(置信度15%)，动量中性(置信度75%)，
  趋势偏多(置信度90%)，波动率中性(置信度70%)，量价偏多(置信度65%)。
  风险等级：low。各维度加权聚合得出最终判断。

 action_plan: 持有观察，等待更明确信号
 risk_notes: 风险等级low，关注趋势逆转信号

------------------------------------------------------------

综合信号汇总表:
Agent        | Signal   | Confidence | 权重
---------------------------------------------
趋势跟踪者        | 偏多       | 90         | 0.25
均值回归者        | 偏空       | 15         | 0.20
动量猎人         | 中性       | 75         | 0.20
波动率交易者       | 中性       | 70         | 0.15
量价分析师        | 偏多       | 65         | 0.20
---------------------------------------------
加权综合         | 中性偏强     | 64         | 1.00
风险控制         | 低风险      | 仓位80   | -
```

### 5.2 信号含义

| Signal | 中文 | 分数区间 | 含义 |
|:---|:---|:---:|:---|
| `bullish` | 偏多 | - | 该维度指标整体看多 |
| `bearish` | 偏空 | - | 该维度指标整体看空 |
| `neutral` | 中性 | - | 该维度指标方向不明确 |
| `强烈偏多` | - | >= 7.8 | 综合强烈看多 |
| `谨慎偏多` | - | 7.0 ~ 7.8 | 综合偏多，但需警惕风险 |
| `中性偏强` | - | 6.0 ~ 7.0 | 略偏多，观望为主 |
| `中性` | - | 5.0 ~ 6.0 | 多空平衡 |
| `中性偏弱` | - | 4.0 ~ 5.0 | 略偏空 |
| `谨慎偏空` | - | < 4.0 | 综合偏空 |

### 5.3 评分体系

- **Composite Score**: 0 ~ 10 分，与 `technical_master.py` 的评分体系兼容
- **Confidence**: 0 ~ 100，反映各维度信号的一致性和强度
- **权重分配**: 趋势 25%、均值回归 20%、动量 20%、波动率 15%、量价 20%

---

## 6. LLM 配置

### 6.1 配置环境变量

在项目根目录 `.env` 文件中添加：

```bash
# Moonshot 标准 API（推荐）
KIMI_API_KEY=sk-你的标准APIKey
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.6                # 默认模型
```

> **注意**：Kimi Code CLI 注入的 `https://api.kimi.com/coding/v1` 端点**仅限 Coding Agent 工具使用**，Python SDK 直接调用会返回 403。必须使用标准 Moonshot API 端点。

### 6.2 获取标准 API Key

1. 访问 [Moonshot 开放平台](https://platform.moonshot.cn/)
2. 注册账号 → 创建 API Key
3. 复制 Key 到 `.env` 文件

### 6.3 测试连通性

```bash
python -c "
from dotenv import load_dotenv
load_dotenv('.env')
from tdx_core.agent.llm_client import LLMClient
client = LLMClient()
result = client.call(
    [{'role': 'user', 'content': '你好'}],
    type('Model', (), {'__annotations__': {'reply': str}})
)
print(result)
"
```

---

## 7. 无 LLM 模式（纯算法）

如果环境没有配置 API Key，或希望节省 token：

```bash
python scripts/agent_analyze.py 688018 --no-llm
```

此模式下：
- 5 个 specialist agent 执行 Step 1（量化打分），跳过 Step 2（LLM 推理）
- Risk Manager 执行量化风险评估，跳过 LLM 推理
- Portfolio Manager 执行算法加权聚合，跳过 LLM 推理
- 不消耗任何 LLM token
- reasoning 为算法自动生成的模板文本

---

## 8. 保存报告

使用 `--save` 会生成两个文件：

```
results/analysis/2026-04-26/
  688018_agent_analysis.md      # Markdown 可读报告
  688018_agent_metrics.json     # 结构化 JSON 数据
```

### 8.1 Markdown 报告内容

- 综合评分表（评分/信号/置信度/操作建议/风险提示）
- 风险控制表（风险等级/止损位/建议仓位/最大回撤）
- 各维度分析详情（signal/confidence/reasoning/metrics）

### 8.2 JSON 数据格式

```json
{
  "code": "688018",
  "name": "乐鑫科技",
  "signals": {
    "trend_follower": { "688018": { "signal": "bullish", "confidence": 90, ... } },
    "mean_reversion_trader": { ... },
    "momentum_hunter": { ... },
    "volatility_trader": { ... },
    "volume_analyst": { ... }
  },
  "risk": {
    "risk_level": "low",
    "stop_loss": 14.13,
    "position_size_pct": 80,
    "risk_notes": "...",
    "max_drawdown_20d": 3.3
  },
  "composite": {
    "signal": "中性偏强",
    "confidence": 64,
    "composite_score": 6.6,
    "reasoning": "...",
    "action_plan": "...",
    "risk_notes": "..."
  }
}
```

---

## 9. 故障排除

| 问题 | 原因 | 解决方案 |
|:---|:---|:---|
| `ModuleNotFoundError: No module named 'langgraph'` | 依赖未安装 | `pip install langgraph langchain-core langchain-openai openai pydantic colorama python-dotenv` |
| `RuntimeError: KIMI_API_KEY or OPENAI_API_KEY required` | 环境变量未配置 | 在 `.env` 中添加 `KIMI_API_KEY=sk-xxx` |
| `403 PermissionDeniedError` | 使用了 Coding 端点 | 将 `KIMI_BASE_URL` 改为 `https://api.moonshot.cn/v1` |
| `404 NotFoundError` | 模型名称错误 | 默认使用 `kimi-k2.6`，可通过 `--model` 覆盖 |
| 综合评分显示 `0.0/10` 且 reasoning 为 `LLM调用失败` | LLM 调用异常 | 检查网络/API Key/额度；或加 `--no-llm` 使用纯算法 |
| 某维度 confidence 为 0 | 该指标数据缺失（NaN） | 正常现象，数据缺失时自动降级为 neutral |
| 首次运行很慢（>2分钟） | 7 个角色都需 LLM 推理 | 正常现象，缓存命中后（`data/llm_cache.json`）会快很多 |

---

## 10. 与其他模块的对比

| 模块 | 分析深度 | LLM | 适用场景 |
|:---|:---|:---:|:---|
| `technical_master.py` | 37 指标 + 多周期 + 背离检测 | 否 | 最全面的单股技术诊断 |
| `analyze_stock.py` | 指定指标扫描 + 信号回测 | 否 | 快速查看特定指标 |
| **`agent_analyze.py`** | **5 维 persona + 风控 + 投资总监** | **是** | **需要叙事性分析和操作建议** |
| `daily_market_review.py` | 全市场 11 维度复盘 | 否 | 每日盘后复盘 |

---

## 11. 扩展开发

### 11.1 添加新 Specialist Agent

在 `tdx_core/agent/agents/` 下新建文件，参考现有 agent 模式：

```python
from tdx_core.agent.base import AgentSignal, _cast
from tdx_core.agent.graph.state import AgentState
from tdx_core.agent.llm_client import LLMClient, llm_available
from tdx_core.agent.agents.persona_prompts import PERSONA_PROMPTS

AGENT_ID = "my_agent"

def _quant_analysis(df) -> dict:
    # Step 1: Python 量化打分
    facts = {"total_score": 50, "metrics": {}, ...}
    return facts

def _algo_fallback(facts: dict) -> dict:
    # 纯算法 fallback
    result = AgentSignal(signal="neutral", confidence=50, reasoning="...", metrics=facts["metrics"])
    return result.model_dump_casted()

def _build_prompt(facts: dict) -> list[dict]:
    return [
        {"role": "system", "content": PERSONA_PROMPTS[AGENT_ID]},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]

def my_agent(state: AgentState) -> dict:
    code = state["data"]["code"]
    df = state["data"]["df"]
    use_llm = state["data"].get("use_llm", True)
    model = state["data"].get("model")

    facts = _quant_analysis(df)

    if use_llm and llm_available():
        try:
            client = LLMClient(model=model)
            result = client.call(_build_prompt(facts), AgentSignal)
            signal_data = result.model_dump_casted()
        except Exception:
            signal_data = _algo_fallback(facts)
    else:
        signal_data = _algo_fallback(facts)

    signal_data["code"] = code
    state["data"].setdefault("analyst_signals", {})[AGENT_ID] = {code: signal_data}
    return {"messages": [...], "data": state["data"]}
```

然后在 `tdx_core/agent/graph/workflow.py` 的 `ANALYST_CONFIG` 中注册，并在 `tdx_core/agent/agents/persona_prompts.py` 中添加 system prompt。

### 11.2 修改角色 System Prompt

编辑 `tdx_core/agent/agents/persona_prompts.py` 中对应角色的字符串，调整 checklist、signal 规则、confidence scale 等。

---

*文档版本: 2026-04-26*
*对应代码版本: tdx_core/agent/ + scripts/agent_analyze.py*
