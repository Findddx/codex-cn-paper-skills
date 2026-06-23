# Codex 中文论文写作与 Word 文档 Skills

这个仓库包含面向 Codex 的通用中文论文工作 skill：

- `chinese-academic-writing-cn`：中文论文起草、改写、润色、引用核查、subagent 多视角审阅和终稿验收。
- `word-academic-docx-cn`：中文论文 Word 文档处理，覆盖 `.doc/.docx`、引用编号、脚注/尾注、参考文献、题注、目录和格式验证。
- `cnki-auto-download`：通过可见浏览器和 Chrome DevTools MCP 执行授权范围内的知网论文检索、题名回查、详情页 PDF 下载、下载归档和问题清单输出。

## 设计重点

- 不依赖固定外部 API、MinerU 或双模型交叉润色流程。
- 在 Codex 环境中使用 subagents 或分轮审阅模拟不同表达和审查视角。
- 将证据映射、引用贴合、学术语体和 Word 格式验收分开处理。
- 对知网下载任务，默认只下载 PDF；需要登录、验证码、机构认证或无权限时由用户在浏览器中手动处理，skill 不绕过访问控制。
- 在最终润色验收中专门审查“不是……而是……”“并非……而是……”等句式，只有存在真实概念辨析、批判性分析或反驳功能时才保留。

## 安装

将需要的 skill 目录复制到 Codex skill 目录，例如 Windows PowerShell：

```powershell
$skills = "$HOME\.codex\skills"
Copy-Item -Recurse .\chinese-academic-writing-cn $skills\
Copy-Item -Recurse .\word-academic-docx-cn $skills\
Copy-Item -Recurse .\cnki-auto-download $skills\
```

也可以只复制其中一个目录。

## 使用建议

- 论文内容写作、改写、降 AI 感、终稿语言验收：使用 `chinese-academic-writing-cn`。
- Word 文件、脚注、尾注、引用编号、题注、目录和版式：使用 `word-academic-docx-cn`。
- 知网论文搜集和 PDF 下载：使用 `cnki-auto-download`。需要 Chrome/Edge 可见浏览器、Chrome DevTools MCP、已登录且有授权的知网账号或学校认证。
- 学位论文终稿通常应同时使用两者：先处理论证和语体，再处理 Word 格式和引用脚注。
