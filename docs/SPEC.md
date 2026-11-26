# 服饰退货复核队列

值班仓管按日结前包裹扫描排队验包。样例是合成退货授权、称重、异店转送和历史验包标签，保留扫描修订、面单跨店、虚假体重和历史未结单据。每个退款授权最多派发一个复核位。容量单位为当班最多可以受理几件包裹，默认九件。

按商品组拟合经营历史中的绝对称重偏差中位数，下限保留称量设备误差。重新派件时使用该时点可见的退款历史。模型是带 L2 的四维逻辑回归，标签按结单时间切分，前三四分之三用于训练、末段用于保序校准。训练域外物件和开封包裹进入人工待核，超过原门店配额仍保留审理队列。金额整数单位为分，页面将其换算为元。

历史阈值复盘仅计算已完成验包记录。平均精确率按同分组聚合，未发现错件的窗口显示不可计算。该历史样本无法评估未被复核退货的真实错件率。曲线显示各个阈值下会漏掉的退款金额。


## 输入记录

### 验包流水

- `rma` 类型 `str`。
- `shop` 类型 `str`。
- `carrier` 类型 `str`。
- `label` 类型 `str`。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `observed` 类型 `int`，有效范围 0–10000000。
- `weight` 类型 `int`，有效范围 1–90000。
- `seal` 类型 `bool`。
- `revision` 类型 `int`，有效范围 1–200。
### 换店去重

- `rma` 类型 `str`。
- `shop` 类型 `str`。
- `parcel_key` 类型 `str`。
- `customer` 类型 `str`。
- `original_shop` 类型 `str`。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `submitted` 类型 `int`，有效范围 0–10000000。
- `weight` 类型 `int`，有效范围 1–90000。
- `seal` 类型 `bool`。
### 退货特征

- `rma` 类型 `str`。
- `original_shop` 类型 `str`。
- `category` 类型 `str`。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `submitted` 类型 `int`，有效范围 0–10000000。
- `weight` 类型 `int`，有效范围 1–90000。
- `listed_weight` 类型 `int`，有效范围 1–90000。
- `prior_returns` 类型 `int`，有效范围 0–100。
- `seal` 类型 `bool`。
- `amount` 类型 `int`，有效范围 1–1000000。
- `priority` 类型 `bool`。
### 验包评分

- `rma` 类型 `str`。
- `original_shop` 类型 `str`。
- `category` 类型 `str`。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `weight_z` 类型 `float`，有效范围 0–100。
- `open_seal` 类型 `float`，有效范围 0–1。
- `repeat_log` 类型 `float`，有效范围 0–10。
- `extra_days` 类型 `float`，有效范围 0–300。
- `found_mismatch` 类型 `bool`。
- `labeled` 类型 `int`，有效范围 0–10000000。
### 复核配额

- `rma` 类型 `str`。
- `original_shop` 类型 `str`。
- `category` 类型 `str`。
- `reason` 类型 `str`。
- `score` 类型 `float`，有效范围 0–1。
- `in_scope` 类型 `bool`。
- `amount` 类型 `int`，有效范围 1–1000000。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `priority` 类型 `bool`。
- `seal` 类型 `bool`。
### 退货复盘

- `rma` 类型 `str`。
- `shop` 类型 `str`。
- `score` 类型 `float`，有效范围 0–1。
- `amount` 类型 `int`，有效范围 1–1000000。
- `mismatch` 类型 `bool`。
- `reviewed` 类型 `bool`。
- `arrival` 类型 `int`，有效范围 0–10000000。
- `closed` 类型 `int`，有效范围 0–10000000。

## 终审与预算证据

验包回测滑动验证点分别锁定训练、校准和后验窗口，展示类别校准差与拒绝原因。复核位试算输出各门店待核份额、已占用名额和未覆盖本金，并标注当前容量成本下的方案前沿。退款台账用原门店加授权单号对账，重复载货标签、金额差异和复核位冲突保留独立原因。试算建议并未调用支付系统。
