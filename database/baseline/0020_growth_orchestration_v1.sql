-- 0020_growth_orchestration_v1 — FAMILY-GROWTH-VERTICAL-SLICE-001 编排域最小持久化
-- 授权:per-phase runtime(base master 2ce16a3)。仅纵切最小表;NON_CANONICAL 服务域,绝不复用
-- growth_onboardings/growth_priorities/intervention_episodes 存 V3 对象;不写 GrowthPriority/Action/Observation。
-- 幂等:IF NOT EXISTS / DO$$ duplicate_object 守卫。ContextReuseProjection=读模型(不建真相表)。

-- ---------- 枚举 ----------
DO $$ BEGIN CREATE TYPE growth_need_source AS ENUM ('MANUAL','PRINCIPAL','SERVICE_FOLLOWUP'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE growth_intent_status AS ENUM ('OPEN','CLOSED','CANCELLED','SUPERSEDED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE resource_recommendation_status AS ENUM ('PROPOSED','SHOWN','SUPERSEDED','EXPIRED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE family_decision_type AS ENUM ('ACCEPT_RECOMMENDATION','SELECT_ALTERNATIVE','DISMISS'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE orchestration_plan_status AS ENUM ('DRAFT','PROPOSED','ACCEPTED','SUPERSEDED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE service_case_status AS ENUM ('OPEN','ASSIGNED','IN_PROGRESS','WAITING_FAMILY','ESCALATED','COMPLETED','CANCELLED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE eligibility_stage AS ENUM ('T1','T2'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE followup_helpfulness AS ENUM ('HELPFUL','SOMEWHAT_HELPFUL','NOT_HELPFUL_YET','UNANSWERED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE followup_truth_class AS ENUM ('PERSPECTIVE','SERVICE_NOTE','OBSERVATION_CANDIDATE'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------- 服务层原始输入(NeedSignal.raw_ref 指向;非 canonical,不复制到多处真相)----------
CREATE TABLE IF NOT EXISTS growth_need_inputs (
  input_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),   -- 谁说的(家长关于孩子的陈述,需 provenance)
  data_class varchar(48) NOT NULL DEFAULT 'FAMILY_PRIVATE_TEXT',
  raw_text text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gni_family ON growth_need_inputs(family_id);

-- ---------- ① GrowthNeedSignal(NON_CANONICAL 推断)----------
CREATE TABLE IF NOT EXISTS growth_need_signals (
  signal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  source growth_need_source NOT NULL,
  raw_ref uuid NOT NULL REFERENCES growth_need_inputs(input_id),
  inferred_need_type varchar(64) NULL,
  confidence numeric(4,3) NOT NULL DEFAULT 0,
  canonical_family_fact boolean NOT NULL DEFAULT false CHECK (canonical_family_fact = false),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gns_family ON growth_need_signals(family_id);

-- ---------- ② GrowthIntent(家长显式确认后才存在)----------
CREATE TABLE IF NOT EXISTS growth_intents (
  intent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  signal_ref uuid NULL REFERENCES growth_need_signals(signal_id),
  need_type varchar(64) NOT NULL,
  goal_text text NOT NULL,
  required_capability_keys text[] NOT NULL,
  status growth_intent_status NOT NULL DEFAULT 'OPEN',
  close_reason varchar(48) NULL,
  confirmed_by uuid NOT NULL REFERENCES persons(person_id),
  confirmed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_gi_family ON growth_intents(family_id);

-- ---------- Eligibility 评估(T1/T2;可追溯)----------
CREATE TABLE IF NOT EXISTS eligibility_evaluations (
  eligibility_evaluation_ref uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  intent_ref uuid NOT NULL REFERENCES growth_intents(intent_id),
  stage eligibility_stage NOT NULL,
  offer_ref varchar(96) NOT NULL,
  eligible boolean NOT NULL,
  reason_codes text[] NOT NULL DEFAULT '{}',
  offer_snapshot jsonb NOT NULL,   -- T1/T2 复验用的 exact Offer 不可变快照(禁 T2 重新生成猜类型)
  policy_version varchar(48) NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_elig_intent ON eligibility_evaluations(intent_ref);
CREATE INDEX IF NOT EXISTS idx_elig_offer ON eligibility_evaluations(intent_ref, stage, offer_ref);

-- ---------- ⑤ ResourceRecommendation(candidates/coverage 存 jsonb)----------
CREATE TABLE IF NOT EXISTS resource_recommendations (
  recommendation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  intent_ref uuid NOT NULL REFERENCES growth_intents(intent_id),
  version integer NOT NULL DEFAULT 1,
  candidates jsonb NOT NULL,
  recommended_offer_refs text[] NOT NULL,
  required_capability_keys text[] NOT NULL,
  covered_capability_keys text[] NOT NULL,
  uncovered_capability_keys text[] NOT NULL,
  why_now text NOT NULL,
  status resource_recommendation_status NOT NULL DEFAULT 'SHOWN',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rec_intent ON resource_recommendations(intent_ref);

-- ---------- 〔边界〕FamilyServiceDecision ----------
CREATE TABLE IF NOT EXISTS family_service_decisions (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  intent_ref uuid NOT NULL REFERENCES growth_intents(intent_id),
  recommendation_ref uuid NOT NULL REFERENCES resource_recommendations(recommendation_id),
  recommendation_version integer NOT NULL,
  decision_type family_decision_type NOT NULL,
  selected_offer_refs text[] NOT NULL DEFAULT '{}',
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  decided_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fsd_intent ON family_service_decisions(intent_ref);

-- ---------- ⑥ OrchestrationPlan(声明式;steps jsonb;无执行真相)----------
CREATE TABLE IF NOT EXISTS orchestration_plans (
  plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  intent_ref uuid NOT NULL REFERENCES growth_intents(intent_id),
  version integer NOT NULL DEFAULT 1,
  accepted_by_decision_ref uuid NOT NULL REFERENCES family_service_decisions(decision_id),
  steps jsonb NOT NULL,
  status orchestration_plan_status NOT NULL DEFAULT 'ACCEPTED',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_plan_intent ON orchestration_plans(intent_ref);

-- ---------- ⑦ ServiceCase(执行真相;Steward 拥有)----------
CREATE TABLE IF NOT EXISTS service_cases (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  intent_ref uuid NOT NULL REFERENCES growth_intents(intent_id),
  plan_ref uuid NOT NULL REFERENCES orchestration_plans(plan_id),
  status service_case_status NOT NULL DEFAULT 'OPEN',
  owner varchar(96) NOT NULL,
  opened_at timestamptz NOT NULL DEFAULT now(),
  next_action_at timestamptz NULL,
  closed_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_case_family ON service_cases(family_id);

-- ---------- ⑧ ServiceContribution ----------
CREATE TABLE IF NOT EXISTS service_contributions (
  contribution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_ref uuid NOT NULL REFERENCES service_cases(case_id),
  provider_ref varchar(96) NULL,
  role varchar(48) NOT NULL,
  task_ref varchar(96) NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  quality_state varchar(32) NOT NULL DEFAULT 'RECORDED'
);
CREATE INDEX IF NOT EXISTS idx_contrib_case ON service_contributions(case_ref);

-- ---------- 回访(服务层;含 helpfulness;非 canonical Observation)----------
CREATE TABLE IF NOT EXISTS service_followup_responses (
  followup_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_ref uuid NOT NULL REFERENCES service_cases(case_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),  -- helpfulness 是某人的服务价值陈述,需 provenance
  response_ref text NULL,
  helpfulness followup_helpfulness NOT NULL DEFAULT 'UNANSWERED',
  truth_class followup_truth_class NOT NULL DEFAULT 'SERVICE_NOTE',
  captured_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_followup_case ON service_followup_responses(case_ref);
