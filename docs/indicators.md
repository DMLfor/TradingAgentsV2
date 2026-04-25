# tdx_core 技术指标库

## 快速上手

```python
from tdx_core import TdxQuery, TdxIndicators

# 方式1：通过股票代码自动获取数据并计算指标
query = TdxQuery()
ind = TdxIndicators(query)
df = ind.calc("000001", indicators=["ma", "macd", "rsi"], start_date="2024-01-01")

# 方式2：直接对 DataFrame 计算
from tdx_core.indicators import ma, macd, rsi, bollinger
df = query.get_daily("000001")
df = ma(df, periods=[5, 10, 20])
df = macd(df)
df = rsi(df, period=14)

# 方式3：静态方法，无需 TdxQuery 实例
df = TdxIndicators.compute(df, indicators=["ma", "bollinger"])

# 方式4：计算全部指标
df = ind.calc("000001")

# 查看可用指标列表
print(TdxIndicators.available_indicators())
```

## 两种列名风格

指标库同时支持 TDX 列名（`open_val/high_val/low_val/close_val`）和标准列名（`open/high/low/close`），自动检测并保留原始列名。

---

## 趋势指标 (Trend)

### MA — 简单移动平均线

**含义**：N 周期内收盘价的算术平均值，反映价格趋势方向。

**用法**：
- 价格在 MA 之上为多头趋势，之下为空头趋势
- 短期 MA 上穿长期 MA 为金叉（买入信号），下穿为死叉（卖出信号）
- 常用周期：5（周线）、10、20（月线）、60（季线）、120（半年线）、250（年线）

```python
df = ma(df, periods=[5, 10, 20, 60, 120, 250])  # 默认值
# 输出列：ma_5, ma_10, ma_20, ma_60, ma_120, ma_250
```

### EMA — 指数移动平均线

**含义**：对近期价格赋予更高权重的移动平均，比 MA 更灵敏。

**用法**：与 MA 类似，但反应更快，适合短线交易。

```python
df = ema(df, periods=[12, 26])  # 默认值
# 输出列：ema_12, ema_26
```

### SMA — 平滑移动平均线

**含义**：Wilder 平滑法（用于 ATR、RSI 等指标内部计算），alpha=1/period。

```python
df = sma(df, periods=[20])
# 输出列：sma_20
```

### WMA — 加权移动平均线

**含义**：近期价格权重更大的移动平均，权重线性递增。

```python
df = wma(df, periods=[20])
# 输出列：wma_20
```

### DEMA — 双指数移动平均线

**含义**：`DEMA = 2*EMA - EMA(EMA)`，减少滞后性。

```python
df = dema(df, periods=[20])
# 输出列：dema_20
```

### TEMA — 三指数移动平均线

**含义**：`TEMA = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))`，进一步减少滞后。

```python
df = tema(df, periods=[20])
# 输出列：tema_20
```

### MACD — 指数平滑异同移动平均线

**含义**：由快慢 EMA 差值（DIF）、信号线（DEA）和柱状图组成，判断趋势强度和方向变化。

**用法**：
- DIF 上穿 DEA → 买入信号
- DIF 下穿 DEA → 卖出信号
- 柱状图由负转正 → 多头动能增强
- 零轴上方为多头市场，下方为空头市场

```python
df = macd(df, fast=12, slow=26, signal=9)  # 默认值
# 输出列：macd, macd_signal, macd_hist
```

### ADX — 平均趋向指数

**含义**：衡量趋势强度（不判断方向），+DI/-DI 判断多空方向。

**用法**：
- ADX > 25：趋势明确（强趋势），< 20：盘整
- +DI > -DI：多头，+DI < -DI：空头

```python
df = adx(df, period=14)
# 输出列：adx, plus_di, minus_di
```

### Aroon — 阿隆指标

**含义**：衡量自最高/最低价以来经过的周期数，判断趋势是否形成或结束。

**用法**：
- Aroon Up 接近 100：强势上涨
- Aroon Down 接近 100：强势下跌
- 两者交叉为趋势转折信号

```python
df = aroon(df, period=25)
# 输出列：aroon_up, aroon_down, aroon_osc
```

### Ichimoku — 一目均衡表

**含义**：日本技术分析系统，同时显示支撑/阻力、趋势方向和动量。

**用法**：
- 价格在云层上方为多头，下方为空头
- 转换线上穿基准线为买入信号
- 云层颜色变化为趋势转换

```python
df = ichimoku(df, tenkan=9, kijun=26, senkou=52)
# 输出列：tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
```

### SAR — 抛物线转向指标

**含义**：跟踪止损指标，SAR 点位随趋势加速远离价格。

**用法**：
- 价格在 SAR 之上为多头，之下为空头
- 价格穿越 SAR 为趋势反转信号

```python
df = sar(df, af_start=0.02, af_max=0.2)
# 输出列：sar
```

### Supertrend — 超级趋势线

**含义**：基于 ATR 的趋势跟踪指标，在价格上下形成动态支撑/阻力。

**用法**：
- 价格在 Supertrend 之上且方向为 -1 → 多头
- 价格在 Supertrend 之下且方向为 1 → 空头

```python
df = supertrend(df, period=10, multiplier=3.0)
# 输出列：supertrend, supertrend_direction
```

### TRIX — 三重平滑 EMA 变动率

**含义**：三重指数移动平均的变化率，过滤短期波动噪声。

**用法**：TRIX 上穿零轴为多头信号，下穿零轴为空头信号。

```python
df = trix(df, period=15)
# 输出列：trix
```

### Vortex — 涡旋指标

**含义**：通过比较 True Range 和价格移动方向识别趋势起点。

**用法**：VI+ 上穿 VI- 为买入信号，下穿为卖出信号。

```python
df = vortex(df, period=14)
# 输出列：vortex_pos, vortex_neg
```

---

## 动量指标 (Momentum)

### RSI — 相对强弱指数

**含义**：衡量价格上涨和下跌力度的比率，范围 0-100。

**用法**：
- RSI > 70：超买（可能回调）
- RSI < 30：超卖（可能反弹）
- 背离：价格创新高但 RSI 未创新高 → 看跌背离

```python
df = rsi(df, period=14)
# 输出列：rsi_14
```

### Stochastic — 随机指标 (KDJ)

**含义**：当前价格在 N 周期高低范围中的相对位置。

**用法**：
- K > 80 且 D > 80：超买
- K < 20 且 D < 20：超卖
- K 上穿 D 为买入信号

```python
df = stochastic(df, k_period=14, d_period=3)
# 输出列：stoch_k, stoch_d
```

### Williams %R — 威廉指标

**含义**：与 Stochastic 类似但反转，范围 -100 到 0。

**用法**：
- > -20：超买
- < -80：超卖

```python
df = williams_r(df, period=14)
# 输出列：williams_r
```

### CCI — 商品通道指数

**含义**：衡量价格偏离统计均值的程度。

**用法**：
- CCI > 100：超买/强上涨
- CCI < -100：超卖/强下跌
- 与零轴交叉为交易信号

```python
df = cci(df, period=20)
# 输出列：cci_20
```

### ROC — 变动率

**含义**：当前价格与 N 周期前价格的百分比变化。

**用法**：ROC > 0 上涨动量，< 0 下跌动量。

```python
df = roc(df, period=12)
# 输出列：roc_12
```

### Momentum — 动量

**含义**：当前价格减去 N 周期前价格，衡量价格变动速度。

```python
df = momentum(df, period=10)
# 输出列：momentum_10
```

### StochRSI — 随机 RSI

**含义**：对 RSI 应用随机指标公式，增强灵敏度。

**用法**：与 Stochastic 类似，0-100 范围。

```python
df = stochrsi(df, rsi_period=14, stoch_period=14, k_period=3, d_period=3)
# 输出列：stochrsi_k, stochrsi_d
```

### Ultimate Oscillator — 终极振荡器

**含义**：综合三个时间周期（7/14/28）的买入压力，减少单周期偏差。

**用法**：
- > 70：超买
- < 30：超卖
- 与价格背离为强信号

```python
df = ultimate_oscillator(df, period1=7, period2=14, period3=28)
# 输出列：ultimate_osc
```

### Awesome Oscillator — 动量震荡指标

**含义**：5 周期与 34 周期中价 SMA 之差，衡量市场动量。

**用法**：
- 由负转正（碟形买入）
- 零轴上方峰值下降 → 看跌

```python
df = awesome_oscillator(df, fast=5, slow=34)
# 输出列：awesome_osc
```

---

## 波动率指标 (Volatility)

### Bollinger Bands — 布林带

**含义**：由中轨（SMA）和上下轨（±N 倍标准差）构成，反映价格波动范围。

**用法**：
- 价格触及上轨：超买/强势
- 价格触及下轨：超卖/弱势
- 带宽收窄预示大行情即将出现
- %b > 1 价格在上轨上方，< 0 在下轨下方

```python
df = bollinger(df, period=20, std_dev=2.0)
# 输出列：bb_upper, bb_middle, bb_lower, bb_bandwidth, bb_pctb
```

### ATR — 真实波幅均值

**含义**：衡量市场波动性，考虑跳空缺口。

**用法**：
- ATR 上升 → 波动加大
- ATR 下降 → 波动减小
- 常用于设置止损距离

```python
df = atr(df, period=14)
# 输出列：atr_14
```

### Keltner Channel — 肯特纳通道

**含义**：基于 EMA 和 ATR 的通道，与布林带类似但基于 ATR 而非标准差。

**用法**：
- 价格突破上轨 → 强势上涨
- 价格突破下轨 → 强势下跌
- 与布林带配合：布林带收窄而 Keltner 未收窄 → 即将突破

```python
df = keltner(df, ema_period=20, atr_period=10, multiplier=1.5)
# 输出列：keltner_upper, keltner_middle, keltner_lower
```

### Donchian Channel — 唐奇安通道

**含义**：N 周期最高价和最低价构成的通道，海龟交易法核心指标。

**用法**：
- 价格突破上轨 → 买入
- 价格突破下轨 → 卖出

```python
df = donchian(df, period=20)
# 输出列：donchian_upper, donchian_middle, donchian_lower
```

### Std Dev — 标准差

**含义**：收盘价的滚动标准差，衡量波动程度。

```python
df = std_dev(df, period=20)
# 输出列：stddev_20
```

### Chaikin Volatility — 蔡金波动率

**含义**：高低价差的 EMA 变动率，衡量波动率变化。

**用法**：
- 上升 → 波动加剧（市场顶部常见）
- 下降 → 波动减小（市场底部常见）

```python
df = chaikin_volatility(df, ema_period=10, roc_period=10)
# 输出列：chaikin_vol
```

---

## 成交量指标 (Volume)

### OBV — 能量潮

**含义**：上涨日累加成交量，下跌日减去成交量，反映资金流向。

**用法**：
- OBV 上升确认价格上涨
- OBV 与价格背离 → 趋势即将反转

```python
df = obv(df)
# 输出列：obv
```

### VWAP — 成交量加权平均价

**含义**：按成交量加权的平均价格，机构常用基准价。

**用法**：价格在 VWAP 之上为多头区域，之下为空头区域。

```python
df = vwap(df)
# 输出列：vwap
```

### MFI — 资金流量指数

**含义**：成交额版 RSI，范围 0-100，反映资金进出强度。

**用法**：
- MFI > 80：超买
- MFI < 20：超卖

```python
df = mfi(df, period=14)
# 输出列：mfi_14
```

### A/D Line — 累积/派发线

**含义**：基于 CLV（收盘价在高低范围中的位置）和成交量的累积指标。

**用法**：与 OBV 类似，但考虑了收盘价在当日范围中的位置。

```python
df = ad_line(df)
# 输出列：ad_line
```

### Chaikin Money Flow — 蔡金资金流量

**含义**：N 周期内 A/D 值占成交量的比例。

**用法**：
- CMF > 0：买方主导
- CMF < 0：卖方主导

```python
df = chaikin_money_flow(df, period=20)
# 输出列：cmf_20
```

### Force Index — 强力指数

**含义**：价格变化 × 成交量，衡量多空力量。

**用法**：
- 正值：多头力量
- 负值：空头力量
- EMA 平滑后与零轴交叉为信号

```python
df = force_index(df, period=13)
# 输出列：force_index_13
```

### Ease of Movement — 简易波动指标

**含义**：衡量价格移动与成交量的关系，高 EOM 表示价格轻松移动。

**用法**：EOM > 0 多头占优，< 0 空头占优。

```python
df = ease_of_movement(df, period=14)
# 输出列：eom_14
```

### Volume ROC — 成交量变动率

**含义**：成交量与 N 周期前的百分比变化。

**用法**：放量（Volume ROC 上升）确认趋势，缩量疑趋势。

```python
df = volume_roc(df, period=12)
# 输出列：vol_roc_12
```

### NVI — 负成交量指数

**含义**：仅在成交量减少日累积价格变化，假设"聪明钱"在清淡日活跃。

**用法**：NVI 上升反映长线资金进场。

```python
df = nvi(df)
# 输出列：nvi
```

---

## 复合指标 (Composite)

### Pivot Points — 枢轴点

**含义**：基于前一周期高低收计算支撑/阻力位。

**用法**：
- 价格在 PP 之上偏多，之下偏空
- R1/R2/R3 为阻力位，S1/S2/S3 为支撑位

```python
df = pivot_points(df, method="standard")  # 可选: "standard", "fibonacci", "camarilla"
# 输出列：pp, r1, r2, r3, s1, s2, s3
```

### Fibonacci Retracement — 斐波那契回撤

**含义**：基于高低价的斐波那契比例（23.6%、38.2%、50%、61.8%、78.6%）计算关键位。

**用法**：价格回调至 38.2% 或 61.8% 常为支撑/阻力。

```python
df = fibonacci_retracement(df)
# 输出列：fib_0, fib_236, fib_382, fib_500, fib_618, fib_786, fib_1000
```

### TD Sequential — TD 序列（简化版）

**含义**：计数连续收盘价高于/低于 4 周期前收盘价的次数，识别趋势衰竭。

**用法**：
- 计数达 9 → 买入/卖出设置完成
- 正数表示买入设置，负数表示卖出设置

```python
df = td_sequential(df)
# 输出列：td_setup, td_countdown
```
