-- UI-35 commercial 21-day parent-practice lifecycle.
-- The camp records caregiver actions only. It never produces a child score,
-- diagnosis, cross-family ranking or claimed growth outcome.

CREATE TABLE IF NOT EXISTS family_growth_camp_programs (
  program_ref varchar(96) NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  purpose varchar(280) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','HOLD','REJECTED')),
  evidence_level varchar(8) NOT NULL DEFAULT 'E1',
  boundary varchar(96) NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (program_ref, version_no),
  CONSTRAINT family_growth_camp_program_window CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE IF NOT EXISTS family_growth_camp_days (
  program_ref varchar(96) NOT NULL,
  program_version integer NOT NULL,
  day_no integer NOT NULL CHECK (day_no BETWEEN 1 AND 21),
  stage varchar(32) NOT NULL,
  title varchar(160) NOT NULL,
  intent varchar(280) NOT NULL,
  action_text varchar(600) NOT NULL,
  suggested_words varchar(400) NOT NULL,
  observation_prompt varchar(400) NOT NULL,
  estimated_minutes integer NOT NULL CHECK (estimated_minutes BETWEEN 1 AND 60),
  PRIMARY KEY (program_ref, program_version, day_no),
  FOREIGN KEY (program_ref, program_version) REFERENCES family_growth_camp_programs(program_ref, version_no)
);

CREATE TABLE IF NOT EXISTS family_growth_camp_enrollments (
  enrollment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  program_ref varchar(96) NOT NULL,
  program_version integer NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAUSED','COMPLETED','CANCELLED')),
  current_day integer NOT NULL DEFAULT 1 CHECK (current_day BETWEEN 1 AND 21),
  started_by_person_id uuid NOT NULL REFERENCES persons(person_id),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (program_ref, program_version) REFERENCES family_growth_camp_programs(program_ref, version_no)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_growth_camp_active_subject
  ON family_growth_camp_enrollments(family_id, subject_person_id, program_ref)
  WHERE status IN ('ACTIVE','PAUSED');
CREATE INDEX IF NOT EXISTS idx_family_growth_camp_scope
  ON family_growth_camp_enrollments(tenant_id, family_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS family_growth_camp_day_checkins (
  checkin_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  enrollment_id uuid NOT NULL REFERENCES family_growth_camp_enrollments(enrollment_id) ON DELETE CASCADE,
  day_no integer NOT NULL CHECK (day_no BETWEEN 1 AND 21),
  completion_status varchar(24) NOT NULL CHECK (completion_status IN ('COMPLETED','PARTIAL','NOT_COMPLETED')),
  reflection varchar(500) NULL,
  reflection_boundary varchar(72) NOT NULL DEFAULT 'PARENT_REFLECTION_NOT_CHILD_FACT_OR_OUTCOME',
  recorded_by_person_id uuid NOT NULL REFERENCES persons(person_id),
  occurred_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (enrollment_id, day_no)
);

CREATE TABLE IF NOT EXISTS family_growth_camp_operations (
  operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  enrollment_id uuid NULL REFERENCES family_growth_camp_enrollments(enrollment_id),
  action_name varchar(64) NOT NULL CHECK (action_name IN ('ENROLL_GROWTH_CAMP','CHECK_IN_GROWTH_CAMP_DAY')),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_body jsonb NOT NULL,
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, family_id, action_name, idempotency_key)
);

INSERT INTO family_growth_camp_programs(program_ref,version_no,title,purpose,status,admission_status,evidence_level,boundary)
VALUES ('PARENT_GROWTH_21',1,'21 天智慧父母成长营','通过示范、练习、回顾与正向反馈，支持家长把温和沟通带入日常。','ACTIVE','ADMITTED','E1','ACTION_RECORD_NOT_OUTCOME')
ON CONFLICT (program_ref,version_no) DO NOTHING;

INSERT INTO family_growth_camp_days(program_ref,program_version,day_no,stage,title,intent,action_text,suggested_words,observation_prompt,estimated_minutes) VALUES
('PARENT_GROWTH_21',1,1,'观察与连接','先听完一句话','练习在回应之前，先完整听见孩子。','找一个普通对话，只听完孩子的一句话，不打断也不急着给建议。','我先听你说完，你慢慢说。','孩子说完后，语气或身体状态有什么变化？',10),
('PARENT_GROWTH_21',1,2,'观察与连接','描述，不评价','把看到的事实和自己的判断分开。','选择一个日常场景，只说出你看到的行为，不加负面人格评价。','我看到书还放在桌上，我们一起看看接下来怎么安排。','当你减少评价时，对话是否更容易继续？',8),
('PARENT_GROWTH_21',1,3,'观察与连接','找到情绪背后的需要','先理解当下，再讨论办法。','冲突出现时，先猜一个可能的感受，并邀请孩子修正。','你现在是不是有点失望？如果我猜错了，你可以告诉我。','孩子是否愿意补充自己的感受？',10),
('PARENT_GROWTH_21',1,4,'观察与连接','留出十分钟专属时间','用稳定陪伴建立连接。','让孩子选择一个十分钟活动，你不看手机、不教学，只参与。','这十分钟你来选，我们一起做。','孩子选择了什么？你最意外的细节是什么？',10),
('PARENT_GROWTH_21',1,5,'观察与连接','看见一次努力','关注过程而不是只看结果。','找到孩子今天一次具体努力，描述你看到的过程。','我看到你刚才重新试了一次，这很不容易。','具体描述和泛泛表扬带来的回应有什么不同？',6),
('PARENT_GROWTH_21',1,6,'观察与连接','暂停一次自动反应','给家长和孩子都留出调节空间。','在想立刻批评时，先做三次缓慢呼吸，再决定是否回应。','我需要一分钟整理一下，我们等会儿再说。','暂停后，你真正想表达的重点是什么？',5),
('PARENT_GROWTH_21',1,7,'观察与连接','第一次家庭小回顾','总结做过的行动，不评价谁好谁坏。','回看前六天，选一个最想保留的小动作。','这周哪一次相处让我们都轻松一点？','家庭愿意保留的动作是什么？',15),
('PARENT_GROWTH_21',1,8,'沟通与习惯','把命令改成有限选择','在边界内给孩子参与感。','选择一个需要完成的小事，提供两个都可接受的选择。','你想先收书包，还是先整理桌面？','有限选择是否减少了拉扯？',8),
('PARENT_GROWTH_21',1,9,'沟通与习惯','说清边界与原因','坚定表达，不使用威胁。','针对一个家庭规则，用一句边界和一句原因表达。','九点后手机要放在客厅，因为睡眠是我们共同保护的事。','孩子最关心规则的哪一部分？',10),
('PARENT_GROWTH_21',1,10,'沟通与习惯','一起把目标变小','把模糊要求变成可以开始的动作。','和孩子把一个任务缩小为十分钟能完成的第一步。','我们不一次做完，先找出第一小步。','任务变小后，开始是否更容易？',10),
('PARENT_GROWTH_21',1,11,'沟通与习惯','用提问代替提醒','帮助孩子参与计划。','今天只用一个开放问题帮助孩子回想自己的安排。','你准备从哪一步开始？需要我帮什么？','孩子能否说出自己的下一步？',8),
('PARENT_GROWTH_21',1,12,'沟通与习惯','设计一个环境提示','少靠意志，多靠环境。','为一个家庭习惯增加可见提示，例如固定收纳点或纸质步骤卡。','我们把提醒放在哪里最顺手？','环境变化是否减少了口头催促？',12),
('PARENT_GROWTH_21',1,13,'沟通与习惯','失败后重新开始','练习恢复，而不是追求连续完美。','回看一次没有做到的计划，只讨论下一次如何更容易开始。','没做到也可以重新来，下一次我们想改哪一点？','当失败不被批评时，孩子是否更愿意讨论？',10),
('PARENT_GROWTH_21',1,14,'沟通与习惯','第二次家庭小回顾','识别适合自己家庭的沟通与习惯工具。','从第 8–13 天选择一个继续使用、一个暂时放下的工具。','哪个方法最像我们家？哪个暂时不适合？','家庭做出的选择和理由是什么？',15),
('PARENT_GROWTH_21',1,15,'反思与延续','区分事实和我的想法','减少把担心当成孩子事实。','写下一件发生的事，再分别写出事实和你的解释。','这是我现在的理解，不一定就是你的感受。','事实和解释分开后，你的情绪有什么变化？',10),
('PARENT_GROWTH_21',1,16,'反思与延续','看见自己的触发点','理解家长反应背后的担心。','回想一次强烈反应，写下当时你最担心发生什么。','我刚才有点着急，是因为我担心……','说出担心后，表达是否更清楚？',10),
('PARENT_GROWTH_21',1,17,'反思与延续','修复一次小冲突','让道歉和修复成为家庭能力。','选择一个小冲突，先为自己的表达方式负责，再邀请孩子补充。','刚才我的语气太重了，对不起。你的感受是什么？','修复后，双方是否更愿意继续对话？',10),
('PARENT_GROWTH_21',1,18,'反思与延续','共同定义一个好时刻','让家庭自己决定什么值得延续。','请每个人说一个最近觉得舒服的家庭时刻。','最近哪一刻让你觉得我们很像一个团队？','不同成员看重的时刻有什么不同？',12),
('PARENT_GROWTH_21',1,19,'反思与延续','选择一个长期微习惯','把课程收获变成低负担日常。','从此前练习中选择一个每周至少做一次的动作。','我们只保留一个最容易坚持的动作，好吗？','这个动作需要什么环境支持？',10),
('PARENT_GROWTH_21',1,20,'反思与延续','约定一次家庭小会','建立稳定、可恢复的家庭复盘节奏。','确定下周一次 15 分钟家庭小会的时间和议题。','下周我们用十五分钟聊聊最近最需要配合的一件事。','什么时间和形式最不容易成为负担？',8),
('PARENT_GROWTH_21',1,21,'反思与延续','完成过程回顾','看见做过的行动，并选择下一阶段。','回看完成和跳过的日子，写下一个发现、一个保留动作和一个仍需支持的问题。','这 21 天不是考试，我们只看看什么对我们家真正有用。','下一阶段更适合继续练习、进入 90 天计划，还是先暂停？',15)
ON CONFLICT (program_ref,program_version,day_no) DO NOTHING;
