# 来源映射与排版数据

每篇论文独立一个工作目录。运行 `prepare` 后的 JSON 是候选分块，**不是已验证的阅读顺序或已完成翻译**。按原页视觉修订。所有坐标为 PDF point，原页左上角为原点，页码从 1 开始。

```json
{
  "schema_version": 1,
  "source": "/absolute/source.pdf",
  "sha256": "prepare computes this; keep unchanged",
  "title": "中文论文标题",
  "pages": [{"number":1,"width":612,"height":792,"reviewed":true,"needs_ocr":false}],
  "blocks": [
    {"id":"S001","page":1,"bbox":[48,210,300,310],"type":"body","action":"translate","original":"Source paragraph.","translation":"原文对应段落的完整译文。"},
    {"id":"F001","page":1,"bbox":[48,320,300,440],"type":"figure","action":"preserve","reason":"User preserves all figure content"}
  ],
  "glossary": {"external quantum efficiency (EQE)":"外量子效率（EQE）"},
  "config": {},
  "notes": []
}
```

- 块 ID 全文唯一。数组顺序表示阅读顺序；不要再维护易冲突的独立 `order` 数字。跨栏/跨页续段可分为两个块，译文在相应位置衔接。
- `action` 仅为 `translate` 或 `preserve`，自动生成的 `unreviewed` 必须逐项处理。保留块必须有 `reason`。图、表、公式和参考文献类型不能标为 translate；图注用 caption，正文 body，另外可用 title、abstract、keywords、heading、footnote、publisher、authors。
- 所有提取字符中心必须被某块覆盖。段落块需涵盖首行字母、上下标等，禁止互相重叠，也不能侵入图表、公式、参考文献等保护框。
- `original` 保存该块的真实原文，不改写以迎合检查。数字保留计数如不同会阻止生成；核实是合理的月份数字化等转换时，才添加 `numeric_review` 字符串说明差异。不能用泛泛“已审核”掩盖漏译。
- 可选 `font_size`、`min_font_size` 覆盖单块字号。默认正文字号 9.65 pt，最小 9 pt；图注默认 8 pt，最小 7.5 pt。标题、脚注分别处理。字体须嵌入并覆盖所有字符。
- `align` 可为 left、center、right、justify；`color` 为 `#RRGGBB`，`leading` 可显式设置行距（point）。默认标题/章节居中、章节蓝色，其他左对齐近黑色，来自本次认可的 IEEE 样式；**新论文原样式不同就明确覆盖**，不能把该默认当成通用论文规范。`prepare` 的 `source_style` 提供字号及颜色候选；对齐方式仍需看原页。混色图注可统一为正文色，若用户要求精确保色需进一步按文字片段排版。
- 自动尝试 macOS 宋体/黑体、Linux 文泉驿/Droid、Windows 宋体。不可用时配置 `config.font` 为中文 TrueType 字体绝对路径，TTC 用 `config.font_index` 选择字面。不要把系统字体打包到 skill。
- 工具支持每页不同尺寸，禁止把 Letter/A4 或四页写死。`config.margin/gutter/top/bottom` 可选，均为非负整数 point，以便精确像素对齐。
- 标题框通常可覆盖原文的整行/两行栏宽并利用原有下方空白，例如原标题在 `[48,55,540,75]`，其后至 y=95 无正文、图或装饰线，可扩展到 `[48,55,540,95]` 容纳中文。先核查保护区域，不能仅为让脚本通过就盖住邻近内容。图形保护框须包含完整矢量图、标记、图例、色条及比例尺，不只框可提取文字。
- inline 特殊格式可扩展脚本，但不能改变科学含义。当前内置 O₂、MoOₓ、ηRad 的上下标排版；其他化学式/变量需按原文补充且验证，复杂数学保留原式，不作为普通中文文本重排。

`build` 的 `.layout.json` 记录实际字号、数值审核、被移除的错位链接。`audit` 的 `.audit.json` 记录每页结果，并以退出码 2 表示失败；它无法证明语义正确，也不会自动宣布人工目视检查通过。

像素策略：英文原页、图表/公式/参考文献保护区域要求零差异。中文侧替换框外允许最多全页 0.01% 的渲染差异，以容纳删除文字层时坐标重序列化造成的微小抗锯齿变化；同时要求全部保留块的可提取文字逐字一致。报告保留实际差异数，不能将容差通过写成“零差异”。新输入若不满足该条件，应检查差异图后修复，不能单纯放宽阈值。

排版源文件在所有文字清理完成后再统一导入输出；不要边向输出导入、边继续修改同一源 PDF 的对象表，否则 PyMuPDF 的 graft map 会失效。命名内链先解析为页码与坐标，再重建为直接跳转；原始命名目标坐标需由 PDF 底部原点转换到页面顶部原点。

`audit` 使用 Pillow，PyMuPDF 负责渲染，不依赖外部 Fontconfig。若另用 Poppler，配置系统字体目录及工作目录中的可写字体缓存，避免大量警告。
