# 开源参考与取舍

检索日期：2026-10-23。检查了 skills.sh 目录与 GitHub 原始 SKILL.md/仓库说明。以下仅为设计参考，未复制第三方代码或安装其 skills；不将仓库自述或星数当成验证结果。未能可靠核实的安装量不填造。

| 项目 | 可参考之处 | 与本个人 skill 的区别 |
|---|---|---|
| [haoyiyin/pdf-translate](https://github.com/haoyiyin/pdf-translate/blob/main/SKILL.md)（MIT） | pdf2zh 工具封装，单语及对照 PDF 输出 | 默认 Google 翻译；图表文字和参考文献的选择性保护需另验；检索时 GitHub 0 星，未当成成熟推荐 |
| [lxsssssss/pdf-translate](https://github.com/lxsssssss/pdf-translate/blob/main/SKILL.md)（MIT） | 几何测量、翻译数据与布局分离、溢出检测和渲染后对比 | 更广泛的公文/招投标场景，本技能只保留科研论文相关做法；检索时 GitHub 93 星 |
| [AIKONG2024/paper-translate-agent-skill](https://github.com/AIKONG2024/paper-translate-agent-skill/blob/main/pdf-translate/SKILL.md)（MIT） | 当前聊天模型翻译、JSON 分批持久化、恢复与验证 | 默认纯译文，依赖专用布局引擎；检索时 GitHub 4 星，未直接安装 |
| [waiwaifeng/codex-skill-article-translator](https://github.com/waiwaifeng/codex-skill-article-translator/blob/main/SKILL.md) | 论文上下文、术语及图文来源映射 | 倾向重排的可读 HTML，不直接满足原版面左右逐页对照；未核实许可，不复制 |
| [BabelDOC](https://github.com/funstory-ai/BabelDOC)（AGPL-3.0，工具而非 skill） | 复杂论文的布局保留翻译引擎，可作为未来替代实现 | 需要另核配置、翻译服务和图表/参考文献保护规则；不作为本技能默认强依赖 |

另查看了 [Anthropic PDF skill](https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md) 的通用 PDF 操作流程；其文档技能许可是 source-available 自定义条款，不能把“公开可读”等同于 MIT 开源。

本技能脚本由本次已认可的排版工作流独立整理：保留原页向量内容、选择性清理文字层、独立译文覆盖、左右并排、保护区域像素检查和可解析链接重建。当前模型承担翻译判断，不额外转发文档到翻译服务。
