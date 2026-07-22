# Whop Chat Exporter

Export the last N hours of chat messages from one or more [Whop](https://whop.com) channels into a single Markdown file, then summarize it with any AI (Notion AI, ChatGPT, etc.).

Runs locally, on demand. No server, no scheduler, no paid API required — it only uses your own logged-in browser session.

[中文说明在下方](#中文说明)

---

## How it works

```
run script  ->  whop_last24h.md (raw chat from all channels)  ->  paste into your AI to summarize
```

The script calls the same GraphQL endpoint the Whop web app uses (`chatFetchMessages`), authenticated with the cookies from your own browser session.

## Requirements

- Python 3.9+
- A Whop account with access to the channels you want to export

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create your config**
   ```bash
   cp config.example.json config.json
   ```
   Then edit `config.json`:
   - `hours_back`: how far back to fetch (e.g. `24`)
   - `user_agent`: your browser's User-Agent string (see below)
   - `channels`: one entry per channel, each with a `name` and a `feed_id`

3. **Create your cookie file**
   ```bash
   cp cookie.txt.example cookie.txt
   ```
   Then replace its contents with your real Cookie string (see below).

## Where to get `feed_id`, `user_agent`, and the Cookie

1. Log in to whop.com in your browser and open the channel.
2. Press **F12** to open DevTools, go to the **Network** tab.
3. Scroll up in the chat so it loads older messages; a request named **`chatFetchMessages`** appears. Click it.
4. **`feed_id`** — in the **Payload** tab, copy the `feedId` value (looks like `chat_feed_...`). Repeat per channel.
5. **`user_agent`** — in **Headers > Request Headers**, copy the `user-agent` value.
6. **Cookie** — in **Headers > Request Headers**, copy the entire `Cookie` value and paste it into `cookie.txt` (no `Cookie:` label, no quotes).

## Run

```bash
python pull_whop.py
```

This writes `whop_last24h.md`. If `pyperclip` is installed, the content is also copied to your clipboard automatically.

## Summarize

Paste the exported Markdown into your AI of choice with a prompt like:

> Below is the raw chat from a finance community over the last 24 hours. Summarize what was discussed and extract key points (tickers, price levels, options). Split into "Summary" and "Details". Note disagreements. Keep it concise.

## Security notes

- **Never commit `cookie.txt` or `config.json`.** They are already in `.gitignore`.
- Your cookie is like a temporary password for your account. If it ever leaks, log out of Whop to invalidate it.
- Cookies expire (often within hours). If you get `HTTP 401/403/429` or a "Cookie expired" message, grab a fresh Cookie and overwrite `cookie.txt`.

## Disclaimer

This tool is for personal use to read content you already have legitimate access to. It relies on an unofficial, undocumented endpoint that may change at any time. Respect Whop's Terms of Service and the content owners' rights. Do not redistribute others' content without permission.

## License

MIT — see [LICENSE](LICENSE).

---

<a name="中文说明"></a>

## 中文说明

把一个或多个 Whop 频道过去 N 小时的聊天导出成一份 Markdown 文件,再用任意 AI(Notion AI、ChatGPT 等)总结。本地手动运行,无需服务器、无需付费 API,只用你自己浏览器的登录态。

### 使用步骤

1. 装依赖:`pip install -r requirements.txt`
2. 复制配置:`cp config.example.json config.json`,填入 `hours_back`、`user_agent`、各频道的 `name` 与 `feed_id`。
3. 复制并填写 Cookie:`cp cookie.txt.example cookie.txt`,把浏览器的整段 Cookie 粘进 `cookie.txt`(不要带 `Cookie:` 前缀、不要加引号)。
4. 运行:`python pull_whop.py`,生成 `whop_last24h.md`。
5. 把内容粘进 Notion 用 Notion AI 总结。

### 如何拿 feed_id / user-agent / Cookie

登录 whop.com 进入频道 → F12 → Network → 往上滚动加载消息 → 找到 `chatFetchMessages` 请求:
- **feed_id**:Payload 里的 `feedId`(每个频道一个)。
- **user-agent** 和 **Cookie**:Headers > Request Headers 里各自复制。

### 安全提醒

- **绝不要提交 `cookie.txt` 和 `config.json`**(已在 `.gitignore` 里排除)。
- Cookie 等于账号临时密码,一旦汄露就去 Whop 退出登录使其失效。
- Cookie 会过期(常常几小时);报 `HTTP 401/403/429` 就重新复制一份新的覆盖 `cookie.txt`。

### 免责声明

仅供个人阅读自己已有权限访问的内容。依赖的是非官方接口,可能随时失效。请遵守 Whop 服务条款及内容版权,未经允许不要转发他人内容。
