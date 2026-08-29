# UI-01 至 UI-34 移动端完成度复核台账

更新时间：2026-08  
范围：移动端 App UI-01 至 UI-34。UI-35 是额外 21 天智慧父母成长营基线，不计入本轮 34 张截图完成数。

## 复核结论

当前不能宣称“34 个移动端 UI 的功能点都已实现”。已有页面、测试和基线资产说明工程已经覆盖大部分路由与安全边界，但逐截图布局、视觉、功能、后端契约和文档口径仍不是同一完成度。

最容易误判的点是：`app/ui/UI-*.tsx` 返回 34 个文件，但其中包含 `UI-02-result.tsx`，同时不存在独立的 `app/ui/UI-01.tsx`。UI-01 由 `app/(tabs)/index.tsx` 承担，因此不能用“34 个 UI 文件”替代“UI-01 至 UI-34 全部完成”。

## 当前证据

| 项目 | 当前事实 | 判断 |
| --- | --- | --- |
| UI 页面文件 | `app/ui/UI-02.tsx` 至 `UI-34.tsx` 加 `UI-02-result.tsx`，共 34 个匹配；`UI-01` 在 `app/(tabs)/index.tsx` | 文件数不能作为完成口径 |
| UI-01 测试 | `tests/ui01-home-entry-map.test.ts` 绑定首页热点到 UI-02/UI-03/UI-04/UI-09/UI-12/UI-13/UI-19 | UI-01 是首页入口，不是独立页面 |
| 基线图片 | `research/baselines` 下有 UI-01 至 UI-34 及 UI-35 原图/分组图，共 70 张 | 原图资料存在，但仍需逐页视觉比对 |
| 测试文件 | 28 个 UI 相关测试，覆盖核心、商业、服务、社区、资产等分组 | 测试覆盖不等于截图一致 |
| 前后端矩阵 | 多页仍为 `GATE_BOUNDARY` 或 `UI_READY_BACKEND_GAP` | 不能把静态 UI 当成业务完成 |

## 必需交付口径

1. UI-01 至 UI-34 每页必须有明确的截图基线、当前实现入口、测试契约、后端/对象投影状态和风险边界。
2. UI-35 只能作为 21 天成长营附加基线接入，不能抵扣 UI-01 至 UI-34 中任何页面。
3. 原图中的诊断、排名、同龄比较、成长成果、积分权益、真实支付、真人服务和社区外发必须按治理边界安全改写。
4. 页面完成必须同时看布局/视觉、功能点、状态来源、路由出口、测试和文档；不能只看文件存在。

## 场景驱动交付方法（2026-08-24）

后续 UI-01 至 UI-34 按场景逐页推进，不再用“页面已存在”作为完成依据。每一页先写清业务场景、用户意图、前置状态、主要动作、退出路径、后端/对象投影、治理边界和验收证据，再进入补代码、补测试、补运行态验证。

每页必须按四层架构拆解后再实现：BA 先定义用户场景、角色、业务前后置、动作与退出路径；DA 定义对象、DTO/投影、状态来源、事实/观点/假设边界和 schema 权限；AA 定义页面、组件、路由、API client、本地状态和自动化测试；TA 定义 Family API、Named Action、Model Gateway、幂等、Audit/Outbox、Human Gate、AI/真人服务边界。没有完成四层拆解的页面，不进入“功能完成”口径。

| 步骤 | 交付物 | 验收方式 |
| --- | --- | --- |
| 场景研究 | 内部规格、基线截图、现有实现、外部理论/实践资料的摘要 | 明确该 UI 是家庭自查、计划、服务、商业、社区还是资产回看场景 |
| BA/DA/AA/TA 拆解 | 业务架构、数据架构、应用架构、IT 与 AI 架构四层边界 | 能说明页面每个可见状态来自哪里、能做什么、不能做什么 |
| 功能点拆解 | 每页功能点清单：入口、展示、选择/填写、保存/提交、跳转、异常态 | 功能点能映射到可见控件、Named Action 或只读投影 |
| 工程实现 | 页面、状态、API/fixture、对象边界、文案与治理口径 | 不突破 DB schema 授权，不绕过 Model Gateway/Human Gate/Consent |
| 自动化测试 | 页面契约、路由热点、边界禁词、Named Action/投影回执 | Vitest 或更窄测试通过，能防止回退 |
| 运行态验证 | 浏览器快照、截图、关键交互记录、阻塞说明 | 记录可见结构、可点击状态、工具限制或真实缺陷 |
| 文档闭环 | 更新本台账、对齐记录、前后端矩阵或评审项 | 文档不高于代码实况，未完成项明确 pending |

当前执行顺序从 UI-01 开始；UI-02 作为第一个按“研究支撑 + 测试契约 + 运行态快照”补齐的免费家庭测评样板页。每完成一页后再进入下一页，除非发现跨页路由或对象契约必须同时验证。

## 反向审计原则（2026-08-24）

用户已明确：如果 UI 基线已经设计，不直接修改既有页面布局、标题或核心文案。后续发现基线文案与治理边界存在张力时，先登记为“基线评审项”，不擅自改代码；只有基线缺失、实现与基线不一致、功能未实现、文档与代码不一致，或获得明确批准时，才进入代码修改。

因此本轮反向审计采用三类处理方式：

| 类型 | 处理方式 | 示例 |
| --- | --- | --- |
| 基线已设计但有治理张力 | 不改代码，登记评审项 | `成长成果`、`立即购买`、`专家顾问答疑`、`积分兑换` 等原图/商业语义 |
| 实现偏离基线 | 可修实现，但需保持原图结构 | UI-01 六宫格位置、UI-26 类型布局、UI-02 下拉选择 |
| 后端/对象/状态缺口 | 补 DTO、投影、Named Action、测试，不替换基线视觉 | `UI_READY_BACKEND_GAP`、`GATE_BOUNDARY` 页面 |

## 反向审计缺陷池

| 缺陷类别 | 涉及页面 | 当前问题 | 修改提升方式 |
| --- | --- | --- | --- |
| 视觉验收缺口 | UI-01 至 UI-34 | `visual-regression/ui01-ui35-portrait-baseline.md` 仍记录 UI-01 至 UI-35 截图“待采集”，上一轮采集未生成图片 | 不改页面；先恢复单页/小批次 375x812 截图采集，建立当前实现与原图并列证据 |
| 完成度口径缺口 | 全部 | `app/ui/UI-*.tsx` 文件数包含 `UI-02-result.tsx` 且 UI-01 在 tab 首页，不能证明 34 页完成 | 保持本台账为交付口径；每页补齐“入口、基线、测试、后端状态、风险边界” |
| UI 基线与治理张力 | UI-14、UI-17、UI-18、UI-29、UI-30、UI-32 | 原图/基线中存在购买、拼团、积分、会员、成果等强商业或结果表达 | 不直接改基线；在页面测试中继续守住 no payment/no ranking/no external effect；必要时提交产品评审 |
| 后端一致性缺口 | UI-04、UI-05、UI-06、UI-13、UI-14、UI-22、UI-27、UI-31、UI-33 | 矩阵标为 `UI_READY_BACKEND_GAP`，页面存在但正式 DTO、投影或对象状态未完全接入 | 优先补只读 DTO/状态投影；涉及写入时必须走 Named Action、幂等、Audit/Outbox |
| 高风险 Gate 缺口 | UI-07、UI-10、UI-11、UI-12、UI-17、UI-19、UI-20、UI-25、UI-28、UI-29、UI-30 | 矩阵标为 `GATE_BOUNDARY`，不能被普通业务接口直接实现 | 保持只读、草稿、意向或家庭私有过程；禁止真实支付、外发、儿童诊断、跨家庭比较 |
| 文档状态滞后 | `ui01-ui35-projection-state-audit.tsv` 等 | 早期投影审计可能仍记录 UI-01 无 remote call，与当前首页实现不一致 | 以代码实况修文档，不把文档写得高于实际完成度 |
| 测试覆盖缺口 | 多页 | 当前多为静态源码契约和局部交互测试，未形成 34 页统一截图/可访问性/状态流回归 | 增加分组测试：视觉截图、路由热点、边界禁词、对象投影、Named Action 回执 |

## 下一轮批次拆分

| 批次 | 范围 | 复核重点 | 不做事项 |
| --- | --- | --- | --- |
| A | UI-01 至 UI-06 | 首页、免费测评、支持方向、计划、打卡与积分入口是否形成可解释闭环 | 不把 UI-03 重新做成 AI 诊断；不新增 DB schema |
| B | UI-13 至 UI-18 | 商城、产品详情、邀请、同行计划、积分、会员是否只产生受控意向或只读投影 | 不接支付、外部分享、真实权益发放、真实通知 |
| C | UI-19 至 UI-24 | 专家/活动服务是否保留原图结构，同时区分真人服务状态与 AI 建议 | 不占用真人时段、不发消息、不伪称预约成功或服务完成 |
| D | UI-25 至 UI-28 | 社区内容是否保持家庭私有草稿/只读经验摘要，不形成公开社区能力 | 不发布公开内容、不生成点赞评论计数、不读取联系人或位置 |
| E | UI-29 至 UI-34 | 成果、年度陪伴、服务、订单资产、家庭档案、服务记录是否只表达过程和资产回看 | 不做效果承诺、家庭排名、儿童诊断、下载导出或外联客服 |

每个批次完成前必须补齐四件事：源代码入口、测试契约、后端/投影边界、视觉截图证据。若发现原始 UI 基线本身存在高风险表达，记录为评审项，不直接改页面。

## 首批已处理缺口

| 页面 | 原缺口 | 已修复 | 验证 |
| --- | --- | --- | --- |
| UI-02-result | 结果页文案把免费测评强绑定到 `AI诊断` | 改为“查看家庭支持方向”，保留家庭确认边界 | `ui02-assessment-baseline.test.ts` 通过 |
| UI-03 | 页面标题、空态、图例和主按钮仍呈现 `AI成长诊断`、`同龄平均`、`生成个性化方案` | 改为“家庭成长解读 / 家庭支持方向概览 / 参考方向 / 查看可选支持方案” | `ui03-growth-explanation-baseline.test.ts` 通过 |
| UI-04 | 直达方案页时把未确认或缺失 plan 展示成 `进行中`、已有任务和累计时长 | 改为无 plan/草稿 plan 时显示“待确认 / 0 / 0h”，四周均为“未开始”，并补强 priority、create、confirm、idempotency、receipt、UI-05 出口门槛 | `ui04-plan-baseline.test.ts` 6/6 通过；浏览器快照已复核，点击验证受 RN Web Pressable 工具限制 |
| UI-05 | 无服务投影时默认展示 `7/9`、`78%`、跨家庭比较和公开互动计数，容易把示例当成事实 | 改为无远端服务投影时 `0/9`、`0%`，过程文案为家庭私有记录；去除“超过伙伴”和效果断言，互动计数改为“家庭私有记录 / 用于复盘” | `ui05-companion-baseline.test.ts` 6/6、`ui05-ui09-real-session-harness.test.ts` 3/3 通过；浏览器快照已复核 |
| 设计文档 | `design.md` 将 35 页混成主交付口径 | 改为“34 个截图基线页面与 UI-35 附加基线” | 待文档诊断复核 |

## 逐页复核矩阵

| UI | 当前实现入口 | 测试证据 | 当前状态判断 | 下一步 |
| --- | --- | --- | --- | --- |
| UI-01 | `app/(tabs)/index.tsx` | `ui01-home-entry-map.test.ts` 5/5 通过，已覆盖顶部、测评 Banner、六宫格、任务区、推荐区和主要入口动作 | 原图核心功能结构已恢复；严格视觉截图仍未完成验收，21 天挑战营当前先到 UI-14 商品详情；本轮浏览器导航 `/` 超时且提示 Metro 连接断开，不能作为视觉证据 | 恢复 Expo/Metro 后采集 375×812 运行截图，对照横幅、六宫格、任务清单、推荐卡和底部导航 |
| UI-02 | `app/ui/UI-02.tsx` | `ui02-assessment-baseline.test.ts` 9/9 通过；`ui02-five-theme-family-assessment-research.md`；浏览器快照已见五主题、三道深追题、补充信息、边界确认和禁用的下一步 | 免费家庭测评主流程已接版本化测评和边界；五主题已有理论支持、实践支持、观察信号、非诊断边界和后续支持方向；运行态可见结构与测试契约一致 | 年龄下拉与单选控件在浏览器自动点击工具中持续等待稳定，暂不能作为缺陷定性；后续用人工点击或更低层 RN Web harness 复核交互，若需改“手机依赖”基线标题为“手机与边界”，先走基线评审 |
| UI-03 | `app/ui/UI-03.tsx` | `ui03-growth-explanation-baseline.test.ts` 6/6 通过；浏览器空态快照显示“先完成一次家庭测评”和非诊断/非评分/非排名说明 | 已消除诊断/同龄比较可见语义，保留原图“摘要 → 方向概览 → 关注点 → 建议 → 行动”结构；无测评数据时不编造个人资料或报告 | 需要带已提交测评 fixture 的运行态复核雷达图、摘要卡和“查看可选支持方案”按钮布局 |
| UI-04 | `app/ui/UI-04.tsx` | `ui04-plan-baseline.test.ts` 6/6 通过；浏览器运行态已复核；`ui04-original-screen-alignment.md` 已补齐 | 已修正未确认计划被显示为 `进行中` 的问题；无 plan/草稿 plan 显示“待确认 / 0 / 0h”，四周均为“未开始”；源码契约已覆盖无 onboarding 回 UI-02、priority 读取、create/confirm plan、幂等键、UI-04 receipt 和 UI-05 出口 | 用 UI-03 已确认关注方向 fixture 或更低层 RN Web harness 继续复核真实点击后的创建/确认计划链路；普通浏览器工具点击 Pressable 未触发，不作为缺陷定性 |
| UI-05 | `app/ui/UI-05.tsx` | `ui05-companion-baseline.test.ts` 6/6、`ui05-ui09-real-session-harness.test.ts` 3/3 通过；浏览器快照显示无远端服务投影时为 `0/9`、`0%`、家庭私有记录 | 已按 BA/DA/AA/TA 收紧为 90 天家庭私有陪跑过程页；服务卡保留原图结构，进度来自 service journey 投影，阶段回顾走 `reviewJourneyPhase` 幂等 API，打卡出口仅到 UI-09；不展示跨家庭比较、效果断言或公开互动计数 | 继续用真实已确认 plan/service journey fixture 复核 reviewDue 阶段回顾面板和 UI09 打卡链路 |
| UI-06 | `app/ui/UI-06.tsx` | `ui06-membership-baseline.test.ts` | 会员/积分/权益存在商业边界风险 | 核对不得显示真实开通、扣款或已生效权益 |
| UI-07 | `app/ui/UI-07.tsx` | `ui07-assessment-entry-baseline.test.ts` | 测评入口存在 | 核对同意说明、预计用时和历史测评状态 |
| UI-08 | `app/ui/UI-08.tsx` | `ui08-growth-report-baseline.test.ts` | 已改为家庭过程回顾，禁止评分/诊断/效果结论 | 浏览器核对五方向视觉与 UI-04 出口 |
| UI-09 | `app/ui/UI-09.tsx` | `ui09-daily-task-baseline.test.ts` | 已移除合成完成率和连续打卡 | 核对窄屏任务卡、完成/暂停/取消反馈 |
| UI-10 | `app/ui/UI-10.tsx` | `ui10-child-assistant-baseline.test.ts` | 儿童相关页已保留监护边界 | 核对不诱导儿童直接诊断/作答 |
| UI-11 | `app/ui/UI-11.tsx` | `ui11-family-rhythm-baseline.test.ts` | 榜单已安全替代为家庭自有节奏 | 核对是否仍有积分/排名式视觉误导 |
| UI-12 | `app/ui/UI-12.tsx` | `ui12-private-story-baseline.test.ts` | 海报已转为私有故事卡 | 核对分享入口是否保持草稿/私有边界 |
| UI-13 | `app/ui/UI-13.tsx` | `ui13-mall-baseline.test.ts` | 商城目录存在，后端 catalog 仍需严核 | 核对价格、权益和推荐来源 |
| UI-14 | `app/ui/UI-14.tsx` | `ui14-product-detail-baseline.test.ts` | 商品详情存在，需确认价格/拼团为沙箱或意向 | 避免真实购买/真实支付表达 |
| UI-15 | `app/ui/UI-15.tsx` | `ui15-invite-baseline.test.ts` | 邀请草稿与 no external effect 已有边界 | 核对不外发、不自动邀请 |
| UI-16 | `app/ui/UI-16.tsx` | `ui16-group-buy-baseline.test.ts` | 同行/拼团意向存在 | 核对不扣款、不真实成团 |
| UI-17 | `app/ui/UI-17.tsx` | `ui17-ui18-commerce-baseline.test.ts` | 积分商城为高风险边界页 | 核对积分不排名、不兑换、不发放权益 |
| UI-18 | `app/ui/UI-18.tsx` | `ui17-ui18-commerce-baseline.test.ts` | 会员中心只读/沙箱口径需复核 | 核对会员权益、积分和续费意向 |
| UI-19 | `app/ui/UI-19.tsx` | `ui19-teacher-zone-baseline.test.ts` | 名师专区涉及真人服务准入 | 核对 provider fixture/资格字段和无真实联系 |
| UI-20 | `app/ui/UI-20.tsx` | `ui20-teacher-detail-baseline.test.ts` | 名师详情需保持服务边界 | 核对资质、适用场景和非诊断说明 |
| UI-21 | `app/ui/UI-21.tsx` | `ui21-consultation-baseline.test.ts` | 预约需求草稿 E2E 方向较完整 | 核对“保存意向”不等于真人已预约成功 |
| UI-22 | `app/ui/UI-22.tsx` | `ui22-ui24-service-baseline.test.ts` | 沙龙列表后端 catalog 仍需复核 | 核对报名意向/日程草稿边界 |
| UI-23 | `app/ui/UI-23.tsx` | `ui21-ui23-submit-feedback.test.ts` | 活动意向链路存在 | 核对报名不收费、不真实占座 |
| UI-24 | `app/ui/UI-24.tsx` | `ui22-ui24-service-baseline.test.ts` | 我的服务记录只读边界存在 | 核对不声明服务效果或孩子变化 |
| UI-25 | `app/ui/UI-25.tsx` | `ui25-ui28-community-baseline.test.ts` | 家长社区只读经验边界存在 | 核对内容流不是跨家庭事实/推荐结论 |
| UI-26 | `app/ui/UI-26.tsx` | `ui25-ui28-community-baseline.test.ts` | 私有小记草稿和 2x2 类型布局已修 | 继续视觉比对媒体/可见范围 |
| UI-27 | `app/ui/UI-27.tsx` | `ui25-ui28-community-baseline.test.ts` | 小记详情边界存在 | 核对评论/互动不变成公开社区事实 |
| UI-28 | `app/ui/UI-28.tsx` | `ui25-ui28-community-baseline.test.ts` | 我的社区强调私有/草稿 | 核对粉丝、积分、公开状态均未出现 |
| UI-29 | `app/ui/UI-29.tsx` | `ui29-ui34-assets-baseline.test.ts` | 标题仍有“成长成果”，但边界已转过程记录 | 评审是否改标题为“成长过程回顾” |
| UI-30 | `app/ui/UI-30.tsx` | `ui29-ui34-assets-baseline.test.ts` | 年度会员/支付高风险页 | 核对开通、续费、支付只表达意向/另行确认 |
| UI-31 | `app/ui/UI-31.tsx` | `ui29-ui34-assets-baseline.test.ts` | 我的服务统一状态存在 | 核对 21 天/90 天/专家/活动来源一致 |
| UI-32 | `app/ui/UI-32.tsx` | `ui29-ui34-assets-baseline.test.ts` | 订单与资产只读/沙箱 | 核对订单、资产、权益不伪造真实交易 |
| UI-33 | `app/ui/UI-33.tsx` | `ui29-ui34-assets-baseline.test.ts` | 家庭档案对象投影需继续接入 | 核对 consent/visibility/成员资料边界 |
| UI-34 | `app/ui/UI-34.tsx` | `ui29-ui34-assets-baseline.test.ts` | 服务记录只读 | 核对不声称真人服务已发生或有效果 |

## 下一轮优先级

1. UI-01：按原图六宫格、21 天挑战营位置、今日任务与推荐内容做视觉/功能比对。
2. UI-04：核对 UI-03 进入后的方案页是否仍存在自动生成、确定性行动或报告事实化表达。
3. UI-06/UI-17/UI-18/UI-30/UI-32：集中复核积分、会员、权益、支付和订单的沙箱边界。
4. UI-19/UI-20/UI-21/UI-24/UI-34：集中复核真人服务、预约、服务发生和效果边界。
5. UI-29：决定是否把可见标题从“成长成果”改为“成长过程回顾”。
