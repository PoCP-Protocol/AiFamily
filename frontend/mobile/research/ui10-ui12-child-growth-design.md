# UI-10 至 UI-12 儿童成长设计依据

**作者：Manus AI**

## 1. 设计结论

UI-10 至 UI-12 不应形成“儿童任务—积分—排行榜—成果海报”的竞争链路，而应形成“家庭已记录一次行动—孩子可以选择一个轻松练习或暂停—家庭回看自己的过程—生成一份家庭私有故事草稿”的共同成长链路。儿童表达属于孩子当下的 Perspective，不代表能力、性格或稳定事实；家庭行动属于过程记录，不等同教育效果；成长故事是家庭对经历的选择性叙述，不自动升级为 Fact 或 Outcome。[1] [2] [3]

| 页面 | 核心问题 | 移动端设计回答 |
|---|---|---|
| UI-10 孩子成长小助手 | 孩子能否参与下一步，又不被评价？ | 提供可选择、可替换、可暂停的轻量练习；不记录“是否听话”，不评分 |
| UI-11 我们的成长节奏 | 家庭怎样看见自己已经走过的步骤？ | 只回看同一家庭的选择、计划、行动和回顾，不产生排名、积分、百分位或连续天数 |
| UI-12 家庭成长故事卡 | 怎样温和地记住共同尝试？ | 用规则模板整理不超过四个过程片段，默认家庭私有，不保存媒体、不生成二维码、不外发 |

## 2. UI-10：自主支持，而不是儿童控制

儿童自主支持的研究将积极引导、低控制和及时回应视为重要线索；家庭日常节奏也需要在可预测与保留选择空间之间取得平衡。[1] [2] 因此，小助手只在家庭已记录一次行动后提供下一步，并允许孩子选择“想试试”“换一个”“今天暂停”。暂停不会扣分、打断连续天数或触发提醒。

孩子友好练习只允许使用低风险、日常、非诊断性内容，例如选择一个家庭活动、用一句话表达需要、共同设计一个小提醒、给家长一个“请先听我说完”的提示。页面不收集姓名、年龄、学校、照片、声音、位置，也不要求孩子描述敏感家庭冲突。

## 3. UI-11：家庭自己的节奏，而不是排行榜

家庭中心实践强调尊重家庭观点、优势与共同目标，并让家庭决定什么对自己重要。[3] 移动端将原“成长排行榜”替换为同一家庭的过程时间线。时间线只描述“选择了一个关注场景”“查看了 90 天方案”“记录了一次家庭行动”“完成了一次阶段回顾”等已发生事件。

UI-11 的数据模型禁止出现 `rank`、`score`、`percentile`、`peer`、`city`、`class`、`streak`、`badge`、`reward` 等比较字段。页面可以显示本周记录数量和当前阶段，但必须说明这只是参与过程，不代表家庭质量或孩子成长结果。

## 4. UI-12：家庭私有叙事，而不是成果证明

家庭故事能够帮助家庭成员把经历组织成共同理解，但叙事仍是对经验的选择和解释；学习故事实践也强调观察、反思、家庭观点和下一步支持，而不是验证儿童能力假设。[4] [5] 因此，UI-12 只从受控过程事件生成标题、过程摘要、不超过四个片段和下一步提示。

故事卡默认 `FAMILY_PRIVATE`，不包含儿童姓名、年龄、学校、照片、音视频、成长前后对比、连续打卡、成长值、勋章或二维码。第一阶段不提供下载、系统分享、公开发布、通知或收件人字段；唯一动作是回到家庭成长节奏，或修改故事标题与家庭内部备注。

## 5. 状态与数据边界

| 对象 | 允许字段 | 禁止推导 |
|---|---|---|
| ChildChoiceDraft | 练习 ID、孩子选择、可见性、记录时间、`perspective_not_fact` | 能力、服从、自律、情绪诊断 |
| FamilyRhythmEvent | 来源 UI、事件类型、时间、家庭私有摘要 | 排名、积分、效果、因果 |
| PrivateGrowthStory | 标题、过程摘要、最多四个来源事件、家庭备注、私有状态 | 成长前后、能力提升、成果证明 |
| Visibility | `FAMILY_PRIVATE` | 默认公开、自动分享、自动通知 |

## 6. 验收要求

测试必须证明：没有家庭行动时 UI-10 不伪造孩子提示；孩子暂停不产生失败记录；儿童表达始终为 Perspective；UI-11 状态和用户文案不包含排名、总分、百分位、积分、称号或奖励；UI-12 不包含儿童识别、媒体、下载、分享、发布或外发字段；三个页面只读取同一家庭的本机或 Family API 过程回执。

## References

[1]: https://pmc.ncbi.nlm.nih.gov/articles/PMC8264621/ "Parental autonomy support in relation to preschool aged children’s behavior"
[2]: https://www.healthychildren.org/English/family-life/family-dynamics/Pages/The-Importance-of-Family-Routines.aspx "American Academy of Pediatrics: The Importance of Family Routines"
[3]: https://headstart.gov/family-engagement/building-partnerships-guide-developing-relationships-families/getting-started-family-engagement-positive-goal-oriented "Head Start: Positive Goal-Oriented Relationships"
[4]: https://pmc.ncbi.nlm.nih.gov/articles/PMC3010736/ "Family Stories and Healing"
[5]: https://www.naeyc.org/resources/pubs/yc/summer2021/learning-stories "NAEYC: Learning Stories"
