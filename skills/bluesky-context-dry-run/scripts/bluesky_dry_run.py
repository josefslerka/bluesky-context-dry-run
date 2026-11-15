#!/usr/bin/env python3
"""Read-only data collection and measured local drafts for a model-agent workflow. Stdlib only."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
import json
import math
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse as urlparse
import urllib.request
import discussion_profile
import workflow_record

API = "https://public.api.bsky.app"
POST = "app.bsky.feed.post"
PREFIX = "[BotyLab · AI] "
ROUTES = {"app.bsky.actor.getProfile", "app.bsky.feed.getAuthorFeed",
          "app.bsky.feed.getPosts", "app.bsky.feed.getPostThread", "app.bsky.feed.searchPosts"}
DEFAULTS = {"days": 14, "seconds": 900, "candidates": 30, "selected": 5,
            "feed_pages": 12, "http_requests": 40, "context_threads": 10, "context_posts": 24}


class RunError(Exception):
    pass


class ReadError(RunError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"Public GET failed: {status} {code}")


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso(value=None):
    return (value or now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def date(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise RunError("Timestamp must include a timezone.")
    return result.astimezone(dt.timezone.utc)


def require(condition, message):
    if not condition:
        raise RunError(message)


def web_url(value):
    require(isinstance(value, str), "URL must be a string.")
    try:
        p = urlparse.urlsplit(value)
        valid = p.scheme in ("http", "https") and p.hostname and not p.username and not p.password
        require(valid and not re.search(r"[\x00-\x20]", value), "Expected an HTTP(S) URL without credentials.")
    except ValueError:
        raise RunError("Invalid URL.") from None
    return value


def canonical(value):
    p = urlparse.urlsplit(value)
    query = [(k, v) for k, v in urlparse.parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid", "mc_cid", "mc_eid")]
    return urlparse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"),
                               urlparse.urlencode(query), ""))


def at_uri(value):
    if isinstance(value, str) and re.fullmatch(r"at://[^/\s]+/app\.bsky\.feed\.post/[A-Za-z0-9._~-]+", value):
        return value
    p = urlparse.urlsplit(web_url(value))
    match = re.fullmatch(r"/profile/([^/]+)/post/([A-Za-z0-9._~-]+)/?", p.path)
    require(p.hostname == "bsky.app" and match is not None, "Expected a Bluesky post URL or at:// post URI.")
    return f"at://{match[1]}/{POST}/{match[2]}"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def identifier(prefix, value):
    return prefix + hashlib.sha256(value.encode()).hexdigest()[:12]


def start(source_url, output_root, limits=None, *, topic=None, parent_run=None, revision_reason=None, executor='codex'):
    require(bool(source_url) != bool(topic), "Supply either a source URL or a topic.")
    if source_url:
        web_url(source_url)
    else:
        require(isinstance(topic, str) and 3 <= len(topic.strip()) <= 1000, "Topic needs 3–1000 characters.")
        topic = topic.strip()
    limits = {**DEFAULTS, **(limits or {})}
    require(all(type(v) is int and v > 0 for v in limits.values()), "Limits must be positive integers.")
    require(limits["selected"] <= 5 and limits["candidates"] <= 30, "At most 5 drafts and 30 candidates.")
    try:
        revision = workflow_record.revision(parent_run, revision_reason)
        executor = workflow_record.executor_label(executor)
    except ValueError as exc:
        raise RunError(str(exc)) from None
    started = now()
    path = Path(output_root).resolve() / (started.strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3))
    path.mkdir(parents=True, exist_ok=False)
    write(path / "run.json", {"version": 3, "discussion_profiles_required": True,
          "discussion_profile_criterion": discussion_profile.THEMATIC_FIT, "status": "running",
          "mode": "codex-dry-run" if executor == 'codex' else 'agent-dry-run', "model_executor": executor,
          "source_url": source_url, "topic": topic, "started_at": iso(started), "limits": limits,
          "revision_of": revision,
          "language_scope": "international unless the user specifies otherwise",
          "publication_enabled": False, "public_writes": 0})
    with locked(path) as run:
        run.event("started", source_url=source_url, topic=topic)
        if topic:
            write(path / "source.json", {"url": None, "attachment_url": None,
                "title": topic, "language": "und", "text_kind": "topic_brief",
                "paragraphs": [], "captured_at": iso(),
                "caveats": ["Téma je zadání, nikoli ověřený faktický zdroj. Doklady pocházejí z načtených příspěvků."],
                "text_sha256": hashlib.sha256(topic.encode()).hexdigest()})
    return path


@contextlib.contextmanager
def locked(path):
    path = Path(path).resolve()
    require((path / "run.json").is_file(), "Run directory does not exist.")
    with (path / ".lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield Run(path)


class Run:
    def __init__(self, path):
        self.path = Path(path)
        self.meta = read(self.path / "run.json")

    def active(self):
        require(self.meta["status"] == "running", "Completed runs are immutable; start a new run.")

    def events(self):
        f = self.path / "events.jsonl"
        return [json.loads(line) for line in f.read_text().splitlines() if line.strip()] if f.exists() else []

    def event(self, kind, **data):
        event = {"id": "E-" + secrets.token_hex(5), "at": iso(), "kind": kind, **data}
        with (self.path / "events.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def remaining(self):
        return self.meta["limits"]["seconds"] - (now() - date(self.meta["started_at"])).total_seconds()

    def network_allowed(self):
        self.active()
        require(self.remaining() > 0, "Time budget reached; finalize the available data.")
        count = sum(e["kind"] == "public_get" for e in self.events())
        require(count < self.meta["limits"]["http_requests"], "GET request budget reached.")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReadError(code, "RedirectRefused")


class PublicReader:
    """Only whitelisted GET endpoints, no tokens, sessions, cookies or write routes."""
    def __init__(self, run, opener=None):
        self.run = run
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def get(self, endpoint, **params):
        require(endpoint in ROUTES, "Endpoint is not in the read-only allowlist.")
        self.run.network_allowed()
        url = API + "/xrpc/" + endpoint + "?" + urlparse.urlencode(params, doseq=True)
        req = urllib.request.Request(url, method="GET", headers={
            "Accept": "application/json", "User-Agent": "BotyLab-dry-run/1.0"})
        started = iso()
        clock = time.monotonic()
        status, error, result = 0, None, None
        try:
            with self.opener.open(req, timeout=max(.1, min(20, self.run.remaining()))) as response:
                status = response.status
                body = response.read(2_000_001)
                require(len(body) <= 2_000_000, "Public response exceeded 2 MB.")
                result = json.loads(body)
                require(isinstance(result, dict), "Public response must be an object.")
        except urllib.error.HTTPError as exc:
            status, error = exc.code, "HTTPError"
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            error = "NetworkError"
        except (ValueError, UnicodeError):
            error = "InvalidJSON"
        except ReadError as exc:
            status, error = exc.status, exc.code
        except RunError:
            error = "InvalidResponse"
        elapsed = round(time.monotonic() - clock, 4)
        snap = "snapshots/" + identifier("R-", started + endpoint + secrets.token_hex(3)) + ".json"
        envelope = {"observed_at": iso(), "started_at": started, "method": "GET", "endpoint": endpoint,
                    "params": params, "status": status, "elapsed_seconds": elapsed,
                    "error": error, "public_writes": 0, "result": result}
        write(self.run.path / snap, envelope)
        self.run.event("public_get", endpoint=endpoint, method="GET", status=status, error=error,
                       elapsed_seconds=elapsed, snapshot=snap)
        if error:
            raise ReadError(status, error)
        return result


def capture_source(run, data):
    run.active()
    require(not (run.path / "source.json").exists(), "Source is already frozen.")
    for k in ("url", "title", "language", "text_kind"):
        require(isinstance(data.get(k), str) and data[k].strip(), f"Source requires {k}.")
    web_url(data["url"])
    require(data["text_kind"] in ("full_text", "excerpt", "post_only", "unavailable"), "Invalid source text_kind.")
    paragraphs = data.get("paragraphs")
    if paragraphs is None:
        require(isinstance(data.get("text"), str), "Source needs text or paragraph strings.")
        paragraphs = re.split(r"\n\s*\n", data["text"])
    require(isinstance(paragraphs, list) and all(isinstance(x, str) for x in paragraphs), "Invalid paragraphs.")
    paragraphs = [x.strip() for x in paragraphs if x.strip()]
    require((paragraphs or data['text_kind'] == 'unavailable') and len("\n\n".join(paragraphs)) <= 60000, "Supply 1–60000 source characters; label excerpts honestly.")
    caveats = data.get("caveats", [])
    require(isinstance(caveats, list) and all(isinstance(x, str) for x in caveats), "Invalid source caveats.")
    require(data['text_kind'] != 'unavailable' or caveats, "Unavailable sources need an explanation.")
    source = {**data, "attachment_url": run.meta["source_url"], "captured_at": iso(), "caveats": caveats,
              "paragraphs": [{"id": f"S{i:03d}", "text": text} for i, text in enumerate(paragraphs, 1)]}
    source.pop("text", None)
    source["text_sha256"] = hashlib.sha256("\n\n".join(paragraphs).encode()).hexdigest()
    write(run.path / "source.json", source)
    run.event("source_frozen", text_kind=source["text_kind"], characters=sum(map(len, paragraphs)),
              paragraphs=len(paragraphs))
    return source


def post_links(post):
    links = []
    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k == "uri" and isinstance(v, str):
                    links.append(v)
                elif k not in ("thumb", "images", "video"):
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(post.get("record", {}))
    return links


def external_text(post):
    values = []
    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("title", "description") and isinstance(v, str):
                    values.append(v)
                elif k not in ("thumb", "images", "video"):
                    walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(post.get("record", {}).get("embed", {}))
    return "\n".join(values)


def normalize(post):
    r = post["record"]
    uri = at_uri(post["uri"])
    require(isinstance(post.get("cid"), str) and post["cid"], "Post has no CID.")
    date(r["createdAt"])
    require(isinstance(r.get("text"), str), "Post has no text.")
    root = r.get("reply", {}).get("root", {}).get("uri", uri)
    return {"id": identifier("C-", uri), "uri": uri, "root_uri": root, "cid": post["cid"],
            "handle": post["author"]["handle"], "author_did": post["author"]["did"],
            "url": f"https://bsky.app/profile/{post['author']['handle']}/post/{uri.rsplit('/', 1)[-1]}",
            "date": r["createdAt"], "text": r["text"], "external_summary": external_text(post),
            "links": post_links(post)}


def duplicate_source(post, source):
    urls = {canonical(source[k]) for k in ("url", "attachment_url") if source.get(k)}
    if post['uri'] == source.get('post_uri'):
        return True
    if post["url"] and canonical(post["url"]) in urls:
        return True
    return any((canonical(link) in urls if link.startswith(("https://", "http://"))
                else link == source.get("post_uri")) for link in post["links"])


def read_source_post(run, value, reader):
    run.active()
    require(not (run.path / 'source-post.json').exists(), 'Source post is already frozen.')
    uri = at_uri(value)
    posts = reader.get('app.bsky.feed.getPosts', uris=[uri]).get('posts', [])
    require(len(posts) == 1, 'Source post is unavailable.')
    post = normalize(posts[0])
    require(post['uri'].rsplit('/', 1)[-1] == uri.rsplit('/', 1)[-1], 'API returned another source post.')
    output = {'post': post, 'external_urls': list(dict.fromkeys(u for u in post['links'] if u.startswith(('https://', 'http://')))),
              'observed_at': iso(), 'public_writes': 0}
    write(run.path / 'source-post.json', output)
    run.event('source_post_read', uri=post['uri'], cid=post['cid'])
    return output


def collect(run, discovery, reader):
    run.active()
    require(not (run.path / "candidates.json").exists(), "Collection is frozen; start a new run to repeat.")
    source = read(run.path / "source.json")
    if source['text_kind'] == 'unavailable':
        output = {'candidates': [], 'warnings': ['Source unavailable; discovery was not attempted.'],
                  'excluded': [], 'raw_feed_rows': 0, 'precap_matches': 0, 'candidate_count': 0,
                  'coverage': 'No source content was available.'}
        write(run.path / 'discovery.json', discovery)
        write(run.path / 'candidates.json', output)
        run.event('collection_complete', candidates=0, warnings=output['warnings'])
        return output
    keywords = discovery.get("keywords", [])
    require(1 <= len(keywords) <= 30 and all(isinstance(k, str) and 2 <= len(k) <= 100 for k in keywords), "Need 1–30 topical keywords.")
    actors = discovery.get("actors", [])
    require(len(actors) <= 10, "At most 10 discovered seed accounts.")
    for actor in actors:
        require(set(actor) >= {"handle", "provenance_url"} and isinstance(actor["handle"], str), "Seed accounts need handles and provenance URLs.")
        web_url(actor["provenance_url"])
    direct = discovery.get("post_urls", [])
    require(len(direct) <= 30, "At most 30 direct post URLs.")
    uris = [at_uri(v) for v in direct]
    queries = discovery.get("bsky_queries", [])
    require(len(queries) <= 4 and all(isinstance(q, str) and 0 < len(q) <= 300 for q in queries), "At most 4 short API search queries.")
    write(run.path / "discovery.json", discovery)
    lower = date(run.meta["started_at"]) - dt.timedelta(days=run.meta["limits"]["days"])
    found, excluded, warnings = {}, [], []
    feed_rows = 0

    def add(raw, via, explicit=False):
        try:
            p = normalize(raw)
            if not lower <= date(p["date"]) <= now() + dt.timedelta(minutes=5):
                return
            if not p["text"].strip():
                return
            if duplicate_source(p, source):
                excluded.append({"uri": p["uri"], "reason": "source_already_shared"})
                return
            blob = (p["text"] + "\n" + p["external_summary"]).casefold()
            matches = [k for k in keywords if k.casefold() in blob]
            if not matches and not explicit:
                return
            p.update(keyword_matches=matches, keyword_score=len(matches), discovered_via=via)
            prior = found.get(p["root_uri"])
            if prior is None or (p["keyword_score"], date(p["date"])) > (prior["keyword_score"], date(prior["date"])):
                found[p["root_uri"]] = p
        except (RunError, KeyError, TypeError, ValueError):
            excluded.append({"uri": raw.get("uri"), "reason": "invalid_post_data"})

    try:
        for i in range(0, len(uris), 25):
            for p in reader.get("app.bsky.feed.getPosts", uris=uris[i:i+25]).get("posts", []):
                add(p, "direct_web_result", True)
        for q in queries:
            try:
                result = reader.get("app.bsky.feed.searchPosts", q=q, sort="latest", limit=30)
                for p in result.get("posts", []):
                    add(p, "public_search:" + q)
            except ReadError as exc:
                warnings.append(f"Public search returned {exc.status}; using discovered public feeds and links.")
                break  # An unavailable anonymous endpoint is not retried for each query.
        queue = [(actor, None, 0) for actor in actors]
        pages = 0
        while queue and pages < run.meta["limits"]["feed_pages"]:
            actor, cursor, page = queue.pop(0)
            params = {"actor": actor["handle"], "limit": 50}
            if cursor:
                params["cursor"] = cursor
            try:
                data = reader.get("app.bsky.feed.getAuthorFeed", **params)
            except ReadError as exc:
                warnings.append(f"Feed {actor['handle']} returned {exc.status}.")
                continue
            pages += 1
            rows = data.get("feed", [])
            feed_rows += len(rows)
            last_own_date = None
            for row in rows:
                if not row.get("reason"):
                    add(row.get("post", {}), "feed:" + actor["handle"])
                if not row.get('reason'):
                    try:
                        last_own_date = date(row['post']['record']['createdAt'])
                    except (KeyError, ValueError, RunError, TypeError):
                        pass
            yield_count = sum(p["discovered_via"] == "feed:" + actor["handle"] for p in found.values())
            if page == 0 and data.get('cursor') and last_own_date and last_own_date >= lower and yield_count and len(found) < run.meta['limits']['candidates']:
                queue.append((actor, data['cursor'], 1))
    except RunError as exc:
        warnings.append(str(exc))
    candidates = sorted(found.values(), key=lambda p: (p["keyword_score"], date(p["date"])), reverse=True)[:run.meta["limits"]["candidates"]]
    output = {"candidates": candidates, "warnings": warnings, "excluded": excluded,
              "raw_feed_rows": feed_rows, "precap_matches": len(found), "candidate_count": len(candidates),
              "coverage": "A bounded sample of search results and discovered seed feeds, not the whole network."}
    write(run.path / "candidates.json", output)
    run.event("collection_complete", candidates=len(candidates), raw_feed_rows=feed_rows, warnings=warnings)
    return output


def fetch_contexts(run, ids, reader):
    run.active()
    candidates = {p["id"]: p for p in read(run.path / "candidates.json")["candidates"]}
    path = run.path / "contexts.json"
    contexts = read(path) if path.exists() else {}
    require(set(ids) <= set(candidates), "Unknown candidate ID.")
    require(len(set(contexts) | set(ids)) <= run.meta["limits"]["context_threads"], "Context thread limit reached.")
    for cid in ids:
        if cid in contexts:
            continue
        expected = candidates[cid]
        posts, queried, pending = {}, set(), list(dict.fromkeys([expected["uri"], expected["root_uri"]]))
        valid, error = True, None
        try:
            while pending and len(queried) < 4 and len(posts) < run.meta["limits"]["context_posts"]:
                uri = pending.pop(0)
                if uri in queried:
                    continue
                result = reader.get("app.bsky.feed.getPostThread", uri=uri, depth=2, parentHeight=2)
                queried.add(uri)
                node = result.get("thread", {})
                if uri == expected["uri"]:
                    require(node.get("post", {}).get("uri") == uri and node["post"].get("cid") == expected["cid"], "Selected post changed or is unavailable.")

                def walk(n):
                    if not isinstance(n, dict):
                        return
                    p = n.get("post")
                    if p and len(posts) < run.meta["limits"]["context_posts"]:
                        item = normalize(p)
                        posts[item["uri"]] = item
                        children = n.get("replies", [])
                        if item["author_did"] == expected["author_did"] and p.get("replyCount", 0) > len(children):
                            pending.append(item["uri"])
                    walk(n.get("parent"))
                    for child in n.get("replies", []):
                        walk(child)
                walk(node)
        except (RunError, KeyError, TypeError, ValueError) as exc:
            valid, error = False, str(exc) if isinstance(exc, RunError) else "Invalid public context data."
        contexts[cid] = {"valid": valid, "error": error, "posts": list(posts.values()),
                         "queried_uris": sorted(queried), "scope": "Bounded parent/reply sample, including author continuations; not a claim of complete thread coverage."}
        write(path, contexts)
        run.event("context_complete", candidate_id=cid, valid=valid, posts=len(posts), error=error)
    return contexts


def render_reply(body, source_url=None):
    require(isinstance(body, str) and body.strip() and not re.search(r"https?://|[\x00-\x08\x0b\x0c\x0e-\x1f]", body), "Draft body must be plain text without URLs or control characters.")
    text = PREFIX + body.strip()
    if source_url is None:
        require(len(text) <= 300, "Draft exceeds 300 characters.")
        return {"text": text, "facets": [], "link_mode": "none"}
    if len(text + " " + source_url) <= 300:
        return {"text": text + " " + source_url, "facets": [], "link_mode": "inline_url"}
    text += " Source"
    require(len(text) <= 300, "Draft exceeds 300 characters even with a compact source link.")
    begin = len(text[:-6].encode("utf-8"))
    return {"text": text, "link_mode": "rich_link", "facets": [{"index": {"byteStart": begin, "byteEnd": len(text.encode('utf-8'))},
             "features": [{"$type": "app.bsky.richtext.facet#link", "uri": source_url}]}]}


def capture_discussion_profiles(run, data):
    run.active()
    require(isinstance(data, dict) and set(data) == {'profiles'} and isinstance(data['profiles'], list), 'Supply a discussion-profile batch.')
    candidates = {p['id']: p for p in read(run.path / 'candidates.json')['candidates']}
    contexts, source = read(run.path / 'contexts.json'), read(run.path / 'source.json')
    path = run.path / 'discussion-profiles.json'
    saved = read(path) if path.exists() else {'version': 1, 'profiles': {}}
    new = {}
    for raw in data['profiles']:
        cid = raw.get('candidate_id') if isinstance(raw, dict) else None
        require(cid in candidates and cid not in saved['profiles'] and cid not in new, 'Unknown or already frozen discussion profile.')
        try:
            new[cid] = discussion_profile.validate(raw, candidates[cid], contexts.get(cid, {}), source)
            discussion_profile.require_criterion(new[cid], run.meta.get('discussion_profile_criterion'))
        except discussion_profile.ProfileError as exc:
            raise RunError(str(exc)) from None
    saved['profiles'].update(new)
    write(path, saved)
    for cid, profile in new.items():
        run.event('discussion_profile_frozen', candidate_id=cid, profile_id=profile['profile_id'],
                  entry_decision=profile['contribution']['decision'], observed_posts=profile['observed_posts'],
                  criterion=profile['contribution'].get('criterion'), actor='program', interpretation_verified=False)
    return saved


def validate_assessment(run, assessment):
    require(set(assessment) == {"summary", "decisions", "limitations"}, "Assessment requires summary, decisions, limitations.")
    require(isinstance(assessment["summary"], str) and isinstance(assessment["limitations"], list)
            and all(isinstance(x, str) for x in assessment['limitations']), "Invalid assessment summary.")
    source = read(run.path / "source.json")
    paragraphs = {p["id"]: p["text"] for p in source["paragraphs"]}
    candidates = {p["id"]: p for p in read(run.path / "candidates.json")["candidates"]}
    contexts = read(run.path / "contexts.json") if (run.path / "contexts.json").exists() else {}
    profile_path = run.path / 'discussion-profiles.json'
    profiles = read(profile_path)['profiles'] if profile_path.exists() else {}
    require(isinstance(assessment["decisions"], list), "Decisions must be an array.")
    ids, bodies, output = set(), set(), []
    for d in assessment["decisions"]:
        require(isinstance(d, dict), "Each decision must be an object.")
        cid = d.get("candidate_id")
        require(cid in candidates and cid not in ids, "Unknown or duplicate decision ID.")
        ids.add(cid)
        require(d.get("decision") in ("select", "reject") and isinstance(d.get("reason"), str) and d["reason"].strip(), "Decision and reason are required.")
        result = {**d, "candidate": candidates[cid]}
        require(isinstance(d.get('limitations', []), list) and all(isinstance(x, str) for x in d.get('limitations', [])), 'Invalid decision limitations.')
        if d["decision"] == "select":
            require(d.get("relation") in ("direct", "comparative"), "Selected relation must be direct or comparative.")
            require(contexts.get(cid, {}).get("valid"), "Selected candidate needs a valid, unchanged context.")
        if run.meta.get('discussion_profiles_required') and contexts.get(cid, {}).get('valid'):
            try:
                result['discussion_profile'] = discussion_profile.gate(profiles.get(cid), candidates[cid], contexts[cid],
                    source, d.get('discussion_profile_id'), d['decision'] == 'select',
                    criterion=run.meta.get('discussion_profile_criterion'))
            except discussion_profile.ProfileError as exc:
                raise RunError(str(exc)) from None
        if d['decision'] == 'select':
            required_fields = ('language', 'context_connection', 'draft_body')
            if run.meta.get('discussion_profile_criterion') != discussion_profile.THEMATIC_FIT:
                required_fields += ('added_information',)
            require(all(isinstance(d.get(k), str) and d[k].strip() for k in required_fields), 'Selected drafts need language, context connection and text.')
            require(d.get('added_information') is None or isinstance(d['added_information'], str), 'Optional added information must be text or null.')
            body_key = " ".join(d["draft_body"].casefold().split())
            require(body_key not in bodies, "Each thread needs a distinct contextual draft.")
            bodies.add(body_key)
            require(isinstance(d.get('source_evidence'), list) and isinstance(d.get('context_evidence'), list), 'Evidence must be arrays.')
            for evidence in d.get("source_evidence", []):
                require(isinstance(evidence, dict), 'Evidence must contain objects.')
                require(isinstance(evidence.get("quote"), str) and len(evidence["quote"].strip()) >= 8 and evidence["quote"] in paragraphs.get(evidence.get("paragraph_id"), ""), "Source evidence quote is missing or not in the frozen source.")
            require(d.get("source_evidence") or source['text_kind'] == 'topic_brief', "Selected drafts need source evidence.")
            texts = {p["uri"]: p["text"] for p in contexts[cid]["posts"]}
            for evidence in d.get("context_evidence", []):
                require(isinstance(evidence, dict), 'Evidence must contain objects.')
                require(isinstance(evidence.get("quote"), str) and len(evidence["quote"].strip()) >= 8 and evidence["quote"] in texts.get(evidence.get("post_uri"), ""), "Context quote is missing or not in the frozen thread.")
            require(d.get("context_evidence"), "Selected drafts need context evidence.")
            result["reply"] = render_reply(d["draft_body"], source["attachment_url"])
            result["reply"]["characters"] = len(result["reply"]["text"])
            reply_uri = d.get('reply_to_uri', candidates[cid]['uri'])
            targets = {p['uri']: p for p in contexts[cid]['posts']}
            require(reply_uri in targets, 'Reply target must be part of the verified context.')
            result['reply_target'] = {k: targets[reply_uri][k] for k in ('uri', 'cid', 'url', 'date')}
        else:
            require(not d.get("draft_body"), "Rejected candidates must not have a draft.")
        output.append(result)
    require(len(bodies) <= run.meta["limits"]["selected"], "Too many selected drafts.")
    return output


def add_event(run, data):
    run.active()
    kind = data.get("kind")
    require(kind in ("human_request", "human_response", "human_correction", "human_review", "usage", "note", "stage", "model_stage"), "Unknown event kind.")
    fields = {k: v for k, v in data.items() if k not in ("kind", "at", "id")}
    if kind == 'model_stage':
        try:
            fields = workflow_record.model_stage(data, executor=run.meta.get('model_executor', 'codex'))
        except ValueError as exc:
            raise RunError(str(exc)) from None
    for name in ("human_active_seconds", "cost_usd", "input_tokens", "output_tokens", "cached_input_tokens"):
        if fields.get(name) is not None:
            value = fields[name]
            require(type(value) in (int, float) and math.isfinite(value) and value >= 0, f"Invalid {name}.")
    if kind == "human_response":
        events = run.events()
        requests = {e["id"]: e for e in events if e["kind"] == "human_request"}
        request_id = fields.get("request_id")
        require(request_id in requests and not any(e.get("request_id") == request_id for e in events if e["kind"] == "human_response"), "Unknown or already resolved human request.")
        fields["waiting_seconds"] = round((now() - date(requests[request_id]["at"])).total_seconds(), 3)
    if fields.get("human_active_seconds") is not None:
        require(kind in ('human_response', 'human_correction', 'human_review'), 'Active human time must belong to a human response, correction or review.')
        require(fields.get("time_basis") in ("user_reported", "timed_editor_session"), "Human time needs a real measurement basis.")
    if kind == "usage":
        require(fields.get("provider") and fields.get("measurement_source"), "Usage needs provider and measurement_source.")
        require(all(fields.get(k) is None or type(fields[k]) is int for k in ('input_tokens', 'output_tokens', 'cached_input_tokens')), 'Token counts must be integers.')
        if fields.get('cached_input_tokens') is not None and fields.get('input_tokens') is not None:
            require(fields['cached_input_tokens'] <= fields['input_tokens'], 'Cached tokens exceed total input tokens.')
    return run.event(kind, **fields)


def measures(run, usage_complete=False):
    events = run.events()
    network = [e for e in events if e["kind"] == "public_get"]
    usage = [e for e in events if e["kind"] == "usage"]
    actual = sum(e["cost_usd"] for e in usage if e.get("cost_usd") is not None)
    cost_known = bool(usage) and all(e.get("cost_usd") is not None for e in usage)
    human = [e for e in events if e["kind"] in ("human_request", "human_correction", "human_review")]
    timed = [e for e in events if e.get("human_active_seconds") is not None]
    return {"elapsed_seconds": round((now() - date(run.meta["started_at"])).total_seconds(), 3),
            "public_get_requests": len(network), "public_get_seconds": round(sum(e["elapsed_seconds"] for e in network), 3),
            "human_interventions": sum(e["kind"] in ("human_request", "human_correction") for e in human),
            "human_requests": sum(e["kind"] == "human_request" for e in human),
            "human_responses": sum(e["kind"] == "human_response" for e in events),
            "pending_human_requests": sum(e["kind"] == "human_request" for e in human)-sum(e["kind"] == "human_response" for e in events),
            "human_editor_reviews": sum(e["kind"] == "human_review" for e in human),
            "human_waiting_seconds": round(sum(e.get("waiting_seconds", 0) for e in events), 3),
            "human_active_seconds": sum(e["human_active_seconds"] for e in timed) if timed else None,
            "human_active_time_coverage": "recorded intervals only" if timed else "unmeasured",
            "actual_cost_usd": actual if usage_complete and cost_known else None,
            "recorded_partial_cost_usd": actual if any(e.get("cost_usd") is not None for e in usage) else None,
            "usage_coverage": "complete" if usage_complete and cost_known else ("partial" if usage else "unavailable"),
            "usage_records": usage, "public_writes": 0}


def report_html(result):
    e = lambda value: html.escape(str(value))
    m = result["measurements"]
    parts = ['<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BotyLab — kontextový dry-run</title><style>:root{color-scheme:light dark}body{font:17px/1.6 system-ui;max-width:1000px;margin:36px auto;padding:0 22px}blockquote{margin-left:0;padding-left:1em;border-left:3px solid #888;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:inherit}td,th{text-align:left;vertical-align:top;padding:.6em;border-bottom:1px solid #8886}table{width:100%;border-collapse:collapse}</style>']
    title = e(result['source']['title'])
    if result['source']['attachment_url']:
        title = '<a href="'+e(result['source']['attachment_url'])+'">'+title+'</a>'
    parts.append('<h1>Kontextový dry-run</h1><p>'+title+' · jazyk zdroje '+e(result['source']['language'])+'</p><p>'+e(result['summary'])+'</p>')
    parts.append('<p><strong>Publikováno: 0.</strong> Čas: '+str(m['elapsed_seconds'])+' s. Lidské zásahy: '+str(m['human_interventions'])+'. Aktivní lidský čas: '+e(m['human_active_seconds'] if m['human_active_seconds'] is not None else 'nezměřeno')+'. Úplná účtovaná cena: '+e(m['actual_cost_usd'] if m['actual_cost_usd'] is not None else 'nedostupná')+'.</p>')
    if m['recorded_partial_cost_usd'] is not None:
        parts.append('<p>Zaznamenaná dílčí cena: '+str(m['recorded_partial_cost_usd'])+' USD. Pokrytí: '+e(m['usage_coverage'])+'.</p>')
    parts.append('<p>Předvýběr: '+str(result['candidate_count'])+' příspěvků; kontext načten: '+str(result['contexts_read'])+'; návrhů: '+str(result['selected_count'])+'. Ověření cituje uložený zdroj a výřez diskuse; účinek na čtenáře se neměřil.</p>')
    for d in result['decisions']:
        p = d['candidate']
        target_url = d.get('reply_target', {}).get('url', p['url'])
        parts.append('<h2><a href="'+e(target_url)+'">'+e(p['handle'])+'</a> · '+e(p['date'][:10])+'</h2><p>'+e(d['reason'])+'</p>')
        if d.get('discussion_profile'):
            parts.append(discussion_profile.html_view(d['discussion_profile']))
        if d['decision'] == 'select':
            parts.append('<p>Vazba: '+e(d['relation'])+'. '+e(d['context_connection'])+'</p>')
            if d.get('added_information'):
                parts.append('<p>Volitelná doplňující informace: '+e(d['added_information'])+'</p>')
            reply = d['reply']
            if reply['link_mode'] == 'none':
                parts.append('<blockquote>'+e(reply['text'])+'</blockquote><p>'+str(reply['characters'])+' znaků. Bez připojené URL.</p>')
            elif reply['link_mode'] == 'inline_url':
                body = e(reply['text'][:-len(result['source']['attachment_url'])])
                link_label = e(result['source']['attachment_url'])
            else:
                body, link_label = e(reply['text'][:-6]), 'Source'
            if reply['link_mode'] != 'none':
                parts.append('<blockquote>'+body+'<a href="'+e(result['source']['attachment_url'])+'">'+link_label+'</a></blockquote><p>'+str(reply['characters'])+' znaků. Jazyk '+e(d['language'])+'.</p>')
            parts.append('<ul>'+''.join('<li>'+e(v)+'</li>' for v in d.get('limitations', []))+'</ul>')
        else:
            parts.append('<p><strong>Nereagovat.</strong></p>')
    parts.append('<h2>Rozsah a omezení</h2><ul>'+''.join('<li>'+e(x)+'</li>' for x in result['limitations'])+'</ul>')
    parts.append('<details><summary>Úplný záznam</summary><pre>'+e(json.dumps(result, ensure_ascii=False, indent=2))+'</pre></details></html>')
    return ''.join(parts)


def finalize(run, assessment, usage_complete=False):
    run.active()
    decisions = validate_assessment(run, assessment)
    source, pool = read(run.path / "source.json"), read(run.path / "candidates.json")
    contexts = read(run.path / "contexts.json") if (run.path / "contexts.json").exists() else {}
    metrics = measures(run, usage_complete)
    limits = list(assessment["limitations"]) + pool["warnings"] + source.get("caveats", [])
    if source["text_kind"] not in ("full_text", "topic_brief"):
        limits.append("Kontrola dokladů pracuje s uloženým výřezem nebo samotným příspěvkem; tento záznam neobsahuje celý článek.")
    if metrics["usage_coverage"] != "complete":
        limits.append("Úplná účtovaná spotřeba a cena nejsou dostupné; neznámé údaje nejsou nula.")
    elapsed = metrics["elapsed_seconds"]
    status = 'source_unavailable' if source['text_kind'] == 'unavailable' else 'completed'
    result = {"mode": "dry-run", "status": status, "started_at": run.meta["started_at"], "ended_at": iso(),
              "source": source, "summary": assessment["summary"], "decisions": decisions,
              "selected_count": sum(d["decision"] == "select" for d in decisions), "candidate_count": len(pool["candidates"]),
              "contexts_read": len(contexts), "measurements": metrics, "limitations": limits,
              "planned_seconds": run.meta["limits"]["seconds"], "overrun_seconds": round(max(0, elapsed-run.meta['limits']['seconds']), 3),
              "publication_enabled": False, "public_writes": 0}
    result['discussion_profiles'] = read(run.path / 'discussion-profiles.json')['profiles'] if (run.path / 'discussion-profiles.json').exists() else {}
    result['discussion_profile_criterion'] = run.meta.get('discussion_profile_criterion')
    result['revision_of'] = run.meta.get('revision_of')
    result['model_stages'] = [e for e in run.events() if e['kind'] == 'model_stage']
    result['model_executor'] = run.meta.get('model_executor', 'codex')
    if result["overrun_seconds"]:
        result["limitations"].append("Celkový interval včetně přípravy a kontroly přehledu překročil zadaný čas; překročení je vykázáno.")
    write(run.path / "assessment.json", assessment)
    write(run.path / "report.json", result)
    (run.path / "report.html").write_text(report_html(result), encoding="utf-8")
    run.meta.update(status=status, ended_at=result["ended_at"])
    write(run.path / "run.json", run.meta)
    run.event("completed", selected=result["selected_count"], elapsed_seconds=elapsed)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("url")
    begin.add_argument("--output-root", default="output/amplifier-runs")
    begin.add_argument("--days", type=int, default=14)
    begin.add_argument("--seconds", type=int, default=900)
    topical = sub.add_parser("start-topic")
    topical.add_argument("topic")
    topical.add_argument("--output-root", default="output/amplifier-runs")
    topical.add_argument("--days", type=int, default=14)
    topical.add_argument("--seconds", type=int, default=900)
    for cmd in (begin, topical):
        cmd.add_argument('--parent-run')
        cmd.add_argument('--revision-reason')
        cmd.add_argument('--executor', default='codex')
    for name in ("read-post", "source", "collect", "context", "profile", "event", "check", "finalize"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run", required=True)
        if name == 'read-post':
            cmd.add_argument('--url', required=True)
        elif name == "context":
            cmd.add_argument("--ids", required=True, nargs="+")
        else:
            cmd.add_argument("--input", required=True)
        if name == "finalize":
            cmd.add_argument("--usage-complete", action="store_true")
    args = parser.parse_args()
    if args.action in ("start", "start-topic"):
        path = start(getattr(args, 'url', None), args.output_root,
                     {"days": args.days, "seconds": args.seconds}, topic=getattr(args, 'topic', None),
                     parent_run=args.parent_run, revision_reason=args.revision_reason, executor=args.executor)
        print(json.dumps({"run_dir": str(path), "publication_enabled": False}, ensure_ascii=False))
        return
    with locked(args.run) as run:
        reader = PublicReader(run)
        if args.action == 'read-post':
            output = read_source_post(run, args.url, reader)
        elif args.action == "source":
            value = capture_source(run, read(args.input))
            output = {"paragraphs": len(value["paragraphs"]), "text_kind": value["text_kind"]}
        elif args.action == "collect":
            value = collect(run, read(args.input), reader)
            output = {"candidate_count": value["candidate_count"], "warnings": value["warnings"]}
        elif args.action == "context":
            value = fetch_contexts(run, args.ids, reader)
            output = {k: {"valid": v["valid"], "posts": len(v["posts"]), "error": v["error"]} for k, v in value.items()}
        elif args.action == "event":
            output = add_event(run, read(args.input))
        elif args.action == 'profile':
            value = capture_discussion_profiles(run, read(args.input))
            output = {cid: {'profile_id': p['profile_id'], 'decision': p['contribution']['decision']} for cid, p in value['profiles'].items()}
        elif args.action == 'check':
            run.active()
            value = validate_assessment(run, read(args.input))
            output = {'formally_checked': len(value), 'selected': sum(d['decision'] == 'select' for d in value),
                      'run_completed': False, 'semantic_interpretation_verified': False, 'public_writes': 0}
        else:
            value = finalize(run, read(args.input), args.usage_complete)
            output = {"selected_count": value["selected_count"], "measurements": value["measurements"], "report": str(run.path / "report.html")}
        print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (RunError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "public_writes": 0}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
