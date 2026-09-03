# ADR-0101：版本化合成多模态 Gold Set

## 状态

Accepted — 2026-08-30

## 决策

评测使用代码生成的、可复现的 `gold.v1` 合成数据集：文本 50、图片 40、音频
40、视频 30、混合模态 40，共 200 个 case；其中 40 个为拒答/对抗样本。Case
只保存 opaque fixture reference，不保存媒体字节、URL、家庭或未成年人信息。每个
版本由稳定 fingerprint 标识，CI、staging 和发布演练必须使用同一版本。

## 边界

- Gold Set 只验证 schema、安全、拒答、provenance、延迟和成本，不代表教育效果、
  家庭总分或孩子成绩。
- 数据集生成器不调用模型、不读取凭据；模型结果仍由离线评测 runner 注入。
- 报告归档、切片 runner 和真实供应商合规审批仍是后续能力，不因数据集存在而自动
  允许生产发布。

## 证据

- `backend/intelligence/experience/gold_set.py`
- `tests/intelligence/experience/test_gold_set.py`
- `backend/intelligence/experience/multimodal_eval.py`
