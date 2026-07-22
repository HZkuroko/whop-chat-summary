"""
Whop channel daily digest fetcher.

Fetches the last N hours of chat messages from one or more Whop channels
and exports them to a Markdown file. Paste that file into Notion (or anywhere)
and summarize it with an AI of your choice.

Usage:
    python pull_whop.py

Config lives in config.json (copy config.example.json).
Your browser Cookie lives in cookie.txt (never commit it).
"""
import json
import time
import datetime
import os
import sys

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run: pip install -r requirements.txt")

URL = "https://whop.com/api/graphql/chatFetchMessages/"

QUERY = """query chatFetchMessages($feedId: ID!, $feedType: FeedTypes!, $limit: Int, $before: BigInt, $direction: Direction, $includeDeleted: Boolean) {
  messages: feedPosts(feedId: $feedId, feedType: $feedType, limit: $limit, before: $before, direction: $direction, includeDeleted: $includeDeleted) {
    posts {
      id
      createdAt
      isPosterAdmin
      content
      markdownContent
      userId
      replyingToPost { content markdownContent user { username name } }
    }
    users { id username name }
  }
}"""

TZ = datetime.timezone(datetime.timedelta(hours=8))  # Beijing time for output


class CookieExpired(Exception):
    pass


def load_config():
    if not os.path.exists("config.json"):
        sys.exit("config.json not found. Copy config.example.json to config.json and fill it in.")
    with open("config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("channels"):
        sys.exit("config.json has no channels. Add at least one channel with a feed_id.")
    return cfg


def load_cookie():
    if not os.path.exists("cookie.txt"):
        sys.exit("cookie.txt not found. Create it and paste your whole browser Cookie string inside.")
    with open("cookie.txt", "r", encoding="utf-8") as f:
        cookie = f.read().strip()
    if not cookie:
        sys.exit("cookie.txt is empty. Paste your whole browser Cookie string inside.")
    return cookie


def build_headers(cookie, user_agent):
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://whop.com",
        "referer": "https://whop.com/",
        "user-agent": user_agent,
        "Cookie": cookie,
    }


def fetch_channel(feed_id, headers, hours_back):
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - hours_back * 60 * 60 * 1000
    posts, users, seen = [], {}, set()
    before = None

    while True:
        variables = {
            "feedId": feed_id,
            "feedType": "chat_feed",
            "limit": 100,
            "direction": "desc",
            "includeDeleted": False,
        }
        if before is not None:
            variables["before"] = str(before)

        resp = requests.post(
            URL, headers=headers,
            data=json.dumps({
                "query": QUERY,
                "variables": variables,
                "operationName": "chatFetchMessages",
            }),
            timeout=30,
        )

        if resp.status_code in (401, 403, 429):
            raise CookieExpired(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ! request failed HTTP {resp.status_code}: {resp.text[:200]}")
            break

        body = resp.json()
        if body.get("errors"):
            msg = body["errors"][0].get("message", "")
            if any(k in msg.lower() for k in ("auth", "permission", "unauthorized", "forbidden")):
                raise CookieExpired(msg)
            print(f"  ! API error: {msg}")
            break

        feed = body["data"]["messages"]
        for u in feed["users"]:
            users[u["id"]] = u.get("username") or u.get("name") or u["id"]

        page = feed["posts"]
        if not page:
            break

        reached_old = False
        for p in page:
            created = int(p.get("createdAt", 0))
            pid = p.get("id")
            if created < cutoff:
                reached_old = True
                continue
            if pid and pid not in seen:
                seen.add(pid)
                posts.append(p)

        before = min(int(p.get("createdAt", 0)) for p in page)
        if reached_old:
            break
        time.sleep(1)

    return posts, users


def format_channel(title, posts, users):
    posts.sort(key=lambda p: int(p.get("createdAt", 0)))
    lines = [f"## Channel: {title} ({len(posts)} messages)", ""]
    for p in posts:
        text = (p.get("markdownContent") or p.get("content") or "").strip().replace("\n", " ")
        if not text:
            continue
        t = datetime.datetime.fromtimestamp(int(p["createdAt"]) / 1000, TZ).strftime("%m-%d %H:%M")
        name = users.get(p.get("userId"), "unknown")
        tag = "[ADMIN] " if p.get("isPosterAdmin") else ""

        prefix = ""
        reply = p.get("replyingToPost")
        if reply:
            rtext = (reply.get("markdownContent") or reply.get("content") or "").strip().replace("\n", " ")
            if rtext:
                ruser = ""
                if reply.get("user"):
                    ruser = reply["user"].get("username") or reply["user"].get("name") or ""
                short = rtext[:40] + ("..." if len(rtext) > 40 else "")
                prefix = f"(reply to {ruser}: {short}) "

        lines.append(f"[{t}] {tag}{name}: {prefix}{text}")
    lines.append("")
    return "\n".join(lines)


def main():
    cfg = load_config()
    cookie = load_cookie()
    hours_back = cfg.get("hours_back", 24)
    user_agent = cfg.get("user_agent", "Mozilla/5.0")
    output_file = cfg.get("output_file", "whop_last24h.md")
    headers = build_headers(cookie, user_agent)

    now = datetime.datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    parts = [f"# Whop chat export - last {hours_back}h",
             f"> Fetched at (UTC+8): {now}", ""]
    total = 0

    try:
        for ch in cfg["channels"]:
            print(f"Fetching channel: {ch['name']} ...")
            posts, users = fetch_channel(ch["feed_id"], headers, hours_back)
            total += len(posts)
            parts.append(format_channel(ch["name"], posts, users))
            print(f"  ok: {len(posts)} messages")
            time.sleep(1)
    except CookieExpired as e:
        sys.exit(
            f"\nCookie expired or unauthorized ({e}).\n"
            "Log in to Whop again, open the chatFetchMessages request, copy a fresh "
            "Cookie, overwrite cookie.txt, then rerun."
        )

    md = "\n".join(parts)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\nDone. {total} messages saved to {output_file}")

    try:
        import pyperclip
        pyperclip.copy(md)
        print("Copied to clipboard. Paste it into Notion.")
    except Exception:
        print(f"Open {output_file}, select all, copy, and paste into Notion.")


if __name__ == "__main__":
    main()
