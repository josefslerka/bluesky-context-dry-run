#!/usr/bin/env python3
"""Offline coordination of three virtual accounts. No network client or live publisher."""
from __future__ import annotations

import argparse
import contextlib
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import html
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time
import participant_invitation
import discussion_profile
import workflow_record


ACCOUNTS = [
    {"id": "virtual:V1", "name": "BotyLab V1 · Data", "role": "data", "languages": ["cs", "en"]},
    {"id": "virtual:V2", "name": "BotyLab V2 · Rozlišení", "role": "clarification", "languages": ["cs", "en"]},
    {"id": "virtual:V3", "name": "BotyLab V3 · Vysvětlení", "role": "explanation", "languages": ["cs", "en", "es"]},
]


class SimulationError(Exception):
    pass


def require(value, message):
    if not value:
        raise SimulationError(message)


def now():
    return dt.datetime.now(dt.timezone.utc)


def iso():
    return now().isoformat(timespec="milliseconds")


def date(value):
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "Timestamps need a timezone.")
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def active(path):
    meta = read(Path(path) / "run.json")
    require(meta["status"] == "preparing", "Completed simulations are immutable; start a new one.")
    return meta


@contextlib.contextmanager
def connect(path):
    db = sqlite3.connect(Path(path) / "queue.sqlite3", timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def emit(db, kind, actor="coordinator", job=None, virtual_second=0, **detail):
    cursor = db.execute("INSERT INTO events(at,virtual_second,actor,kind,job_id,detail) VALUES(?,?,?,?,?,?)",
                        (iso(), virtual_second, actor, kind, job, json.dumps(detail, ensure_ascii=False)))
    return cursor.lastrowid


def start(topic, output_root, session_log=None, *, parent_run=None, revision_reason=None, executor='codex'):
    require(isinstance(topic, str) and 3 <= len(topic.strip()) <= 1000, "Topic needs 3–1000 characters.")
    try:
        revision = workflow_record.revision(parent_run, revision_reason)
        executor = workflow_record.executor_label(executor)
    except ValueError as exc:
        raise SimulationError(str(exc)) from None
    path = Path(output_root).resolve() / (now().strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3))
    session = read(session_log) if session_log else None
    if session:
        require(date(session["task_started_at"]) <= now(), "Session clock cannot be in the future.")
    path.mkdir(parents=True, exist_ok=False)
    write(path / "run.json", {"version": 3, "discussion_profiles_required": True,
          "discussion_profile_criterion": discussion_profile.THEMATIC_FIT, "id": path.name, "status": "preparing",
          "topic": topic.strip(), "started_at": iso(), "accounts": ACCOUNTS, "revision_of": revision,
          "model_executor": executor,
          "mode": "offline-simulation", "publication_enabled": False, "public_writes": 0,
          "session_clock": session, "session_clock_sha256": fingerprint(session_log) if session_log else None})
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE queue(id TEXT PRIMARY KEY, root_uri TEXT, account_id TEXT,
                status TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL, due_second REAL, payload TEXT NOT NULL);
            CREATE UNIQUE INDEX one_job_per_thread ON queue(root_uri) WHERE active=1;
            CREATE UNIQUE INDEX one_job_per_account ON queue(account_id) WHERE active=1;
            CREATE TABLE local_posts(job_id TEXT PRIMARY KEY REFERENCES queue(id),
                receipt TEXT UNIQUE NOT NULL, account_id TEXT NOT NULL, text TEXT NOT NULL,
                target_uri TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                virtual_second REAL NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
                job_id TEXT, detail TEXT NOT NULL);
        """)
        emit(db, "simulation_started", topic=topic, accounts=[a["id"] for a in ACCOUNTS],
             transport="local SQLite only", public_writes=0)
    return path


def check_quote(evidence, texts, label):
    require(isinstance(evidence, list) and evidence, f"Missing {label} evidence.")
    for item in evidence:
        require(isinstance(item, dict), f"Invalid {label} evidence.")
        key = item.get("post_uri") if label == "context" else item.get("paragraph_id")
        quote = item.get("quote")
        require(isinstance(quote, str) and len(quote.strip()) >= 8 and quote in texts.get(key, ""),
                f"Unverified {label} quote.")


def validate_fictional_profile(item, target, context, research):
    profile = item.get("psychological_profile")
    require(isinstance(profile, dict), "A complete fictional profile is required.")
    require(research['candidates'].get('context_origin') == 'synthetic',
            "Psychological adaptation is available only for invented recipients.")
    fields = {'kind', 'id', 'motivation', 'anticipated_emotion', 'formulation_strategy', 'empirical_support'}
    require(set(profile) == fields and profile['kind'] == 'fictional_hypothesis'
            and profile['empirical_support'] is None, "Profiles must be explicitly fictional, without empirical claims.")
    require(isinstance(profile['id'], str) and re.fullmatch(r'synthetic:persona:[A-Za-z0-9_-]+', profile['id']), "Invalid fictional recipient ID.")
    require(target['author_did'] == profile['id'] == target['handle'], "Profile must identify only its invented recipient.")
    for post in context['posts']:
        require(post.get('origin') == 'synthetic' and post['uri'].startswith('sim://')
                and post['root_uri'].startswith('sim://') and post['cid'].startswith('synthetic:')
                and post['author_did'].startswith('synthetic:persona:') and post['url'] is None,
                "Real public posts cannot be joined to psychological profiles.")
    for key in ('motivation', 'anticipated_emotion', 'formulation_strategy'):
        require(isinstance(profile[key], str) and 3 <= len(profile[key]) <= 1000
                and not re.search(r'https?://|www\.|bsky\.app|@[A-Za-z]', profile[key]), "Invalid fictional profile description.")
    baseline, adapted = item.get('baseline_draft_body'), item['draft_body']
    require(isinstance(baseline, str) and baseline.strip() and len('[BotyLab · AI · V1] ' + baseline) <= 300
            and not re.search(r'https?://|www\.|bsky\.app|[\x00-\x1f]', baseline, re.I), "Invalid baseline reply.")
    require(' '.join(baseline.split()) != ' '.join(adapted.split()), "Profile adaptation needs an actual wording change.")
    numbers = lambda text: set(re.findall(r'\d+(?:[.,]\d+)?%?', text))
    require(numbers(baseline) == numbers(adapted), "Profile adaptation changed numerical facts.")
    trace = item.get('adaptation_trace')
    require(isinstance(trace, list) and trace, "Profile adaptation needs a trace of wording changes.")
    for change in trace:
        require(isinstance(change, dict) and set(change) == {'field', 'before', 'after', 'reason'}, "Invalid adaptation trace.")
        require(change['field'] in ('motivation', 'anticipated_emotion', 'formulation_strategy'), "Unknown profile field in trace.")
        require(all(isinstance(change[k], str) and len(change[k].strip()) >= 3 for k in ('before', 'after', 'reason')),
                "Empty adaptation trace.")
        require(change['before'] in baseline and change['after'] in adapted and change['before'] != change['after'],
                "Wording trace is not present in the actual drafts.")


def validate_job(item, research):
    require(isinstance(item, dict), "Job must be an object.")
    require(item.get("decision", "reply") in ("reply", "reject"), "Invalid decision.")
    for name in ("candidate_id", "reason"):
        require(isinstance(item.get(name), str) and item[name].strip(), f"Missing {name}.")
    candidates = {p["id"]: p for p in research["candidates"]["candidates"]}
    candidate = candidates.get(item["candidate_id"])
    require(candidate, "Unknown candidate.")
    context = research["contexts"].get(item["candidate_id"], {})
    require(context.get("valid"), "Candidate has no valid frozen context.")
    posts = {p["uri"]: p for p in context.get("posts", [])}
    anchor = posts.get(candidate["uri"])
    require(anchor and anchor["cid"] == candidate["cid"], "Frozen candidate CID does not match its context.")
    target = posts.get(item.get("reply_to_uri", candidate["uri"]))
    require(target, "Reply target is outside the verified context.")
    result = {**item, "target": target, "root_uri": candidate["root_uri"],
              "carrier": {"handle": target["handle"], "did": target["author_did"]}}
    if research.get('discussion_profiles_required'):
        error = research.get('discussion_profile_errors', {}).get(item['candidate_id'])
        require(not error, error or 'Invalid discussion profile.')
        result['discussion_profile'] = discussion_profile.gate(
            research.get('discussion_profiles', {}).get(item['candidate_id']), candidate, context, research['source'],
            item.get('discussion_profile_id'), item.get('decision', 'reply') == 'reply',
            criterion=research.get('discussion_profile_criterion'))
    if item.get("decision") == "reject":
        require(not item.get("draft_body"), "Rejected jobs cannot carry a draft.")
        return result
    for name in ("support_basis", "language", "role", "draft_body"):
        require(isinstance(item.get(name), str) and item[name].strip(), f"Missing {name}.")
    body = item["draft_body"].strip()
    require(not re.search(r"https?://|www\.|bsky\.app|[\x00-\x1f]", body, re.I),
            "Supportive replies must be plain text without URLs or control characters.")
    check_quote(item.get("context_evidence"), {p["uri"]: p["text"] for p in posts.values()}, "context")
    if item.get("source_evidence"):
        check_quote(item["source_evidence"], {p["id"]: p["text"] for p in research["source"]["paragraphs"]}, "source")
    require(len("[BotyLab · AI · V1] " + body) <= 300, "Reply exceeds 300 characters including its label.")
    if 'participant_invitation' in item:
        require('psychological_profile' not in item, 'Participant and fictional profiles cannot be combined.')
        participant_invitation.validate_job(item, target, context, research)
    elif any(k in item for k in ('psychological_profile', 'baseline_draft_body', 'adaptation_trace')):
        validate_fictional_profile(item, target, context, research)
    result["draft_body"] = body
    return result


def check_plan(path, research_dir, plan):
    meta = active(path)
    require(not (Path(path) / "plan.json").exists(), "Plan is already frozen.")
    require(plan.get("topic") == meta["topic"], "Plan topic differs from the assignment.")
    require(plan.get("intent") == "support_factual_contribution", "Expected a factual supportive-reply plan.")
    require(isinstance(plan.get("jobs"), list) and len(plan["jobs"]) <= 30, "At most 30 queue items.")
    require(isinstance(plan.get("limitations", []), list) and all(isinstance(x, str) for x in plan.get("limitations", [])), "Limitations must be strings.")
    require(isinstance(plan.get("synthetic_reactions", []), list), "Synthetic reactions must be an array.")
    research_dir = Path(research_dir).resolve()
    names = {"source": "source.json", "candidates": "candidates.json", "contexts": "contexts.json"}
    research = {key: read(research_dir / name) for key, name in names.items()}
    research["provenance"] = {"directory": str(research_dir), "reused_snapshot": True,
          "hashes": {name: fingerprint(research_dir / name) for name in names.values()},
          "imported_at": iso(), "new_discovery_in_this_simulator": False,
          "context_origin": research['candidates'].get('context_origin', 'public_snapshot')}
    if (research_dir / "discovery.json").is_file():
        research["discovery"] = read(research_dir / "discovery.json")
    if (research_dir / 'invitation-context.json').is_file():
        research['invitation_context'] = read(research_dir / 'invitation-context.json')
        research['provenance']['hashes']['invitation-context.json'] = fingerprint(research_dir / 'invitation-context.json')
    public_context = (research['provenance']['context_origin'] not in ('synthetic', 'consented_participant_invitation')
                      or any(p.get('uri', '').startswith('at://') for context in research['contexts'].values()
                             for p in context.get('posts', [])))
    research['discussion_profiles_required'] = bool(public_context and meta.get('discussion_profiles_required'))
    research['discussion_profile_criterion'] = meta.get('discussion_profile_criterion') if public_context else None
    research['discussion_profiles'], research['discussion_profile_errors'] = {}, {}
    profile_path = research_dir / 'discussion-profiles.json'
    if public_context and profile_path.is_file():
        research['provenance']['hashes']['discussion-profiles.json'] = fingerprint(profile_path)
        candidates = {p['id']: p for p in research['candidates']['candidates']}
        for cid, profile in read(profile_path)['profiles'].items():
            try:
                research['discussion_profiles'][cid] = discussion_profile.ensure_current(
                    profile, candidates[cid], research['contexts'].get(cid, {}), research['source'])
            except (discussion_profile.ProfileError, KeyError, TypeError) as exc:
                research['discussion_profile_errors'][cid] = str(exc)
    checked = []
    for item in plan["jobs"]:
        try:
            checked.append((validate_job(item, research), None))
        except (SimulationError, KeyError, TypeError, ValueError) as exc:
            checked.append((item if isinstance(item, dict) else {}, str(exc)))
    return meta, research, checked


def load_plan(path, research_dir, plan):
    meta, research, checked = check_plan(path, research_dir, plan)
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        require(not db.execute("SELECT 1 FROM queue").fetchone(), "Queue is already populated.")
        used_roots, used_accounts, used_texts = {}, set(), set()
        for index, (item, error) in enumerate(checked, 1):
            job = f"J{index:03d}"
            status, account, reason, enabled, due = "rejected", None, error or item["reason"], 0, None
            emit(db, "queue_received", job=job, candidate_id=item.get("candidate_id"))
            if item.get('discussion_profile') and not error:
                dp = item['discussion_profile']
                emit(db, 'discussion_profile_applied', job=job, profile_id=dp['profile_id'],
                     entry_decision=dp['contribution']['decision'], observed_posts=dp['observed_posts'],
                     criterion=dp['contribution'].get('criterion'), reply_mode=dp['contribution'].get('reply_mode'))
            if not error and item.get("decision") != "reject":
                key = " ".join(item["draft_body"].casefold().split())
                eligible = [a for a in meta["accounts"] if a["id"] not in used_accounts
                            and item["language"] in a["languages"] and a["role"] == item["role"]]
                if item.get("preferred_account"):
                    eligible = [a for a in eligible if a["id"] == item["preferred_account"]]
                if item["root_uri"] in used_roots:
                    status, reason = "held", "thread_already_reserved_by:" + used_roots[item["root_uri"]]
                elif key in used_texts:
                    status, reason = "held", "duplicate_text"
                elif not eligible:
                    status, reason = "held", "no_available_account_for_role_and_language"
                else:
                    account = eligible[0]["id"]
                    status, enabled, due = "ready", 1, (len(used_accounts) + 1) * 10
                    used_roots[item["root_uri"]] = job
                    used_accounts.add(account)
                    used_texts.add(key)
                    item["text"] = f"[BotyLab · AI · {account.rsplit(':', 1)[-1]}] " + item["draft_body"]
                    if item.get('psychological_profile'):
                        emit(db, 'fictional_profile_applied', job=job,
                             profile_id=item['psychological_profile']['id'],
                             changed_fields=sorted({x['field'] for x in item['adaptation_trace']}),
                             empirical_support=None)
                    if item.get('participant_invitation'):
                        invitation = item['participant_invitation']
                        emit(db, 'participant_invitation_prepared', job=job, pattern=invitation['pattern'],
                             selection_basis=invitation['selection_basis'], used_dimensions=invitation['used_profile_dimensions'],
                             scope=invitation['scope'], profile_validated=False)
                    emit(db, "assigned", job=job, account=account, virtual_due_second=due,
                         basis="role and language; one account and one job per thread")
            db.execute("INSERT INTO queue(id,root_uri,account_id,status,active,reason,due_second,payload) VALUES(?,?,?,?,?,?,?,?)", (job, item.get("root_uri"), account,
                       status, enabled, reason, due, json.dumps(item, ensure_ascii=False)))
            if not enabled:
                emit(db, status, job=job, reason=reason)
        db.commit()
    write(Path(path) / "research.json", research)
    write(Path(path) / "plan.json", plan)
    return status_data(path)


def prepare_invitation(path, estimate_file, corpus_file, consent_file):
    meta = active(path)
    require(not (Path(path) / 'plan.json').exists(), 'Plan is already frozen.')
    inputs = {'estimate': read(estimate_file), 'corpus': read(corpus_file), 'consent': read(consent_file)}
    try:
        case = participant_invitation.make_case(inputs, meta['topic'], iso())
    except (ValueError, TypeError, KeyError) as exc:
        raise SimulationError(str(exc)) from None
    directory = Path(path) / 'participant-research'
    directory.mkdir(exist_ok=False)
    for key, filename in [('source', 'source.json'), ('candidates', 'candidates.json'),
                          ('contexts', 'contexts.json'), ('invitation_context', 'invitation-context.json')]:
        write(directory / filename, case[key])
    write(Path(path) / 'plan-input.json', case['plan'])
    return load_plan(path, directory, case['plan'])


def claim(path, account):
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM queue WHERE account_id=? AND status='ready' ORDER BY id LIMIT 1", (account,)).fetchone()
        if row is None:
            db.commit()
            return None
        db.execute("UPDATE queue SET status='claimed' WHERE id=? AND status='ready'", (row["id"],))
        emit(db, "claimed", actor=account, job=row["id"], virtual_second=row["due_second"])
        db.commit()
        return row["id"]


def local_publish(path, job, account):
    """Persist a local receipt atomically; deliberately has no external transport."""
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM queue WHERE id=?", (job,)).fetchone()
        require(row is not None and row["account_id"] == account, "Account does not own this job.")
        previous = db.execute("SELECT * FROM local_posts WHERE job_id=?", (job,)).fetchone()
        if previous:
            db.commit()
            return dict(previous)
        require(row["status"] == "claimed", "Only a claimed job can enter the local outbox.")
        payload = json.loads(row["payload"])
        receipt = f"sim://{Path(path).name}/{job}"
        db.execute("INSERT INTO local_posts VALUES(?,?,?,?,?,?)", (job, receipt, account, payload["text"], payload["target"]["uri"], iso()))
        db.execute("UPDATE queue SET status='simulated_published' WHERE id=?", (job,))
        emit(db, "simulated_published", actor=account, job=job, virtual_second=row["due_second"] + 1,
             receipt=receipt, public_writes=0, transport="local SQLite only")
        result = dict(db.execute("SELECT * FROM local_posts WHERE job_id=?", (job,)).fetchone())
        db.commit()
        return result


def add_measurement(path, data):
    meta = active(path)
    kind = data.get("kind")
    require(kind in ("human_request", "human_response", "human_correction", "human_review", "usage", "note", "model_stage"), "Invalid measurement event.")
    detail = {k: v for k, v in data.items() if k not in ("kind", "at", "id", "actor", "job", "virtual_second")}
    if kind == 'model_stage':
        try:
            detail = workflow_record.model_stage(data, executor=meta.get('model_executor', 'codex'))
        except ValueError as exc:
            raise SimulationError(str(exc)) from None
    for key in ("cost_usd", "human_active_seconds", "input_tokens", "output_tokens"):
        if detail.get(key) is not None:
            v = detail[key]
            require(type(v) in (int, float) and math.isfinite(v) and v >= 0, "Invalid measurement number.")
    if detail.get("human_active_seconds") is not None:
        require(kind in ("human_response", "human_correction", "human_review")
                and detail.get("time_basis") in ("user_reported", "timed_editor_session"), "Human time needs a real basis.")
    if kind == "usage":
        require(detail.get("provider") and detail.get("measurement_source"), "Usage needs provider evidence.")
        require(all(detail.get(k) is None or type(detail[k]) is int for k in ("input_tokens", "output_tokens")), "Token counts must be integers.")
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        if kind == "human_response":
            events = status_events(db)
            requests = {e["seq"]: e for e in events if e["kind"] == "human_request"}
            rid = detail.get("request_id")
            require(rid in requests and not any(e["kind"] == "human_response" and e["detail"].get("request_id") == rid for e in events), "Unknown or answered request.")
            detail["waiting_seconds"] = round((now() - date(requests[rid]["at"])).total_seconds(), 3)
        seq = emit(db, kind, actor=detail.pop('actor', 'measurement'), **detail)
        db.commit()
    return seq


def status_events(db):
    return [{**dict(row), "detail": json.loads(row["detail"])} for row in db.execute("SELECT * FROM events ORDER BY seq")]


def status_data(path):
    with connect(path) as db:
        queue = [{**dict(row), "payload": json.loads(row["payload"])} for row in db.execute("SELECT * FROM queue ORDER BY id")]
        posts = [dict(row) for row in db.execute("SELECT * FROM local_posts ORDER BY job_id")]
        events = status_events(db)
    return {"queue": queue, "local_posts": posts, "coordination_log": events}


def run(path, usage_complete=False):
    clock = time.perf_counter()
    meta = active(path)
    plan = read(Path(path) / "plan.json")
    require(not any(e["kind"] == "execution_started" for e in status_data(path)["coordination_log"]),
            "An interrupted execution needs inspection; it is not restarted automatically.")
    with connect(path) as db:
        emit(db, "execution_started", workers=3, approval_kind="simulation rules, not human editorial approval")
    def worker(account):
        job = claim(path, account["id"])
        if job:
            return local_publish(path, job, account["id"])
        with connect(path) as db:
            emit(db, "account_idle", actor=account["id"], reason="no eligible task")
        return None
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="virtual-account") as pool:
        results = list(pool.map(worker, meta["accounts"]))
    published_ids = {p["job_id"] for p in results if p}
    synthetic = plan.get("synthetic_reactions", [])
    require(isinstance(synthetic, list), "Synthetic reactions must be an array.")
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        for item in synthetic:
            require(isinstance(item, dict) and item.get("job_id") in published_ids, "Synthetic reaction needs a locally published job.")
            require(item.get("kind") in ("like", "reply", "repost"), "Invalid synthetic reaction.")
            actor = item.get("actor", "")
            require(isinstance(actor, str) and (actor in {a["id"] for a in ACCOUNTS} or actor.startswith("synthetic:")), "Synthetic actor must be explicitly marked.")
            emit(db, "synthetic_reaction", actor=actor, job=item["job_id"], virtual_second=60,
                 reaction=item["kind"], origin="own_network" if actor.startswith("virtual:") else "synthetic_external",
                 is_observed_on_bluesky=False)
        emit(db, "observation_finished", actor="observer", virtual_second=60 if synthetic else 31,
             real_audience_observation="not performed", public_requests=0, public_writes=0)
        db.commit()
    finished = now()
    elapsed = round(time.perf_counter() - clock, 6)
    result = build_result(path, finished, elapsed, usage_complete)
    save_report(path, result)
    meta.update(status="completed", completed_at=finished.isoformat(timespec="milliseconds"))
    write(Path(path) / "run.json", meta)
    return result


def build_result(path, finished, execution_seconds, usage_complete=False):
    meta, data = read(Path(path) / "run.json"), status_data(path)
    plan = read(Path(path) / "plan.json")
    events = data["coordination_log"]
    usage = [e["detail"] for e in events if e["kind"] == "usage"]
    priced = [e["cost_usd"] for e in usage if e.get("cost_usd") is not None]
    cost_complete = usage_complete and bool(usage) and len(priced) == len(usage)
    timed = [e["detail"]["human_active_seconds"] for e in events if e["detail"].get("human_active_seconds") is not None]
    reactions = [e for e in events if e["kind"] == "synthetic_reaction"]
    external = [e for e in reactions if e["detail"]["origin"] == "synthetic_external"]
    queue, posts = data["queue"], data["local_posts"]
    research = read(Path(path) / "research.json")
    count = lambda status: sum(j["status"] == status for j in queue)
    profiles = [{'job_id': j['id'], 'account_id': j['account_id'],
                 'profile': j['payload']['psychological_profile'],
                 'baseline': j['payload']['baseline_draft_body'], 'adapted': j['payload']['draft_body'],
                 'trace': j['payload']['adaptation_trace']} for j in queue
                if j['active'] and j['payload'].get('psychological_profile')]
    invitations = [{'job_id': j['id'], 'account_id': j['account_id'], **j['payload']['participant_invitation']}
                   for j in queue if j['active'] and j['payload'].get('participant_invitation')]
    metrics = {"workflow_wall_seconds": round((finished - date(meta["started_at"])).total_seconds(), 3),
        "local_execution_seconds": execution_seconds,
        "assignment_elapsed_seconds": round((finished - date(meta["session_clock"]["task_started_at"])).total_seconds(), 3) if meta.get("session_clock") else None,
        "virtual_scenario_seconds": max((e["virtual_second"] for e in events), default=0),
        "simulated_posts": len(posts), "held_jobs": count("held"), "rejected_jobs": count("rejected"),
        "unique_target_authors": len({j["payload"]["target"]["author_did"] for j in queue if j["status"] == "simulated_published"}),
        "public_network_requests": 0, "public_writes": 0, "new_model_api_calls_by_simulator": 0,
        "actual_cost_usd": sum(priced) if cost_complete else None,
        "recorded_partial_cost_usd": sum(priced) if priced else None,
        "usage_coverage": "complete" if cost_complete else ("partial" if usage else "unavailable"),
        "human_interventions": sum(e["kind"] in ("human_request", "human_correction") for e in events),
        "human_editor_reviews": sum(e["kind"] == "human_review" for e in events),
        "pending_human_requests": sum(e["kind"] == "human_request" for e in events) - sum(e["kind"] == "human_response" for e in events),
        "human_active_seconds": sum(timed) if timed else None,
        "human_waiting_seconds": sum(e["detail"].get("waiting_seconds", 0) for e in events),
        "synthetic_reactions_total": len(reactions), "synthetic_own_network_reactions": len(reactions) - len(external),
        "synthetic_external_reactions": len(external), "synthetic_external_actors": len({e["actor"] for e in external}),
        "observed_real_audience_reactions": None, "observed_real_reach": None,
        "fictional_psychological_profiles": len(profiles),
        "real_psychological_profiles": sum(bool(x['used_profile_dimensions']) for x in invitations),
        "consented_participant_invitations": len(invitations)}
    metrics['discussion_profiles'] = len(research.get('discussion_profiles', {}))
    metrics['discussion_profiles_reply'] = sum(p['contribution']['decision'] == 'reply' for p in research.get('discussion_profiles', {}).values())
    metrics['discussion_profiles_skip'] = sum(p['contribution']['decision'] == 'skip' for p in research.get('discussion_profiles', {}).values())
    return {"mode": "offline-simulation", "publication_enabled": False, "public_writes": 0,
        "topic": meta["topic"], "started_at": meta["started_at"], "completed_at": finished.isoformat(timespec="milliseconds"),
        "accounts": meta["accounts"], **data, "measurements": metrics, "psychological_profiles": profiles,
        "participant_invitations": invitations,
        "discussion_profiles": research.get('discussion_profiles', {}),
        "discussion_profile_criterion": research.get('discussion_profile_criterion'),
        "revision_of": meta.get('revision_of'),
        "model_stages": [e for e in events if e['kind'] == 'model_stage'],
        "model_executor": meta.get('model_executor', 'codex'),
        "research_provenance": research["provenance"], "reference_source": research["source"],
        "limitations": plan.get("limitations", []) + [
            "Všechny publikace jsou místní sim:// záznamy, nikoli příspěvky na Bluesky.",
            "Návrhy dodal modelový agent nebo označený předpřipravený vzorek; samotný simulátor není jazykový model a neprovádí nové hledání.",
            "Čas scénáře je ilustrativní. Skutečný čas zpracování a čas přípravy jsou vykázány odděleně.",
            "Syntetické reakce jsou zadaná testovací data, nikoli naměřený účinek.",
            "Neznámá cena a aktivní lidský čas nejsou nula. Lidská redakční kontrola se započítá pouze při skutečném provedení.",
            "Původ rešerše je uložen s otisky souborů. Načtení zmrazených dat není nový průzkum Bluesky."]}


def save_report(path, result):
    path = Path(path)
    write(path / "report.json", result)
    write(path / "queue.json", result["queue"])
    write(path / "local-posts.json", result["local_posts"])
    write(path / 'discussion-profiles.json', {'version': 1, 'profiles': result.get('discussion_profiles', {})})
    (path / "coordination.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in result["coordination_log"]), encoding="utf-8")
    (path / "queue.csv").write_text(queue_csv(result["queue"]), encoding="utf-8")
    template = Path(__file__).resolve().parents[1] / "assets" / "virtual-report.html"
    payload = json.dumps(result, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    rows = "".join("<tr><td>" + html.escape(j["id"]) + "</td><td>" + html.escape(j["account_id"] or "—") + "</td><td>" + html.escape(j["status"]) + "</td><td>" + html.escape(j["payload"].get("text", j["reason"])) + "</td></tr>" for j in result["queue"])
    replacements = {"__REPORT_DATA__": payload, "__NOSCRIPT_QUEUE__": rows}
    document = re.sub("__REPORT_DATA__|__NOSCRIPT_QUEUE__", lambda m: replacements[m.group()], template.read_text(encoding="utf-8"))
    (path / "report.html").write_text(document, encoding="utf-8")


def queue_csv(queue):
    import csv
    import io
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["job", "account", "status", "target", "text", "reason"])
    for j in queue:
        cells = [j["id"], j["account_id"] or "", j["status"], j["payload"].get("target", {}).get("url", ""), j["payload"].get("text", ""), j["reason"]]
        writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in cells])
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("--topic", required=True)
    begin.add_argument("--output-root", default="output/virtual-amplifier")
    begin.add_argument("--session-log")
    begin.add_argument('--parent-run')
    begin.add_argument('--revision-reason')
    begin.add_argument('--executor', default='codex')
    for name in ("load", "check", "event", "run", "status", "invite"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run", required=True)
        if name in ("load", "check", "event"):
            cmd.add_argument("--input", required=True)
        if name in ("load", "check"):
            cmd.add_argument("--research", required=True)
        if name == "run":
            cmd.add_argument("--usage-complete", action="store_true")
        if name == 'invite':
            cmd.add_argument('--profile', required=True)
            cmd.add_argument('--posts', required=True)
            cmd.add_argument('--consent', required=True)
    args = parser.parse_args()
    if args.action == "start":
        print(json.dumps({"run_dir": str(start(args.topic, args.output_root, args.session_log,
                          parent_run=args.parent_run, revision_reason=args.revision_reason, executor=args.executor)), "public_writes": 0}))
    elif args.action == "load":
        value = load_plan(Path(args.run), args.research, read(args.input))
        print(json.dumps({"queue_items": len(value["queue"]), "ready": sum(j["status"] == "ready" for j in value["queue"]), "public_writes": 0}))
    elif args.action == 'check':
        _, _, checked = check_plan(Path(args.run), args.research, read(args.input))
        print(json.dumps({'formally_checked': len(checked), 'queue_modified': False,
                          'semantic_interpretation_verified': False, 'public_writes': 0,
                          'items': [{'candidate_id': item.get('candidate_id'), 'error': error} for item, error in checked]},
                         ensure_ascii=False))
    elif args.action == "event":
        print(json.dumps({"event_seq": add_measurement(Path(args.run), read(args.input))}))
    elif args.action == "status":
        print(json.dumps(status_data(Path(args.run)), ensure_ascii=False, indent=2))
    elif args.action == 'invite':
        value = prepare_invitation(Path(args.run), args.profile, args.posts, args.consent)
        print(json.dumps({'queue_items': len(value['queue']), 'ready': sum(j['status'] == 'ready' for j in value['queue']), 'public_writes': 0}))
    else:
        value = run(Path(args.run), args.usage_complete)
        print(json.dumps({"measurements": value["measurements"], "report": str((Path(args.run) / "report.html").resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (SimulationError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc), "public_writes": 0}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
