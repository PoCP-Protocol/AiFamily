-- 0013_principal_review_workflow — M3-103 REVIEW 人工复核工作流
-- 依赖:0011(principal_human_handoffs)。为 REVIEW/HIGH_RISK 队列补解决(resolve)溯源列。
-- handoff 仍非 canonical;复核结论不写 Growth 事实。幂等:ADD COLUMN IF NOT EXISTS。

ALTER TABLE principal_human_handoffs
  ADD COLUMN IF NOT EXISTS resolution varchar(32) NULL,        -- APPROVED | REJECTED | ESCALATED | INFO_ONLY
  ADD COLUMN IF NOT EXISTS resolution_note text NULL,
  ADD COLUMN IF NOT EXISTS resolved_by_actor_id varchar(128) NULL,
  ADD COLUMN IF NOT EXISTS resolved_at timestamptz NULL;

CREATE INDEX IF NOT EXISTS idx_principal_handoffs_open
  ON principal_human_handoffs(family_id, created_at DESC)
  WHERE status = 'OPEN';
