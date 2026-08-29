-- 0012_principal_action_bridge — M3-101A-C Action Bridge 溯源列
-- 依赖:0011(principal_action_proposals)。仅为「被采纳的 proposal → 既有 StartIntervention Named Action」记录桥接溯源。
-- proposal 仍非 canonical(0011 的 canonical=false CHECK 不变);canonical 事实/状态仍只在 Growth OS(intervention_episodes/growth_actions)。
-- 幂等:ADD COLUMN IF NOT EXISTS。

ALTER TABLE principal_action_proposals
  ADD COLUMN IF NOT EXISTS accepted_episode_id uuid NULL REFERENCES intervention_episodes(episode_id),
  ADD COLUMN IF NOT EXISTS accepted_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS accepted_by_actor_id varchar(128) NULL;

-- status 允许值(0011 默认 'PROPOSED'):PROPOSED → ACCEPTED(桥接成功);其余状态由代码管理,不在此加 CHECK 以免与既有行冲突。
CREATE INDEX IF NOT EXISTS idx_principal_proposals_accepted_episode
  ON principal_action_proposals(accepted_episode_id)
  WHERE accepted_episode_id IS NOT NULL;
