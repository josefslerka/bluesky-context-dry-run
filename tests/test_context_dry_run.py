"""Meaningful invariants for the new Codex workflow. No live network or model calls."""
import copy
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/bluesky-context-dry-run/scripts"))
import bluesky_dry_run as dry
from discussion_fixture import profile_for


class Response(io.BytesIO):
    status = 200


def post(key, text, age=1):
    return {"uri": "at://did:plc:fixture/"+dry.POST+"/"+key, "cid": "fixture-cid-"+key,
            "author": {"did": "did:plc:fixture", "handle": "technical.example"},
            "record": {"text": text, "createdAt": dry.iso(dry.now()-dt.timedelta(days=age))},
            "replyCount": 0}


class FakeOpener:
    def __init__(self, source_url):
        self.calls = []
        self.changed = False
        self.paginate = False
        self.posts = [post("alpha", "Facial recognition needs supplier audits."),
                      post("beta", "Facial recognition investment is hard to trace."),
                      post("old", "Facial recognition in an old discussion.", 40)]
        duplicate = post("duplicate", "Facial recognition report, already shared.")
        duplicate["record"]["embed"] = {"external": {"uri": source_url+"?utm_source=test"}}
        self.posts.append(duplicate)

    def open(self, request, timeout):
        self.calls.append(request)
        if request.get_method() != "GET" or request.has_header("Authorization"):
            raise AssertionError("Only anonymous GET is permitted")
        parsed = urllib.parse.urlsplit(request.full_url)
        endpoint = parsed.path.rsplit("/", 1)[-1]
        query = urllib.parse.parse_qs(parsed.query)
        if endpoint == "app.bsky.feed.searchPosts":
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        if endpoint == "app.bsky.feed.getAuthorFeed":
            result = {"feed": [{"post": copy.deepcopy(p)} for p in self.posts]}
            if self.paginate and "cursor" not in query:
                result["cursor"] = "more"
        elif endpoint == "app.bsky.feed.getPosts":
            keys = {u.rsplit("/", 1)[-1] for u in query["uris"]}
            result = {"posts": [copy.deepcopy(p) for p in self.posts if p["uri"].rsplit("/", 1)[-1] in keys]}
        elif endpoint == "app.bsky.feed.getPostThread":
            item = copy.deepcopy(next(p for p in self.posts if p["uri"] == query["uri"][0]))
            if self.changed:
                item["cid"] = "edited-cid"
            result = {"thread": {"post": item, "replies": []}}
        else:
            raise AssertionError(endpoint)
        return Response(json.dumps(result).encode())


class ContextWorkflowTests(unittest.TestCase):
    def test_topic_without_url_collects_and_finishes_with_context_evidence_only(self):
        path = dry.start(None, self.tmp.name, topic='Supplier accountability')
        run = dry.Run(path)
        pool = dry.collect(run, self.discovery, dry.PublicReader(run, self.opener))['candidates']
        dry.fetch_contexts(run, [p['id'] for p in pool], dry.PublicReader(run, self.opener))
        self.profile_contexts(run, pool)
        assessment = self.assessment(pool, run)
        for d in assessment['decisions']:
            d['source_evidence'] = []
        result = dry.finalize(run, assessment)
        self.assertIsNone(result['source']['attachment_url'])
        self.assertEqual(result['source']['text_kind'], 'topic_brief')
        self.assertTrue(all(d['reply']['link_mode'] == 'none' and 'Source' not in d['reply']['text'] for d in result['decisions']))
        self.assertEqual(result['public_writes'], 0)

    def test_no_url_mode_still_enforces_the_post_length_limit(self):
        with self.assertRaises(dry.RunError):
            dry.render_reply('x' * 300)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.url = "https://publisher.example/story"
        self.path = dry.start(self.url, self.tmp.name)
        self.run = dry.Run(self.path)
        dry.capture_source(self.run, {"url": self.url, "title": "Supplier report", "language": "cs",
            "text_kind": "full_text", "paragraphs": ["The fund invested in Vendor Q. The amount was not disclosed."], "caveats": []})
        self.opener = FakeOpener(self.url)
        self.reader = dry.PublicReader(self.run, self.opener)
        self.discovery = {"keywords": ["facial recognition"], "bsky_queries": ["facial", "recognition"],
            "actors": [{"handle": "technical.example", "provenance_url": "https://bsky.app/profile/technical.example"}], "post_urls": []}

    def prepare(self):
        pool = dry.collect(self.run, self.discovery, self.reader)["candidates"]
        dry.fetch_contexts(self.run, [p["id"] for p in pool], self.reader)
        self.profile_contexts(self.run, pool)
        return pool

    def profile_contexts(self, run, pool):
        contexts, source = dry.read(run.path / 'contexts.json'), dry.read(run.path / 'source.json')
        dry.capture_discussion_profiles(run, {'profiles': [profile_for(p, contexts[p['id']], source) for p in pool]})

    def assessment(self, pool, run=None):
        run = run or self.run
        path = run.path / 'discussion-profiles.json'
        profiles = dry.read(path)['profiles'] if path.exists() else {}
        return {"summary": "Two contextual drafts prepared.", "limitations": ["Fixture experiment."],
                "decisions": [{"candidate_id": p["id"], "decision": "select", "relation": "comparative",
                    'discussion_profile_id': profiles.get(p['id'], {}).get('profile_id'),
                    "reason": "Adds an investor example to this discussion.", "context_connection": p["text"],
                    "added_information": "Amounts were not disclosed.", "language": "en",
                    "draft_body": "A supplier example for "+p["id"]+": the investment amount was not disclosed.",
                    "source_evidence": [{"paragraph_id": "S001", "quote": "The amount was not disclosed."}],
                    "context_evidence": [{"post_uri": p["uri"], "quote": p["text"]}], "limitations": []} for p in pool]}

    def test_complete_get_only_flow_with_search_fallback_and_unknown_cost(self):
        pool = self.prepare()
        self.assertEqual(len(pool), 2)  # Old post and existing source share are excluded.
        self.assertEqual(sum("searchPosts" in r.full_url for r in self.opener.calls), 1)
        result = dry.finalize(self.run, self.assessment(pool))
        self.assertEqual(result["selected_count"], 2)
        self.assertEqual(result["public_writes"], 0)
        self.assertIsNone(result["measurements"]["actual_cost_usd"])
        self.assertIsNone(result["measurements"]["human_active_seconds"])
        self.assertTrue(all(r.get_method() == "GET" for r in self.opener.calls))
        self.assertTrue((self.path / "report.html").is_file())

    def test_write_endpoint_refused_before_network(self):
        with self.assertRaisesRegex(dry.RunError, "allowlist"):
            self.reader.get("com.atproto.repo.createRecord", text="No")
        self.assertEqual(self.opener.calls, [])

    def test_bad_evidence_blocks_final_report(self):
        pool = self.prepare()
        a = self.assessment(pool)
        a["decisions"][0]["source_evidence"][0]["quote"] = "The investment was definitely one billion."
        with self.assertRaisesRegex(dry.RunError, "Source evidence"):
            dry.finalize(self.run, a)
        self.assertFalse((self.path / "report.json").exists())
        self.assertEqual(dry.read(self.path / "run.json")["status"], "running")

    def test_changed_post_cannot_be_selected(self):
        pool = dry.collect(self.run, self.discovery, self.reader)["candidates"]
        self.opener.changed = True
        contexts = dry.fetch_contexts(self.run, [p["id"] for p in pool], self.reader)
        self.assertTrue(all(not c["valid"] for c in contexts.values()))
        with self.assertRaisesRegex(dry.RunError, "unchanged context"):
            dry.finalize(self.run, self.assessment(pool))

    def test_thread_root_deduplication(self):
        reply = post("reply", "Facial recognition in the same thread.", 0)
        reply["record"]["reply"] = {"root": {"uri": self.opener.posts[0]["uri"]}}
        self.opener.posts.append(reply)
        pool = dry.collect(self.run, self.discovery, self.reader)["candidates"]
        self.assertEqual(len(pool), 2)
        self.assertEqual(len({p["root_uri"] for p in pool}), 2)

    def test_reply_discovery_loads_root_and_allows_only_verified_reply_targets(self):
        reply = post('deepreply', 'Facial recognition deserves a supplier discussion.', 0)
        root = self.opener.posts[0]
        reply['record']['reply'] = {'root': {'uri': root['uri']}, 'parent': {'uri': root['uri']}}
        self.opener.posts.append(reply)
        pool = dry.collect(self.run, self.discovery, self.reader)['candidates']
        candidate = next(p for p in pool if p['root_uri'] == root['uri'])
        self.assertEqual(candidate['uri'], reply['uri'])
        contexts = dry.fetch_contexts(self.run, [candidate['id']], self.reader)
        self.assertIn(root['uri'], {p['uri'] for p in contexts[candidate['id']]['posts']})
        self.profile_contexts(self.run, [candidate])
        assessment = self.assessment([candidate])
        assessment['decisions'][0]['reply_to_uri'] = root['uri']
        checked = dry.validate_assessment(self.run, assessment)
        self.assertEqual(checked[0]['reply_target']['uri'], root['uri'])
        assessment['decisions'][0]['reply_to_uri'] = 'at://did:plc:unread/'+dry.POST+'/invented'
        with self.assertRaisesRegex(dry.RunError, 'Reply target'):
            dry.validate_assessment(self.run, assessment)

    def test_bluesky_source_read_is_public_and_resolved_uri_blocks_alias_duplicates(self):
        value = 'https://bsky.app/profile/technical.example/post/alpha'
        source = dry.read_source_post(self.run, value, self.reader)
        self.assertEqual(source['post']['uri'], self.opener.posts[0]['uri'])
        self.assertTrue(all(r.get_method() == 'GET' for r in self.opener.calls))
        p = dry.normalize(self.opener.posts[0])
        self.assertTrue(dry.duplicate_source(p, {'url': self.url, 'attachment_url': value, 'post_uri': p['uri']}))

    def test_each_thread_requires_its_own_wording(self):
        pool = self.prepare()
        a = self.assessment(pool)
        a["decisions"][1]["draft_body"] = a["decisions"][0]["draft_body"]
        with self.assertRaisesRegex(dry.RunError, "distinct"):
            dry.validate_assessment(self.run, a)

    def test_long_url_kept_with_correct_utf8_facet(self):
        url = "https://publisher.example/" + "x"*400
        reply = dry.render_reply("Příliš žluťoučký 🐦: nový výzkum.", url)
        self.assertEqual(reply["link_mode"], "rich_link")
        facet = reply["facets"][0]
        raw = reply["text"].encode()
        self.assertEqual(raw[facet["index"]["byteStart"]:facet["index"]["byteEnd"]].decode(), "Source")
        self.assertEqual(facet["features"][0]["uri"], url)
        self.assertLessEqual(len(reply["text"]), 300)
        with self.assertRaises(dry.RunError):
            dry.render_reply("x"*301, url)

    def test_waiting_is_not_active_human_time(self):
        begin = dry.now()
        with patch.object(dry, "now", return_value=begin):
            request = dry.add_event(self.run, {"kind": "human_request", "reason": "A missing input"})
        with patch.object(dry, "now", return_value=begin+dt.timedelta(seconds=12)):
            dry.add_event(self.run, {"kind": "human_response", "request_id": request["id"], "detail": "Answered"})
        m = dry.measures(self.run)
        self.assertEqual(m["human_interventions"], 1)
        self.assertGreaterEqual(m["human_waiting_seconds"], 12)
        self.assertIsNone(m["human_active_seconds"])
        with self.assertRaises(dry.RunError):
            dry.add_event(self.run, {"kind": "human_review", "human_active_seconds": 12})

    def test_partial_cost_is_not_total_cost_and_zero_can_be_real(self):
        dry.add_event(self.run, {"kind": "usage", "provider": "fixture", "measurement_source": "test billing response", "cost_usd": 0, "input_tokens": 12})
        self.assertIsNone(dry.measures(self.run)["actual_cost_usd"])
        self.assertEqual(dry.measures(self.run)["recorded_partial_cost_usd"], 0)
        self.assertEqual(dry.measures(self.run, True)["actual_cost_usd"], 0)
        with self.assertRaises(dry.RunError):
            dry.add_event(self.run, {"kind": "usage", "provider": "fixture", "measurement_source": "test", "cost_usd": float('nan')})

    def test_budget_stops_network_but_can_report_empty_result(self):
        self.run.meta["started_at"] = dry.iso(dry.now()-dt.timedelta(seconds=901))
        result = dry.collect(self.run, self.discovery, self.reader)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["warnings"])
        self.assertEqual(self.opener.calls, [])
        report = dry.finalize(self.run, {"summary": "Budget reached.", "decisions": [], "limitations": []})
        self.assertGreater(report["overrun_seconds"], 0)

    def test_source_unavailable_is_not_reported_as_no_relevant_threads(self):
        path = dry.start("https://publisher.example/unavailable", self.tmp.name)
        run = dry.Run(path)
        dry.capture_source(run, {"url": "https://publisher.example/unavailable", "title": "Unavailable", "language": "und", "text_kind": "unavailable", "paragraphs": [], "caveats": ["Source could not be read."]})
        result = dry.collect(run, {}, dry.PublicReader(run, self.opener))
        self.assertEqual(result["candidates"], [])
        self.assertEqual(self.opener.calls, [])
        report = dry.finalize(run, {"summary": "Source unavailable.", "decisions": [], "limitations": []})
        self.assertEqual(report["status"], "source_unavailable")

    def test_report_escapes_source_and_draft_markup_and_run_is_immutable(self):
        pool = self.prepare()
        a = self.assessment(pool)
        a["decisions"][0]["draft_body"] = "<script>alert(1)</script> Here is a factual case."
        dry.finalize(self.run, a)
        document = (self.path / "report.html").read_text()
        self.assertNotIn("<script>", document)
        self.assertIn("&lt;script&gt;", document)
        with self.assertRaisesRegex(dry.RunError, "immutable"):
            dry.add_event(self.run, {"kind": "note", "detail": "Change sealed run"})

    def test_first_pages_from_all_seed_accounts_precede_pagination(self):
        self.opener.paginate = True
        self.discovery["actors"].append({"handle": "second.example", "provenance_url": "https://bsky.app/profile/second.example"})
        dry.collect(self.run, self.discovery, self.reader)
        feeds = [urllib.parse.parse_qs(urllib.parse.urlsplit(r.full_url).query) for r in self.opener.calls if "getAuthorFeed" in r.full_url]
        self.assertEqual([q["actor"][0] for q in feeds[:2]], ["technical.example", "second.example"])
        self.assertNotIn("cursor", feeds[0])
        self.assertNotIn("cursor", feeds[1])


if __name__ == "__main__":
    unittest.main()
