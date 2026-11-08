"""Export authorized Whop chats using one external config.txt.

This exporter does not call an AI or modify Notion. An optional user-provided
prompt is prepended verbatim to the Markdown, not executed by the program.
"""
import argparse
import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

try:
    import requests
except ImportError:
    requests = None

from whop_config import ConfigError, load_config, select_channels, validate_credentials

BASE_DIR = Path(__file__).resolve().parent
URL = "https://whop.com/api/graphql/chatFetchMessages/"
TZ = datetime.timezone(datetime.timedelta(hours=8))


class ExportError(Exception):
    pass


def ts_to_seconds(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            return 0.0
        if n >= 10 ** 18:
            n /= 10 ** 9
        elif n >= 10 ** 15:
            n /= 10 ** 6
        elif n >= 10 ** 12:
            n /= 10 ** 3
        return float(n)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return 0.0


def build_headers(settings):
    return {"accept": "*/*", "content-type": "application/json",
        "origin": "https://whop.com", "referer": "https://whop.com/",
        "user-agent": settings.user_agent, "Cookie": settings.cookie}


def fetch_channel(feed_id, headers, query, cutoff_sec, end_sec, delay=1, max_pages=1000):
    if requests is None:
        raise ExportError("缺少 requests，请运行 python -m pip install -r requirements.txt。")
    posts, users, seen, visited = [], {}, set(), set()
    before = None
    for _ in range(max_pages):
        variables = {"feedId": feed_id, "feedType": "chat_feed", "limit": 50,
            "direction": "desc", "includeDeleted": False}
        if before is not None:
            variables["before"] = str(before)
        try:
            resp = requests.post(URL, headers=headers, json={"query": query,
                "variables": variables, "operationName": "chatFetchMessages"},
                timeout=30, allow_redirects=False)
        except requests.exceptions.RequestException:
            raise ExportError("网络连接失败，请检查网络、代理设置及是否能访问 whop.com；未打印请求凭据。") from None
        if resp.status_code in (401, 403):
            raise ExportError("认证失效或没有频道权限（HTTP 401/403），请更新 config.txt 中的 Cookie 并确认访问权限。")
        if resp.status_code == 429:
            raise ExportError("请求过于频繁（HTTP 429），请稍后再试或增大 request_delay；这不一定是 Cookie 失效。")
        if resp.status_code != 200:
            raise ExportError("接口返回 HTTP %s；已停止导出，未打印响应内容。" % resp.status_code)
        try:
            body = resp.json()
        except (ValueError, TypeError):
            raise ExportError("接口没有返回有效 JSON，可能是登录页、验证页或接口变化。") from None
        if not isinstance(body, dict) or body.get("errors"):
            raise ExportError("GraphQL 返回错误，可能是权限、登录状态或接口结构变化；本次不保存不完整结果。")
        data = body.get("data")
        feed = data.get("messages") if isinstance(data, dict) else None
        if not isinstance(feed, dict) or not isinstance(feed.get("posts"), list):
            raise ExportError("接口返回结构与预期不符，本次不保存不完整结果。")
        for user in feed.get("users") or []:
            if isinstance(user, dict) and user.get("id"):
                users[user["id"]] = user.get("username") or user.get("name") or user["id"]
        page = feed["posts"]
        if not page:
            return posts, users
        reached_old = False
        for post in page:
            if not isinstance(post, dict):
                raise ExportError("消息结构异常，已停止导出。")
            created = ts_to_seconds(post.get("createdAt"))
            if created <= 0:
                raise ExportError("消息时间戳缺失或不正确，无法确认时间范围。")
            if created < cutoff_sec:
                reached_old = True
                continue
            pid = post.get("id")
            if pid and pid not in seen and created <= end_sec and not post.get("isDeleted"):
                seen.add(pid)
                posts.append(post)
        if reached_old:
            return posts, users
        candidates = [int(str(p["sortKey"])) for p in page
            if str(p.get("sortKey", "")).lstrip("-").isdigit()]
        if not candidates:
            candidates = [int(str(p["createdAt"])) for p in page
                if str(p.get("createdAt", "")).isdigit()]
        if not candidates:
            raise ExportError("没有可用翻页游标，已停止以避免循环。")
        cursor = min(candidates)
        if cursor in visited or (before is not None and cursor >= before):
            raise ExportError("分页游标没有前进，已停止以避免重复或无限请求。")
        visited.add(cursor)
        before = cursor
        time.sleep(delay)
    raise ExportError("达到 max_pages 上限，未将不完整抓取伪装成成功；请缩短时间范围或调整上限。")


def format_channel(title, posts, users):
    lines = ["## 频道：%s（共 %s 条）" % (title, len(posts)), ""]
    for post in sorted(posts, key=lambda p: ts_to_seconds(p.get("createdAt"))):
        text = str(post.get("markdownContent") or post.get("content") or "").strip().replace("\n", " ")
        stamp = datetime.datetime.fromtimestamp(ts_to_seconds(post["createdAt"]), TZ).strftime("%m-%d %H:%M")
        name = users.get(post.get("userId"), "未知用户")
        tag = "【管理员】" if post.get("isPosterAdmin") else ""
        prefix = ""
        reply = post.get("replyingToPost")
        if isinstance(reply, dict):
            rtext = str(reply.get("content") or "").strip().replace("\n", " ")
            ruser = reply.get("user") or {}
            rname = ruser.get("username") or ruser.get("name") or ""
            if rtext:
                prefix = "(↩ 回复 %s: %s) " % (rname, rtext[:40] + ("…" if len(rtext) > 40 else ""))
        if not text:
            count = len(post.get("attachments") or [])
            text = "[无文本消息%s]" % ("；%s个附件，未下载" % count if count else "")
        lines.append("[%s] %s%s: %s%s" % (stamp, tag, name, prefix, text))
    return "\n".join(lines + [""])


def build_markdown(settings, channels_data, now, include_prompt=True, hours=None):
    duration = settings.hours_back if hours is None else hours
    parts = ["# Whop 群聊原文 · 过去%g小时" % duration,
        "> 抓取时间（北京）：%s" % now.astimezone(TZ).strftime("%Y-%m-%d %H:%M"), ""]
    parts += [format_channel(ch.name, posts, users) for ch, posts, users in channels_data]
    text = "\n".join(parts)
    if include_prompt and settings.include_prompt and settings.prompt:
        text = settings.prompt + "\n\n---\n\n" + text
    return text


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                dir=str(path.parent), prefix=".whop-", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(text)
        os.replace(str(temp), str(path))
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def make_parser():
    parser = argparse.ArgumentParser(description="Whop 导出器：prompt、Cookie 和频道全部读取同一个 config.txt")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.txt")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--channel", action="append", help="频道名称、feed_id 或编号；可重复")
    selection.add_argument("--channels", nargs="+", help="一次指定一个或多个频道名称、feed_id 或编号")
    selection.add_argument("--all", action="store_true", help="导出配置内全部频道")
    selection.add_argument("--interactive", action="store_true", help="显示频道菜单，输入编号，支持 1,3 或 all")
    parser.add_argument("--list-channels", action="store_true", help="只列出频道，不联网")
    parser.add_argument("--check-config", action="store_true", help="只校验配置，不联网且不输出 Cookie/prompt")
    parser.add_argument("--hours", type=float, help="本次覆盖 hours_back")
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--no-clipboard", action="store_true")
    return parser


def main(argv=None):
    args = make_parser().parse_args(argv)
    try:
        settings = load_config(args.config)
        if args.list_channels or args.interactive:
            for index, ch in enumerate(settings.channels, 1):
                print("%s. %s [%s]" % (index, ch.name, ch.feed_id))
        if args.list_channels:
            return 0
        selectors = args.channel or args.channels
        if args.all:
            selectors = ["all"]
        elif args.interactive:
            if len(settings.channels) == 1:
                selectors = ["1"]
            else:
                try:
                    answer = input("选择编号（如 1 或 1,2；all=全部，回车=配置默认）：").strip()
                except EOFError:
                    raise ConfigError("无法读取交互输入，请使用 --channel / --channels / --all。") from None
                selectors = answer.replace("，", ",").replace(",", " ").split() if answer else None
        if not selectors:
            selectors = settings.selected_channels.replace("，", ",").replace(",", " ").split()
        channels = select_channels(settings.channels, selectors)
        validate_credentials(settings, channels)
        hours = settings.hours_back if args.hours is None else args.hours
        if not math.isfinite(hours) or hours <= 0:
            raise ConfigError("--hours 必须是正的有限数。")
        if args.check_config:
            print("配置有效：选中 %s 个频道；未联网，未输出 Cookie/prompt。" % len(channels))
            return 0
        query = (BASE_DIR / "whop_query.graphql").read_text(encoding="utf-8")
        now = datetime.datetime.now(datetime.timezone.utc)
        end = now.timestamp()
        cutoff = end - hours * 3600
        collected = []
        for ch in channels:
            print("抓取频道：%s ..." % ch.name)
            posts, users = fetch_channel(ch.feed_id, build_headers(settings), query, cutoff,
                end, settings.request_delay, settings.max_pages)
            collected.append((ch, posts, users))
            print("  已取得 %s 条" % len(posts))
        md = build_markdown(settings, collected, now, not args.no_prompt, hours)
        write_atomic(settings.output_file, md)
        print("完成：%s 个频道，%s 条，已保存到 %s" % (len(channels),
            sum(len(posts) for _, posts, _ in collected), settings.output_file))
        if settings.copy_clipboard and not args.no_clipboard:
            try:
                import pyperclip
                pyperclip.copy(md)
                print("已复制到剪贴板。")
            except Exception:
                print("剪贴板不可用，文件已保存，请手动复制。")
        return 0
    except (ConfigError, ExportError) as error:
        print("错误：%s" % error, file=sys.stderr)
        return 1
    except OSError:
        print("错误：无法读取查询文件或写入输出文件，请检查文件位置和权限。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
