"""
Whop channel daily digest fetcher.

Fetches the last N hours of chat messages from one or more Whop channels
and exports them to a Markdown file. Paste that file into Notion (or any AI)
and summarize it however you like.

Usage:
    python pull_whop.py

Config lives in config.json (copy config.example.json).
Your browser Cookie lives in cookie.txt (never commit it).
If Whop needs a VPN in your region, turn on a global/system VPN before running.
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

# Full query captured from Whop's own web app. Do NOT trim it: the server
# rejects simplified queries with a generic "(3301)" error.
QUERY = """query chatFetchMessages($feedId: ID!, $feedType: FeedTypes!, $limit: Int, $before: BigInt, $after: BigInt, $direction: Direction, $pinned: Boolean, $includeReactions: Boolean, $includeDeleted: Boolean) {
  messages: feedPosts(
    feedId: $feedId
    feedType: $feedType
    limit: $limit
    before: $before
    after: $after
    direction: $direction
    pinned: $pinned
    includeReactions: $includeReactions
    includeDeleted: $includeDeleted
  ) {
    posts {
      ...DmsPostFragment
    }
    users {
      ...BasicUserProfileDetails
    }
    reactions {
      ...ReactionFragment
    }
  }
}
fragment Attachment on AttachmentInterface {
  __typename
  id
  signedId
  analyzed
  byteSizeV2
  filename
  contentType
  source(variant: original) {
    url
  }
  ... on ImageAttachment {
    height
    width
    blurhash
    aspectRatio
  }
  ... on VideoAttachment {
    height
    width
    duration
    aspectRatio
    preview(variant: original) {
      url
    }
  }
  ... on AudioAttachment {
    duration
    waveformUrl
  }
}
fragment BasicUserProfileDetails on PublicProfileUser {
  id
  name
  createdAt
  profilePicture {
    sourceUrl
  }
  username
  roles
  lastSeenAt
  blockedAt
  isPlatformPolice
  companyUserProfile {
    id
    company {
      id
    }
    name
    profilePicture {
      sourceUrl
    }
  }
}
fragment DmsPostFragment on DmsPost {
  __typename
  id
  createdAt
  updatedAt
  isDeleted
  sortKey
  isPosterAdmin
  mentionedUserIds
  content
  richContent
  markdownContent
  feedId
  feedType
  attachments {
    ...Attachment
  }
  gifs {
    height
    provider
    originalUrl
    previewUrl
    slug
    title
    width
  }
  isEdited
  isEveryoneMentioned
  isPinned
  linkEmbeds {
    description
    favicon
    image
    processing
    title
    url
    footer {
      title
      description
      icon
    }
  }
  userId
  viewCount
  reactionCounts {
    reactionType
    userCount
    value
  }
  messageType
  embed
  replyingToPostId
  replyingToPost {
    id
    content
    gifs {
      __typename
    }
    isDeleted
    messageType
    attachments {
      contentType
    }
    user {
      id
      name
      username
      roles
      profilePicture {
        sourceUrl
      }
    }
  }
  poll {
    options {
      id
      text
    }
  }
  customAuthor {
    displayName
    profilePicture {
      sourceUrl
    }
  }
}
fragment ReactionFragment on Reaction {
  id
  isDeleted
  createdAt
  updatedAt
  feedId
  feedType
  postId
  postType
  userId
  reactionType
  score
  value
}"""

TZ = datetime.timezone(datetime.timedelta(hours=8))  # Beijing time for output


def ts_to_seconds(v):
    """Normalize a Whop timestamp (seconds / ms / us / ns) to seconds."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return 0
    if n >= 10 ** 18:       # nanoseconds
        return n / 1_000_000_000
    if n >= 10 ** 15:       # microseconds
        return n / 1_000_000
    if n >= 10 ** 12:       # milliseconds
        return n / 1000
    return n                # seconds


class CookieExpired(Exception):
    pass


class NetworkBlocked(Exception):
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
    cutoff_sec = time.time() - hours_back * 60 * 60
    posts, users, seen = [], {}, set()
    before = None

    while True:
        variables = {
            "feedId": feed_id,
            "feedType": "chat_feed",
            "limit": 50,
            "direction": "desc",
            "includeDeleted": False,
        }
        if before is not None:
            variables["before"] = str(before)

        try:
            resp = requests.post(
                URL, headers=headers,
                data=json.dumps({
                    "query": QUERY,
                    "variables": variables,
                    "operationName": "chatFetchMessages",
                }),
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkBlocked(str(e))

        if resp.status_code in (401, 403, 429):
            raise CookieExpired(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  ! request failed HTTP {resp.status_code}: {resp.text[:300]}")
            break

        body = resp.json()
        errs = body.get("errors")
        data = body.get("data") or {}
        feed = data.get("messages")

        if feed is None:
            if errs:
                msg = str(errs[0].get("message", ""))
                if any(k in msg.lower() for k in ("auth", "permission", "unauthorized", "forbidden", "login")):
                    raise CookieExpired(msg)
                print("  ! API returned an error. Full payload below:")
                print(json.dumps(errs, ensure_ascii=False, indent=2)[:2000])
            else:
                print("  ! no data returned:", json.dumps(body, ensure_ascii=False)[:500])
            break

        for u in (feed.get("users") or []):
            users[u["id"]] = u.get("username") or u.get("name") or u["id"]

        page = feed.get("posts") or []
        if not page:
            break

        reached_old = False
        for p in page:
            created_sec = ts_to_seconds(p.get("createdAt", 0))
            pid = p.get("id")
            if created_sec < cutoff_sec:
                reached_old = True
                continue
            if pid and pid not in seen:
                seen.add(pid)
                posts.append(p)

        # Pagination cursor: prefer sortKey (matches the web app), fall back to createdAt.
        cursors = [int(p["sortKey"]) for p in page
                   if str(p.get("sortKey", "")).lstrip("-").isdigit()]
        if cursors:
            before = min(cursors)
        else:
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
        t = datetime.datetime.fromtimestamp(ts_to_seconds(p["createdAt"]), TZ).strftime("%m-%d %H:%M")
        name = users.get(p.get("userId"), "unknown")
        tag = "[ADMIN] " if p.get("isPosterAdmin") else ""

        prefix = ""
        reply = p.get("replyingToPost")
        if reply:
            rtext = (reply.get("content") or "").strip().replace("\n", " ")
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
            "Log in to Whop again, copy a fresh Cookie, overwrite cookie.txt, then rerun."
        )
    except NetworkBlocked as e:
        sys.exit(
            "\nCould not reach whop.com (network problem).\n"
            f"   Details: {str(e)[:200]}\n\n"
            "If Whop is blocked in your region, turn on a global/system VPN and rerun."
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
