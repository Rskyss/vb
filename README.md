# Vibe Workflow — 非开发者的 AI 开发管控层

给**不会写代码、靠 AI 开发产品**的人（产品经理、创业者、独立开发爱好者）用的一套工程纪律 skill。装上之后，你的 AI 编程助手会被四道硬关卡管住：

1. **没对齐不动工** —— 动工前把歧义列成选择题让你拍板，不再自作主张
2. **没全绿不报完** —— "做完了"必须有真实环境走通流程的证据，不是"测试通过"四个字
3. **没登记不算做完** —— 项目里自动维护一份你看得懂的《开发进度跟踪.md》，随时能查做到哪了
4. **版本纪律** —— 一个版本一个提交、发布说明用人话写、上线前必请示

每条规则都附带"为什么"——它们全部来自一个真实产品数月开发中踩过的坑（AI 谎报完成、进度失踪、版本历史变流水账……），并且经过压力测试验证：在"明早要演示、快一点"和"别问了你看着办"这类高压场景下，AI 仍然守得住。

## 适合谁

- ✅ 不写代码、靠 AI 全权开发的人：这套流程就是为你设计的
- ⚠️ 专业开发者：部分规则（如一版一提交 squash）是面向"用户靠版本感知进度"场景的取舍，可能与你的团队惯例冲突，按需取用

## 安装

skill 遵循 [Agent Skills 开放标准](https://agentskills.io)（SKILL.md 格式），主流 AI 编程工具均可使用。

**Claude Code**

```bash
git clone https://github.com/Rskyss/vb.git
cp -r vb/vibe-workflow ~/.claude/skills/
```

（只想在某个项目用：改放到项目的 `.claude/skills/` 目录）

**Codex CLI / Gemini CLI**

把 `vibe-workflow/` 文件夹放进对应工具的 skills 目录（Codex：`~/.codex/skills/`；Gemini CLI 参考其 [skills 文档](https://geminicli.com/docs/cli/skills/)）。

**Cursor 等暂不支持自动触发的工具**

把 `vibe-workflow/` 放进项目，在项目规则文件（如 `.cursor/rules` 或 AGENTS.md）里加一句：
> 开发工作必须遵守 vibe-workflow/SKILL.md 的工作规范，动工前先完整阅读它。

## 内容结构

```
vibe-workflow/
  SKILL.md                    # 主规范：四道关卡 + 借口对照表 + 红旗清单
  references/
    进度台账模板.md            # 《开发进度跟踪.md》的结构与登记格式
    验收记录模板.md            # 单个任务"凭什么算做完"的写法
    版本与推送规则.md          # 版本号、一版一提交、Release 文案规则
    自测清单.md                # "全绿"的逐项定义
```

## 一点提醒

skill 是规则文本，不是强制执行器——它能大幅提高 AI 的纪律性（经多模型压力测试验证），但不同工具、不同模型的遵守程度有差异。最可靠的用法：你自己记住四道关卡，发现 AI 说"做完了"却拿不出证据时，问一句"台账登记了吗？自测证据呢？"

## License

MIT
