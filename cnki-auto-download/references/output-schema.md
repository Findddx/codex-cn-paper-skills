# 输出文件与状态规范

批量任务至少生成三个文件：检索结果、下载队列、下载 manifest。问题清单可由 manifest 汇总生成。

## cnki_search_results.json

数组或对象均可，但每条结果应包含：

```json
{
  "query": "巴蜀 治水 传说",
  "title": "论文题名",
  "href": "https://kns.cnki.net/...",
  "authors": "作者1; 作者2",
  "source": "期刊或学位授予单位",
  "date": "2024-01-01",
  "citations": "12",
  "downloads": "203",
  "page": "1/10",
  "exportId": "可选"
}
```

## cnki_download_queue.json

候选去重后形成队列：

```json
[
  {
    "id": "cnki-0001",
    "title": "论文题名",
    "authors": "作者",
    "source": "来源",
    "date": "日期",
    "href": "详情页 URL",
    "query": "命中的检索词",
    "score": 42.5,
    "status": "pending",
    "note": ""
  }
]
```

## cnki_download_manifest.json

每次下载或跳过都记录一条：

```json
{
  "run_started_at": "2026-06-23T18:00:00+08:00",
  "pdf_only": true,
  "items": [
    {
      "title": "论文题名",
      "status": "downloaded_pdf",
      "source_file": "C:\\Users\\found\\Downloads\\论文题名.pdf",
      "output_file": "D:\\project\\papers\\论文题名_作者.pdf",
      "href": "https://kns.cnki.net/...",
      "message": ""
    }
  ]
}
```

## 状态码

| 状态 | 含义 | 后续动作 |
| --- | --- | --- |
| `pending` | 已入队，尚未处理 | 继续下载流程 |
| `download_triggered` | 页面已点击 PDF 下载，但文件尚未确认落盘 | 等待下载目录 |
| `downloaded_pdf` | PDF 已下载并移动到输出目录 | 完成 |
| `unmatched_pdf` | 新 PDF 已出现，但无法可靠匹配队列题名 | 人工核对 |
| `skipped_no_pdf` | 详情页无 PDF 链接，PDF-only 下跳过 | 可人工确认 |
| `skipped_caj_only` | 只有 CAJ，用户未允许 CAJ | 不下载 |
| `not_logged_in` | 浏览器未登录知网或学校认证失效 | 用户登录后重试 |
| `captcha_wait` | 出现滑块验证码 | 用户手动验证后继续 |
| `no_permission` | 学校未购买、无权下载或需付费 | 跳过或手动处理 |
| `download_timeout` | 点击后在限定时间内未发现 PDF | 单篇重试 |
| `page_timeout` | 检索页或详情页加载超时 | 单篇重试 |
| `error` | 未归类异常 | 记录消息并人工排查 |

## cnki_problem_downloads.md

问题清单按人工处理优先级输出：

```markdown
# CNKI 问题下载清单

## 需要登录或验证

- 论文题名｜作者｜状态：not_logged_in｜详情页 URL

## 学校未购买或无权限

- 论文题名｜作者｜状态：no_permission｜详情页 URL

## 无 PDF 或只有 CAJ

- 论文题名｜作者｜状态：skipped_no_pdf｜详情页 URL

## 下载超时或待核对

- 论文题名｜作者｜状态：download_timeout｜详情页 URL
```

问题清单不得写入账号、Cookie、下载令牌或浏览器个人信息。
