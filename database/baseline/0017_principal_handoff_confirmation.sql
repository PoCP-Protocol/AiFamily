-- 0017_principal_handoff_confirmation — M3-W2R-105 Human Confirmation 闭环
-- 依赖:0011(principal_human_handoffs)、0013(resolve 溯源列)。
-- 目的:质量闸判 REVIEW 的候选响应不再直接展示给家长,而是【扣留】并挂到 handoff;
--       人工复核 APPROVED 后才【释放】给家长(Human Gate 闭环)。
-- 边界:handoff 仍非 canonical;复核/释放不写 Growth 事实。幂等:ADD COLUMN IF NOT EXISTS。

ALTER TABLE principal_human_handoffs
  ADD COLUMN IF NOT EXISTS response_id uuid NULL
    REFERENCES principal_responses(response_id) ON DELETE SET NULL,  -- 被扣留、待人工确认的候选响应
  ADD COLUMN IF NOT EXISTS released_at timestamptz NULL;             -- 人工 APPROVED 后释放给家长的时刻(null=未释放)

-- 查"某响应是否已因人工确认而释放"的窄索引(仅已释放行)
CREATE INDEX IF NOT EXISTS idx_principal_handoffs_released
  ON principal_human_handoffs(response_id)
  WHERE released_at IS NOT NULL;
