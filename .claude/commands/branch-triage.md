---
description: 只读评估一批git分支相对main的真实合并价值（去重/识别已被main吸收的假分支/识别POC沙盒），给出结构化verdict
argument-hint: [branch-name-1] [branch-name-2] ...
---

对传入的每个分支 `origin/$1`（以及后续参数），只读调研其相对 `origin/main` 的真实内容，不切换分支、不修改任何文件：

1. `git merge-base origin/main origin/<branch>` 判断merge-base是否等于分支tip或main的祖先——用于识别"已被main吸收"的假分支
2. `git rev-list --count origin/<branch>..origin/main` 看落后多少commit；落后越多，diff里的大量删除越可能是main独立演进的假象，而不是该分支主动删除功能——**不要被巨大的删除行数吓到下错误判断，必须验证**
3. `git log origin/main..origin/<branch> --oneline` 看真实新增的提交
4. `git diff --name-only origin/main origin/<branch>` 过滤出真正的功能代码文件（排除 lock文件/node_modules/__pycache__）
5. 对2-4个最关键的功能文件跑 `git diff` 判断真实改动内容
6. 检查是否有对应新增/修改的测试文件
7. 检查该功能文件路径是否已存在于当前main（区分"新功能"vs"已被吸收"vs"被main另一套实现取代"）

按以下schema给出结构化verdict（每个分支一份）：
- `branch`: 分支名
- `summary`: 1-3句话说清楚这条分支真实实现了什么
- `files_changed_vs_main` / `real_feature_files`: 表面差异文件数 vs 真正承载功能的文件
- `has_tests`: 是否有对应测试
- `verdict`: `MERGE_WORTHY`（值得合并，可能需要rebase） / `SUPERSEDED_BY_ANOTHER_BRANCH`（被别的分支或main的独立实现取代） / `EXPERIMENTAL_ONLY`（POC沙盒，不接入生产） / `DUPLICATE_OF_ALREADY_MERGED`（内容已经在main历史里）
- `verdict_reason`: 给出可验证的证据链（merge-base结果、真实新增文件、测试覆盖情况），不要凭分支名或commit message的自我描述下结论

如果分支数量多（5个以上），用 Workflow 工具并行评估（每个分支一个agent），不要串行跑。评估完成后给出一份汇总表格：按verdict分组，标注哪些可以直接安全删除（DUPLICATE_OF_ALREADY_MERGED且逐字节确认commit已存在于main历史）、哪些需要真正的迁移工程（MERGE_WORTHY）、哪些需要产品决策（EXPERIMENTAL_ONLY是否要立项转正）。

**删除远程分支前，必须让用户逐字确认具体分支名**——不能因为评估给出DUPLICATE判断就自动执行删除，这是不可逆操作。
