# Whop Chat Exporter

Export recent messages from one or more Whop channels into one Markdown file.
**Prompt, Cookie and channel list now live together in one local `config.txt`.**
There is no built-in personal prompt, community name or real channel ID.

Runs locally on demand. It does not call an AI, send a prompt to an AI service. Paste the exported Markdown into your preferred AI yourself.

[中文使用说明](#中文使用说明)

## Requirements

- Python 3.9+ and `python -m pip install -r requirements.txt`
- Your own Whop account with authorized access to the selected channels
- A current browser Cookie; no paid AI API is needed

## Quick start

```bash
python -m pip install -r requirements.txt
```

Copy `config.example.txt` to **`config.txt`**, then edit only `config.txt`.
On Windows: `copy config.example.txt config.txt`.
On macOS/Linux: `cp config.example.txt config.txt`.
Optional Windows setup: `powershell -File setup.ps1` installs dependencies and
creates `config.txt` only when it does not already exist.

The file uses INI syntax, but is a normal UTF-8 `.txt`:

```ini
[settings]
hours_back = 48
output_file = output/whop_chat.md
user_agent = Mozilla/5.0
include_prompt = true
copy_clipboard = true
selected_channels = all
request_delay = 1
max_pages = 1000

[cookie]
value = PASTE_COOKIE_HERE

[channels]
Channel One = chat_feed_REPLACE_1
Channel Two = chat_feed_REPLACE_2

[prompt]
text =
```

- Replace the placeholder Cookie and channel IDs with your own. The checked-in example is intentionally not ready to authenticate.
- Keep one channel line for a single channel, or several lines for multiple channels. Channel names and IDs must be unique.
- `selected_channels = all` chooses every configured channel by default; `1` selects one, `1,2` selects several in the configured order. CLI choices override this setting.
- The prompt is **empty by default**. Put your own text after `text =`; indent **every continuation line** with four spaces. For example, writing `text = YOUR_OWN_PROMPT` uses a single-line prompt. Do not paste a prompt into the Python source.
- For a multiline prompt, start with `text =` on its own line, then indent each prompt line. Blank lines are allowed. Markdown headings such as `#` and literal `%`, `;`, `=` are preserved; do not add INI comments outside values.
- `include_prompt = false` or `--no-prompt` exports only the chat. An empty prompt is simply omitted.
- Keep the entire Cookie on one line after `value =`. No quotes are needed. A copied `Cookie:` prefix is accepted and removed. No separate `cookie.txt` is used.
- Output paths are relative to the directory containing the selected config file, not the shell's current directory.
- `user_agent` can be replaced with your actual browser User-Agent.

## Select channels

```bash
# Default: use selected_channels from config.txt
python pull_whop.py

# View configured channels without making a network request
python pull_whop.py --list-channels

# One channel: use a quoted name, feed_id, or 1-based list number
python pull_whop.py --channel "Channel One"
python pull_whop.py --channel 1

# Several channels; both forms work
python pull_whop.py --channels 1 2
python pull_whop.py --channel "Channel One" --channel "Channel Two"

# All channels, or interactive menu
python pull_whop.py --all
python pull_whop.py --interactive

# Other options
python pull_whop.py --config "D:/private/whop-config.txt" --channels 1 2
python pull_whop.py --hours 24 --no-prompt --no-clipboard
python pull_whop.py --check-config
```

On Windows, double-click **`run.bat`** to open the channel menu. Enter `1`,
`1,2`, or `all`. Press Enter to use the config default. With one configured
channel it is selected automatically. Command-line arguments also work:
`run.bat --channels 1 2`. `run.ps1` provides the same default interactive mode.
Launchers select an interpreter before running the exporter: an application
error will **not** trigger a second fetch under another interpreter.

The default output is `output/whop_chat.md`; successful runs replace that file.
If clipboard access is available it is copied automatically. Errors in any
selected channel stop the export without overwriting the previous output.

## Where to find the credentials

1. Log in to Whop and open a channel you are allowed to access.
2. Open browser DevTools → **Network** and scroll up in the chat.
3. Find the **`chatFetchMessages`** request.
4. In Payload, copy `feedId` into a line under `[channels]`. Repeat for each channel.
5. In Request Headers, copy the full Cookie into `[cookie] value =`.
6. Optionally copy the browser `user-agent` into `[settings]`.

Only the fixed `https://whop.com/api/graphql/chatFetchMessages/` endpoint receives
the Cookie. HTTP redirects are not followed. The program does not print the Cookie
or include it as metadata in the export; the Markdown does contain the prompt and
chat content you choose to export.

## Troubleshooting

- **401/403**: refresh the Cookie and verify that your account has channel access.
- **429**: rate limiting; wait and/or increase `request_delay`. This is not automatically a Cookie-expiry diagnosis.
- **GraphQL/response errors**: the unofficial endpoint may have changed; the program fails instead of silently saving an incomplete successful export.
- **Repeated pagination cursor / max_pages**: export stops instead of looping or claiming completeness.
- **Network failures**: check connectivity and any VPN/proxy configuration. The script does not bypass access controls.
- **Config parse error**: use UTF-8; ensure all four sections exist, keys are not duplicated and prompt continuation lines are indented. Parser details are intentionally not printed because they can contain a Cookie line.
- **Clipboard unavailable**: the Markdown file remains usable.

## Updating an existing checkout

This version replaces the old separate `config.json` + `cookie.txt` design and
the uploaded script's hard-coded prompt/channels. Old config files are **not read**.

1. Back up your local settings outside the repository.
2. Copy these release files into your checkout, replacing files with the same names.
3. Remove obsolete **example** files `config.example.json` and `cookie.txt.example` from the repository; they describe the previous setup. `setup.ps1` is replaced with the new single-TXT setup.
4. Create a local `config.txt` from `config.example.txt`. Move your Cookie, channels and any prompt you still want into it. Existing prompts are not migrated or shipped automatically.
5. Untrack private files if they were previously tracked; this does not delete the local copies:

```bash
git rm --cached --ignore-unmatch config.txt cookie.txt config.json
```

6. Review before committing:

```bash
git status --short --untracked-files=all
git diff --cached
```

Commit only source, tests, docs and the sanitized example. Adding `.gitignore`
does **not** remove secrets already present in earlier commits. Invalidate any
exposed session and clean repository history where necessary. Do not upload the
whole local working folder through the GitHub website: browser uploads do not
apply `.gitignore`. The supplied release ZIP deliberately excludes private configs.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use mocked HTTP responses and dummy credentials, not a real Whop login.
They cover config parsing, one/multiple channel selection, prompt inclusion,
Cookie redaction, paging, API errors and safe output handling. GitHub Actions is
included for Python 3.9 and 3.13 on Linux and Windows; those remote jobs run only
after the workflow is pushed. Local tests do not prove the live Whop endpoint is
currently compatible. Attachment-only messages are represented by placeholders;
attachment binaries are not downloaded.

## Security and responsible use

See [SECURITY.md](SECURITY.md). **Never commit `config.txt`, other personal `.txt`
configs, cookies, private prompts/channel lists, or chat exports.** `.gitignore`
ignores `.txt` files except the sanitized example and requirements, plus generated
Markdown except the public documentation. Avoid `git add -f` for personal files.

Use only your own legitimate session and channels. Respect Whop's terms and the
content owners' rights. This unofficial endpoint may change. Do not redistribute
private chat content without permission.

## License

MIT; original repository license retained in `LICENSE`.

---

## 中文使用说明

### 本次修改

- 删除原脚本内置的整段私人总结 prompt、频道名称和真实频道 ID。
- **prompt、Cookie、channels 列表全部放进同一个 `config.txt`**；代码里不用再改。
- 支持单频道、多频道、全部频道；Windows 双击 `run.bat` 可输入编号选择。
- 自定义 prompt 默认空白；不填就是纯原文，填写后才会加在导出文件最上方。
- 只导出 Markdown，不自动调用 AI

### 最简单的使用方法

1. 安装 Python 3.9 及以上版本。
2. 在项目目录运行 `python -m pip install -r requirements.txt`。
3. 复制 `config.example.txt` 为 `config.txt`，用支持 UTF-8 的编辑器打开。
4. 在 `[cookie]` 的 `value =` 后同一行粘贴完整 Cookie；不用引号，也不再使用独立 cookie.txt。
5. 在 `[channels]` 下填写 `频道名称 = chat_feed_真实ID`。只需要一个频道就只留一行，多频道就留多行。
6. 在 `[prompt]` 的 `text =` 后填写自己的 prompt；多行内容每行缩进四个空格。留空即可，不会自动填回原来的 prompt。
7. 双击 `run.bat`：输入 `1` 选单个，输入 `1,2` 选多个，输入 `all` 选全部；回车使用配置默认值。
8. 导出在 `output/whop_chat.md`。复制给任意 AI 使用；程序本身不会执行 prompt。

命令行也能用：

```bash
python pull_whop.py --channel 1
python pull_whop.py --channels 1 2
python pull_whop.py --all
python pull_whop.py --check-config
```

`selected_channels = all` 表示默认全部，改成 `1` 或 `1,2` 可固定默认选择。
`--check-config` 仅做本地检查，不联网，也不打印 Cookie/prompt。
`hours_back` 控制过去多少小时；`--hours 24` 只覆盖本次。

### 更新到已有 GitHub 仓库

把发布包内同名文件覆盖进仓库；新增的 `whop_config.py` 和
`whop_query.graphql` 必须与 `pull_whop.py` 一起提交，不能只替换一个脚本。
删除已弃用的 `config.example.json`、`cookie.txt.example`；保留新版
`config.example.txt`。真实 `config.txt` 只放本地，**不要上传**。

`.gitignore` 只影响未跟踪的文件，不能自动撤回已经提交过的 Cookie，
也不会替 GitHub 网页上传过滤文件。若曾泄露 Cookie，请先使会话失效，
必要时清理 Git 历史。本次发布包不含个人配置、聊天记录或原私人 prompt。

### 限制

Whop 接口非官方，可能变化；测试使用模拟请求，没有使用真实 Cookie 联网验证。
聊天附件只保留“无文本/附件”占位，不下载附件。401/403 检查登录和权限；
429 是限流，请等候后再试，不要误判为一定要换 Cookie。
