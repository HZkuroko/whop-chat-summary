"""Read personal settings from one UTF-8 INI-formatted .txt file.

No built-in summary prompt, channel IDs or account cookies.
"""
import configparser
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Channel:
    name: str
    feed_id: str


@dataclass(frozen=True)
class Settings:
    config_path: Path
    hours_back: float
    output_file: Path
    user_agent: str
    include_prompt: bool
    copy_clipboard: bool
    selected_channels: str
    request_delay: float
    max_pages: int
    cookie: str
    channels: List[Channel]
    prompt: str


def load_config(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ConfigError("找不到配置文件。请复制 config.example.txt 为 config.txt，并填写 Cookie 和频道。")
    # No interpolation or inline comments: %, #, ; and = remain literal values.
    parser = configparser.ConfigParser(interpolation=None, comment_prefixes=(),
        inline_comment_prefixes=None, strict=True, empty_lines_in_values=True)
    parser.optionxform = str
    try:
        parser.read_string(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, configparser.Error):
        # Parser exceptions can contain the raw Cookie line: never display them.
        raise ConfigError("配置文件读取失败。请使用 UTF-8，并检查区块、重复键和多行缩进；未输出配置内容。") from None
    if parser.defaults():
        raise ConfigError("不支持 [DEFAULT]，请把设置放在对应区块中。")
    expected = {"settings", "cookie", "channels", "prompt"}
    if set(parser.sections()) != expected:
        raise ConfigError("配置必须且只能包含 [settings]、[cookie]、[channels]、[prompt] 四个区块。")
    allowed = {"hours_back", "output_file", "user_agent", "include_prompt", "copy_clipboard",
        "selected_channels", "request_delay", "max_pages"}
    if set(parser["settings"]) - allowed or set(parser["cookie"]) != {"value"} or set(parser["prompt"]) != {"text"}:
        raise ConfigError("配置项不正确，请对照 config.example.txt 检查键名。")
    try:
        hours = parser.getfloat("settings", "hours_back", fallback=48)
        delay = parser.getfloat("settings", "request_delay", fallback=1)
        max_pages = parser.getint("settings", "max_pages", fallback=1000)
        include = parser.getboolean("settings", "include_prompt", fallback=True)
        clipboard = parser.getboolean("settings", "copy_clipboard", fallback=True)
    except ValueError:
        raise ConfigError("hours_back / request_delay / max_pages 或布尔设置格式不正确。") from None
    if not math.isfinite(hours) or hours <= 0 or not math.isfinite(delay) or delay < 0 or max_pages <= 0:
        raise ConfigError("hours_back、max_pages 必须为正数；request_delay 必须为非负有限数。")
    cookie = parser["cookie"]["value"].strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie.split(":", 1)[1].strip()
    if any(c in cookie for c in "\r\n"):
        raise ConfigError("Cookie 必须放在 value = 后同一行，不能换行。")
    user_agent = parser.get("settings", "user_agent", fallback="Mozilla/5.0").strip()
    if not user_agent or any(c in user_agent for c in "\r\n"):
        raise ConfigError("user_agent 不能为空或含换行。")
    channels = []
    ids = set()
    for name, feed_id in parser["channels"].items():
        name, feed_id = name.strip(), feed_id.strip()
        if not name or not re.fullmatch(r"chat_feed_[A-Za-z0-9_-]+", feed_id):
            raise ConfigError("频道格式不正确：每行填写 频道名称 = chat_feed_...，名称不要使用 = 或换行。")
        if feed_id in ids:
            raise ConfigError("同一个 feed_id 不能配置两次。")
        ids.add(feed_id)
        channels.append(Channel(name, feed_id))
    if not channels:
        raise ConfigError("[channels] 至少需要一个频道。")
    filename = parser.get("settings", "output_file", fallback="output/whop_chat.md").strip()
    if not filename:
        raise ConfigError("output_file 不能为空。")
    output = Path(filename).expanduser()
    if not output.is_absolute():
        output = path.parent / output
    output = output.resolve()
    if output.suffix.lower() != ".md" or output == path:
        raise ConfigError("output_file 必须是独立的 .md 文件，不能覆盖配置文件。")
    return Settings(path, hours, output, user_agent, include, clipboard,
        parser.get("settings", "selected_channels", fallback="all").strip(), delay,
        max_pages, cookie, channels, parser["prompt"]["text"].strip())


def select_channels(channels, selectors=None):
    if not selectors or selectors == ["all"]:
        return list(channels)
    if "all" in selectors:
        raise ConfigError("all 不能与其他频道同时选择。")
    chosen = []
    seen = set()
    for selector in selectors:
        # Prefer an exact name/ID over numeric index, so numeric channel names work.
        match = next((c for c in channels if selector in (c.name, c.feed_id)), None)
        if match is None and selector.isdigit() and 1 <= int(selector) <= len(channels):
            match = channels[int(selector) - 1]
        if match is None:
            raise ConfigError("未找到所选频道，请用 --list-channels 查看名称、编号或 feed_id。")
        if match.feed_id not in seen:
            seen.add(match.feed_id)
            chosen.append(match)
    return chosen


def validate_credentials(settings, selected):
    if not settings.cookie or settings.cookie in {"PASTE_COOKIE_HERE", "YOUR_COOKIE_HERE"}:
        raise ConfigError("请在 config.txt 的 [cookie] value = 后填写你自己的完整 Cookie。")
    if any("REPLACE" in ch.feed_id for ch in selected):
        raise ConfigError("请把所选频道的示例 feed_id 替换为真实值。")
