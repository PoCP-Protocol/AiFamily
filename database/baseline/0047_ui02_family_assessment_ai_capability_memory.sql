-- 0044_ui02_family_assessment_ai_capability_memory
-- Family assessment becomes a versioned AI capability asset. This stores
-- measurement design memory, not private long-term memory of a family.

CREATE TABLE IF NOT EXISTS family_assessment_capability_memory_assets (
  memory_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability_ref varchar(96) NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  memory_kind varchar(32) NOT NULL CHECK (memory_kind IN ('DIMENSION','ITEM','EVIDENCE_ANCHOR','PRACTICE_PATTERN','OUTCOME_FEEDBACK')),
  dimension_ref varchar(96) NOT NULL DEFAULT '',
  item_ref varchar(96) NOT NULL DEFAULT '',
  title varchar(160) NOT NULL,
  payload jsonb NOT NULL,
  evidence_level varchar(8) NOT NULL DEFAULT 'E1',
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','HOLD','REJECTED')),
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (capability_ref, version_no, memory_kind, dimension_ref, item_ref)
);

INSERT INTO family_assessment_capability_memory_assets(
  capability_ref, version_no, memory_kind, dimension_ref, item_ref, title, payload, evidence_level, admission_status, status
) VALUES
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'DIMENSION','LEARNING_HABITS','','学习习惯','{"operational_definition":"家庭情境中孩子启动、维持、完成学习任务时获得结构支持的情况。","observable_signals":["作业启动","困难坚持","家庭学习节奏"],"boundary":"不推断智力、学习障碍或学习成绩原因。"}'::jsonb,'E1','ADMITTED','ACTIVE'),
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'DIMENSION','EMOTION_REGULATION','','情绪管理','{"operational_definition":"孩子情绪触发、表达、恢复，以及家长共同调节支持的家庭互动情况。","observable_signals":["恢复时间","冲突暂停","家长回应策略"],"boundary":"不判断心理疾病、气质类型或临床风险。"}'::jsonb,'E1','ADMITTED','ACTIVE'),
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'DIMENSION','PARENT_CHILD_COMMUNICATION','','亲子沟通','{"operational_definition":"孩子是否愿意表达、家长是否能倾听，以及冲突后关系修复的家庭循环。","observable_signals":["表达意愿","讲道理/纠正循环","冲突修复"],"boundary":"不把一次冲突概括成关系事实或孩子性格标签。"}'::jsonb,'E1','ADMITTED','ACTIVE'),
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'DIMENSION','DEVICE_USE_CONTEXT','','手机依赖','{"operational_definition":"数字设备使用对睡眠、作业、家庭节奏与亲子规则协商的影响。","observable_signals":["日常功能干扰","围绕设备冲突","规则一致性"],"boundary":"不使用成瘾诊断，不把设备问题单独归因于孩子。"}'::jsonb,'E1','ADMITTED','ACTIVE'),
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'DIMENSION','SELF_REGULATION','','自律能力','{"operational_definition":"孩子在家庭支持下参与计划、执行、检查和复盘的自我管理过程。","observable_signals":["监督依赖","自主参与","方法复盘"],"boundary":"不评价孩子懒惰或意志品质，不生成能力排名。"}'::jsonb,'E1','ADMITTED','ACTIVE'),
('FAMILY_ASSESSMENT_AI_CAPABILITY',1,'OUTCOME_FEEDBACK','','','测评迭代反馈信号','{"signals":["completion_rate","dropoff_item_ref","not_sure_rate","parent_feedback","human_review_outcome","followup_action_usefulness"]}'::jsonb,'E1','ADMITTED','ACTIVE')
ON CONFLICT (capability_ref, version_no, memory_kind, dimension_ref, item_ref) DO UPDATE SET
  title = EXCLUDED.title,
  payload = EXCLUDED.payload,
  evidence_level = EXCLUDED.evidence_level,
  admission_status = EXCLUDED.admission_status,
  status = EXCLUDED.status,
  updated_at = now();

INSERT INTO family_assessment_tools(
  tool_ref, version_no, title, purpose, status, admission_status,
  evidence_level, schema_ref, item_schema, boundary, effective_from
) VALUES (
  'FAMILY_SUPPORT_NEEDS', 2, '智能家庭支持需要测评',
  '通过五维入口与方向深追题，帮助家庭形成下一步支持建议', 'ACTIVE', 'ADMITTED',
  'E1', 'family://assessment/FAMILY_SUPPORT_NEEDS/v2',
  '{
    "items": [
      {"item_ref":"FOCUS","response_type":"SINGLE_CHOICE","required":true,"options":["LEARNING_HABITS","EMOTION_REGULATION","PARENT_CHILD_COMMUNICATION","DEVICE_USE_CONTEXT","SELF_REGULATION"]},
      {"item_ref":"FAMILY_STRUCTURE","response_type":"SINGLE_CHOICE","required":false,"options":["TWO_PARENT","SINGLE_PARENT","BLENDED","PREFER_NOT_TO_SAY"]},
      {"item_ref":"CHILD_GENDER","response_type":"SINGLE_CHOICE","required":false,"options":["BOY","GIRL","SELF_DESCRIBED","PREFER_NOT_TO_SAY"]},
      {"item_ref":"LEARNING_HABITS_Q01","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"LEARNING_HABITS_Q02","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"LEARNING_HABITS_Q03","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"EMOTION_REGULATION_Q01","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"EMOTION_REGULATION_Q02","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"EMOTION_REGULATION_Q03","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"PARENT_CHILD_COMMUNICATION_Q01","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"PARENT_CHILD_COMMUNICATION_Q02","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"PARENT_CHILD_COMMUNICATION_Q03","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"DEVICE_USE_CONTEXT_Q01","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"DEVICE_USE_CONTEXT_Q02","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"DEVICE_USE_CONTEXT_Q03","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"SELF_REGULATION_Q01","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"SELF_REGULATION_Q02","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]},
      {"item_ref":"SELF_REGULATION_Q03","response_type":"SINGLE_CHOICE","required":false,"options":["OFTEN","SOMETIMES","RARELY","NOT_SURE"]}
    ]
  }'::jsonb,
  '{"truth_class":"FAMILY_PERSPECTIVE","capability_ref":"FAMILY_ASSESSMENT_AI_CAPABILITY","ai_use_case":"ASSESSMENT_INTERPRETATION","memory_kinds":["DIMENSION","ITEM","EVIDENCE_ANCHOR","PRACTICE_PATTERN","OUTCOME_FEEDBACK"],"not_a_score":true,"not_a_diagnosis":true,"no_eligibility_effect":true,"withdrawable":true,"training_use":false}'::jsonb,
  now()
) ON CONFLICT (tool_ref, version_no) DO UPDATE SET
  title = EXCLUDED.title,
  purpose = EXCLUDED.purpose,
  status = EXCLUDED.status,
  admission_status = EXCLUDED.admission_status,
  evidence_level = EXCLUDED.evidence_level,
  schema_ref = EXCLUDED.schema_ref,
  item_schema = EXCLUDED.item_schema,
  boundary = EXCLUDED.boundary;
