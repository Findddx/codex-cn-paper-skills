# 浏览器自动化工作流

本文档给 Codex 执行知网检索和 PDF 下载时使用。所有下载都必须发生在用户授权的可见浏览器会话中。

## 1. 页面准备

优先复用已经打开的知网页面：

1. 调用 `list_pages`，寻找 URL 包含 `cnki.net` 的标签页。
2. 如果存在，`select_page` 到该页。
3. 如果不存在，`new_page` 或 `navigate_page` 到 `https://kns.cnki.net/kns8s/search`。
4. 不主动关闭用户标签页。

如遇登录页、机构认证页、滑块验证码或支付确认页，停下让用户处理。

验证码判断：

```javascript
() => {
  const cap = document.querySelector('#tcaptcha_transform_dy');
  return !!(cap && cap.getBoundingClientRect().top >= 0);
}
```

只有 `top >= 0` 时才视为正在显示验证码。知网会预加载隐藏验证码 DOM，隐藏状态不能当作阻塞。

## 2. 关键词检索并抽取结果

打开 `https://kns.cnki.net/kns8s/search` 后，使用一次 `evaluate_script` 完成输入、点击、等待和抽取。把 `YOUR_QUERY` 替换为实际检索式。

```javascript
async () => {
  const query = "YOUR_QUERY";
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  await new Promise((resolve, reject) => {
    let n = 0;
    const check = () => {
      if (document.querySelector('input.search-input')) resolve();
      else if (++n > 40) reject(new Error('search_input_timeout'));
      else setTimeout(check, 500);
    };
    check();
  });

  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) {
    return { error: 'captcha' };
  }

  const input = document.querySelector('input.search-input');
  input.value = query;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('input.search-btn')?.click();

  await sleep(2500);
  await new Promise((resolve, reject) => {
    let n = 0;
    const check = () => {
      if (document.querySelector('.result-table-list tbody tr') || document.body.innerText.includes('条结果')) resolve();
      else if (++n > 60) reject(new Error('results_timeout'));
      else setTimeout(check, 500);
    };
    check();
  });

  const cap2 = document.querySelector('#tcaptcha_transform_dy');
  if (cap2 && cap2.getBoundingClientRect().top >= 0) {
    return { error: 'captcha' };
  }

  const rows = Array.from(document.querySelectorAll('.result-table-list tbody tr'));
  const checkboxes = Array.from(document.querySelectorAll('.result-table-list tbody input.cbItem'));
  const results = rows.map((row, i) => {
    const titleLink = row.querySelector('td.name a.fz14');
    const authors = Array.from(row.querySelectorAll('td.author a.KnowledgeNetLink')).map(a => a.innerText.trim()).filter(Boolean);
    return {
      n: i + 1,
      title: titleLink?.innerText?.trim() || '',
      href: titleLink?.href || '',
      exportId: checkboxes[i]?.value || '',
      authors: authors.join('; '),
      source: row.querySelector('td.source a')?.innerText?.trim() || '',
      date: row.querySelector('td.date')?.innerText?.trim() || '',
      citations: row.querySelector('td.quote')?.innerText?.trim() || '',
      downloads: row.querySelector('td.download')?.innerText?.trim() || ''
    };
  }).filter(x => x.title);

  return {
    query,
    total: document.querySelector('.pagerTitleCell')?.innerText?.match(/([\d,]+)/)?.[1] || '',
    page: document.querySelector('.countPageMark')?.innerText || '',
    results
  };
}
```

建议每个关键词检索完成后等待 2.5-6 秒，再进行下一次检索或翻页。

## 3. 题名精确回查

批量下载时，不直接使用结果页下载按钮。若详情页 URL 不可靠，按论文题名回查：

1. 进入检索页。
2. 把完整题名填入 `input.search-input`。
3. 点击搜索。
4. 在当前结果页中优先选择题名完全相同或规范化后完全相同的结果。
5. `navigate_page` 到该结果的 `href`。

规范化题名时去掉空白、书名号、引号、破折号、冒号和常见标点；不要把不同副标题误并为同一篇。

## 4. 详情页 PDF 下载

进入详情页后，使用一次 `evaluate_script` 检查状态并点击 PDF。`FORMAT` 固定为 `pdf`，除非用户明确允许 CAJ。

```javascript
async () => {
  const format = "pdf";
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  await new Promise((resolve, reject) => {
    let n = 0;
    const check = () => {
      if (document.querySelector('.brief h1')) resolve();
      else if (++n > 60) reject(new Error('detail_timeout'));
      else setTimeout(check, 500);
    };
    check();
  });

  await sleep(1500);

  const cap = document.querySelector('#tcaptcha_transform_dy');
  if (cap && cap.getBoundingClientRect().top >= 0) {
    return { error: 'captcha', message: 'CNKI 正在显示滑块验证码。请在 Chrome 中手动完成。' };
  }

  const title = document.querySelector('.brief h1')?.innerText?.trim()?.replace(/\s*网络首发\s*$/, '') || '';
  const pdfLink = document.querySelector('#pdfDown') || document.querySelector('.btn-dlpdf a');
  const cajLink = document.querySelector('#cajDown') || document.querySelector('.btn-dlcaj a');
  const notLogged = document.querySelector('.downloadlink.icon-notlogged') || document.querySelector('[class*="notlogged"]');
  const pageText = document.body.innerText || '';

  if (notLogged || /登录|请先登录/.test(pageText) && !pdfLink && !cajLink) {
    return { error: 'not_logged_in', title };
  }

  if (/未订购|没有权限|无权下载|余额不足|购买|充值|付费/.test(pageText) && !pdfLink) {
    return { error: 'no_permission', title };
  }

  if (format === 'pdf') {
    if (!pdfLink) {
      return { error: 'no_pdf', title, hasPDF: false, hasCAJ: !!cajLink };
    }
    pdfLink.click();
    return { status: 'downloading', format: 'PDF', title, hasPDF: true, hasCAJ: !!cajLink };
  }

  if (format === 'caj' && cajLink) {
    cajLink.click();
    return { status: 'downloading', format: 'CAJ', title, hasPDF: !!pdfLink, hasCAJ: true };
  }

  return { error: 'no_download', title, hasPDF: !!pdfLink, hasCAJ: !!cajLink };
}
```

点击后等待下载开始。若浏览器弹出下载确认、机构确认或验证码，等待用户手动处理。

## 5. 下载目录观察

下载触发前记录当前时间。触发后在浏览器默认下载目录中查找修改时间晚于任务开始时间的文件：

- 正在下载：`.crdownload`
- 成功 PDF：`.pdf`
- 误下 CAJ：`.caj`

只有当 `.crdownload` 消失、PDF 文件大小稳定后，才移动到目标目录并记录 `downloaded_pdf`。如果超时仍无 PDF，记录 `download_timeout`。

可使用辅助脚本：

```powershell
python .\cnki-auto-download\scripts\cnki_manifest_tools.py move-downloads `
  --download-dir "$HOME\Downloads" `
  --output-dir "D:\path\to\papers" `
  --queue ".\cnki_download_queue.json" `
  --manifest ".\cnki_download_manifest.json" `
  --since "2026-06-23T18:00:00" `
  --pdf-only
```

## 6. 推荐关键词拓展方式

学术检索不能只用用户给出的一个词。围绕主题扩展时可按以下维度组合：

- 研究对象：地域、时代、人物、神灵、庙宇、制度、文类。
- 核心概念：传说、神话、故事、信仰、祭祀、民俗、地方志、口头传统。
- 相关概念：水利、治水、防洪、江河、都江堰、堰工、水神、川主、二郎神、大禹、李冰。
- 学科入口：民间文学、民俗学、宗教学、人类学、历史地理、地方社会史、文化记忆。

每一轮检索后先入库去重，再决定是否下载。不要一边检索一边大量点击下载。

## 7. 常见状态处理

- `captcha`：停止，提示用户完成滑块验证。
- `not_logged_in`：停止，提示用户登录或完成学校认证。
- `no_permission`：记录跳过，不反复尝试。
- `no_pdf`：PDF-only 时记录跳过；只有用户允许 CAJ 才尝试 CAJ。
- `download_timeout`：记录问题清单，可稍后按题名单篇重试。
- `unmatched_pdf`：文件已下载但未能匹配到队列题名，需要人工核对。
