"""Tests for build.py and the local stdio connector. Run: python3 -m unittest discover tests"""
import copy
import json
import os
import subprocess
import sys
import unittest

os.environ["SHARE_A_CLICKY_LOG"] = "off"  # keep tests from writing connector.log

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "connector", "local"))

import build  # noqa: E402
import share_a_clicky_mcp as local  # noqa: E402

LOCAL_SERVER = os.path.join(ROOT, "connector", "local", "share_a_clicky_mcp.py")


def load_source():
    with open(build.SOURCE_PATH) as source_file:
        return json.load(source_file)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.source = load_source()
        self.data = build.build(self.source)

    def test_every_clicky_has_generated_fields(self):
        for clicky in self.data["clickys"]:
            for field in ("setup_text", "connector_response_text", "estimated_agent_messages_per_month"):
                self.assertIn(field, clicky)

    def test_setup_text_contains_every_key_part(self):
        for clicky in self.data["clickys"]:
            text = clicky["setup_text"]
            for part in (clicky["name"], clicky["personality"], clicky["instructions"],
                         clicky["routine"]["label"], clicky["first_task"]):
                self.assertIn(part, text)
            for app in clicky["apps"]:
                self.assertIn(app, text)

    def test_connector_text_contains_setup_and_handoff_rule(self):
        for clicky in self.data["clickys"]:
            text = clicky["connector_response_text"]
            self.assertTrue(text.startswith(clicky["setup_text"]))
            self.assertIn("you cannot create a new Clicky yourself", text)
            self.assertIn("Do not try to operate the HeyClicky app", text)
            self.assertIn("Click + (New Clicky) and paste this.", text)

    def test_message_estimate_math(self):
        job_hunter = next(c for c in self.data["clickys"] if c["slug"] == "job-hunter")
        self.assertEqual(job_hunter["estimated_agent_messages_per_month"], 30)
        self.assertEqual(job_hunter["share_of_plan_percent"]["free"], 120)
        self.assertEqual(job_hunter["share_of_plan_percent"]["pro"], 20)

    def test_all_generated_outputs_match_source(self):
        with open(build.SITE_DATA_PATH) as site_file:
            site_data = json.load(site_file)
        with open(build.LOCAL_DATA_PATH) as local_file:
            local_data = json.load(local_file)
        self.assertEqual(site_data, self.data, "docs/clickys.json is stale: run python3 build.py")
        self.assertEqual(local_data, self.data, "connector/local/clickys.json is stale: run python3 build.py")
        with open(build.WORKER_OUTPUT_PATH) as worker_file:
            worker_source = worker_file.read()
        self.assertIn(json.dumps(self.data, ensure_ascii=False), worker_source,
                      "worker.js is stale: run python3 build.py")

    def test_page_url_uses_site_url(self):
        source = copy.deepcopy(self.source)
        source["site_url"] = "https://example.github.io/share-a-clicky/"
        data = build.build(source)
        self.assertEqual(data["clickys"][0]["page_url"],
                         "https://example.github.io/share-a-clicky/c/" + data["clickys"][0]["slug"] + "/")
        self.assertIn("Share page: https://example.github.io", data["clickys"][0]["connector_response_text"])

    def test_share_link_pages_preview_each_clicky(self):
        outputs = build.generated_outputs(self.data)
        for clicky in self.data["clickys"]:
            page = outputs[os.path.join(build.SHARE_LINK_DIR, clicky["slug"], "index.html")]
            self.assertIn(f'<meta property="og:url" content="{clicky["page_url"]}">', page)
            self.assertIn(clicky["name"], page)
            self.assertIn("not affiliated with HeyClicky", page)
            self.assertIn(f'url=../../?c={clicky["slug"]}', page)

    def test_share_link_page_escapes_html(self):
        source = copy.deepcopy(self.source)
        source["clickys"][0]["name"] = 'Job "Hunter" <b>'
        data = build.build(source)
        page = build.render_share_link_page(data, data["clickys"][0])
        self.assertNotIn("<b>", page)
        self.assertIn("&lt;b&gt;", page)

    def test_connector_response_says_pro_and_next_steps(self):
        job_hunter = next(c for c in self.data["clickys"] if c["slug"] == "job-hunter")
        text = job_hunter["connector_response_text"]
        self.assertIn("more than the Free plan's 25, so it needs Pro", text)
        self.assertIn("tell the new Clicky to create its routine", text)
        weekly = next(c for c in self.data["clickys"] if c["slug"] == "weekly-wins")
        self.assertNotIn("needs Pro", weekly["connector_response_text"])

    def test_invite_link_used_when_sharer_has_one(self):
        source = copy.deepcopy(self.source)
        source["sharers"]["@mohit"]["invite_url"] = "https://www.heyclicky.com/@mohit"
        clicky = build.build(source)["clickys"][0]
        self.assertEqual(clicky["get_heyclicky_url"], "https://www.heyclicky.com/@mohit")
        self.assertIn("Get it with @mohit's invite: https://www.heyclicky.com/@mohit",
                      clicky["connector_response_text"])

    def test_without_invite_falls_back_and_claims_nothing(self):
        source = copy.deepcopy(self.source)
        source["sharers"]["@mohit"]["invite_url"] = ""
        clicky = build.build(source)["clickys"][0]
        self.assertEqual(clicky["get_heyclicky_url"], source["default_get_url"])
        self.assertNotIn("'s invite:", clicky["connector_response_text"])

    def test_check_mode_detects_stale_output(self):
        with open(build.SITE_DATA_PATH) as site_file:
            original = site_file.read()
        try:
            with open(build.SITE_DATA_PATH, "w") as site_file:
                site_file.write(original.replace("Job Hunter", "Job Huntr", 1))
            self.assertEqual(build.main(["--check"]), 1)
        finally:
            with open(build.SITE_DATA_PATH, "w") as site_file:
                site_file.write(original)
        self.assertEqual(build.main(["--check"]), 0)

    def test_validation_rejects_bad_input(self):
        cases = [
            ("duplicate slug", lambda s: s["clickys"].append(copy.deepcopy(s["clickys"][0]))),
            ("bad slug", lambda s: s["clickys"][0].update(slug="Job Hunter")),
            ("missing name", lambda s: s["clickys"][0].update(name="  ")),
            ("no apps", lambda s: s["clickys"][0].update(apps=[])),
            ("negative runs", lambda s: s["clickys"][0]["routine"].update(runs_per_month=-1)),
            ("zero per run", lambda s: s["clickys"][0].update(agent_messages_per_run=0)),
            ("no clickys", lambda s: s.update(clickys=[])),
            ("bad plan", lambda s: s["plans"].update(pro=0)),
            ("unknown sharer", lambda s: s["clickys"][0].update(shared_by="@nobody")),
            ("example not bool", lambda s: s["clickys"][0].update(example="yes")),
            ("http site url", lambda s: s.update(site_url="http://insecure.example")),
            ("bad invite url", lambda s: s["sharers"]["@mohit"].update(invite_url="javascript:alert(1)")),
        ]
        for label, mutate in cases:
            with self.subTest(label):
                source = copy.deepcopy(self.source)
                mutate(source)
                with self.assertRaises(build.ValidationError):
                    build.build(source)


class LocalHandlerTests(unittest.TestCase):
    def setUp(self):
        self.data = local.load_data()

    def call(self, name, arguments):
        response = local.handle_message(self.data, {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        result = response["result"]
        return result["content"][0]["text"], result["isError"]

    def test_initialize_echoes_protocol_version(self):
        response = local.handle_message(self.data, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(response["result"]["serverInfo"]["name"], "share-a-clicky")

    def test_initialize_without_version_uses_default(self):
        response = local.handle_message(self.data, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_unsupported_protocol_version_falls_back(self):
        for requested in ("1999-01-01", [], 5):
            response = local.handle_message(self.data, {
                "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": requested}})
            self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_notifications_get_no_reply(self):
        self.assertIsNone(local.handle_message(self.data, {"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_tools_list(self):
        response = local.handle_message(self.data, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["list_shared_clickys", "get_shared_clicky"])

    def test_get_accepts_slug_name_case_and_spaces(self):
        expected = next(c for c in self.data["clickys"] if c["slug"] == "job-hunter")["connector_response_text"]
        for value in ("job-hunter", "Job Hunter", "  JOB_HUNTER ", "job--hunter", "job\u2011hunter", "job\u2013hunter"):
            with self.subTest(value):
                text, is_error = self.call("get_shared_clicky", {"slug": value})
                self.assertFalse(is_error)
                self.assertEqual(text, expected)

    def test_get_unknown_or_empty(self):
        for arguments in ({"slug": "nope"}, {"slug": ""}, {}, {"slug": ["job-hunter"]}, {"slug": 0}):
            with self.subTest(arguments):
                text, is_error = self.call("get_shared_clicky", arguments)
                self.assertTrue(is_error)
                self.assertIn("Available ids: job-hunter", text)

    def test_malformed_arguments_are_invalid_params(self):
        for arguments in (None, ["x"], "job-hunter"):
            with self.subTest(arguments):
                response = local.handle_message(self.data, {
                    "jsonrpc": "2.0", "id": 7, "method": "tools/call",
                    "params": {"name": "get_shared_clicky", "arguments": arguments}})
                self.assertEqual(response["error"]["code"], -32602)

    def test_list(self):
        text, is_error = self.call("list_shared_clickys", {})
        self.assertFalse(is_error)
        for clicky in self.data["clickys"]:
            self.assertIn(clicky["slug"], text)

    def test_unknown_tool_missing_name_and_unknown_method(self):
        for params in ({"name": "delete_everything"}, {"name": ""}, {}):
            response = local.handle_message(self.data, {
                "jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": params})
            self.assertEqual(response["error"]["code"], -32602)
        response = local.handle_message(self.data, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_client_responses_are_not_answered(self):
        self.assertIsNone(local.handle_message(self.data, {"jsonrpc": "2.0", "id": 5, "result": {}}))
        self.assertIsNone(local.handle_message(self.data, {"jsonrpc": "2.0", "id": 5, "error": {"code": 1}}))

    def test_missing_method_is_invalid_request(self):
        response = local.handle_message(self.data, {"jsonrpc": "2.0", "id": 6})
        self.assertEqual(response["error"]["code"], -32600)
        self.assertEqual(response["id"], 6)

    def test_handler_crash_does_not_kill_process(self):
        original = local.handle_message
        local.handle_message = lambda data, message: 1 / 0
        try:
            response = local.safe_handle(self.data, {"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
            self.assertEqual(response["error"]["code"], -32603)
            self.assertIsNone(local.safe_handle(self.data, {"jsonrpc": "2.0", "method": "x"}))
        finally:
            local.handle_message = original

    def test_invalid_request_shape(self):
        response = local.handle_message(self.data, ["not", "an", "object"])
        self.assertEqual(response["error"]["code"], -32600)


class LocalProcessTests(unittest.TestCase):
    """Runs the real script over stdio, the way HeyClicky does."""

    def run_session(self, lines):
        completed = subprocess.run(
            [sys.executable, LOCAL_SERVER], input="\n".join(lines) + "\n",
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]

    def test_full_session_survives_bad_input(self):
        responses = self.run_session([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                   "clientInfo": {"name": "test", "version": "1"}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            "this is not json",
            "",
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "get_shared_clicky", "arguments": {"slug": "job-hunter"}}}),
            json.dumps({"jsonrpc": "2.0", "id": 4, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                        "params": {"name": "get_shared_clicky", "arguments": {"slug": "follow\u2011up\u2011keeper"}}},
                       ensure_ascii=False),
            json.dumps([{"jsonrpc": "2.0", "id": 6, "method": "ping"},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}]),
            json.dumps([]),
        ])
        self.assertEqual(len(responses), 8)
        batch_reply, empty_batch_reply = responses[6], responses[7]
        # 2025-06-18 removed JSON-RPC batching, so a batch after negotiating it is refused
        self.assertEqual(batch_reply["error"]["code"], -32600)
        self.assertIn("2025-06-18", batch_reply["error"]["message"])
        self.assertEqual(empty_batch_reply["error"]["code"], -32600)
        responses = responses[:6]
        self.assertEqual([r.get("id") for r in responses], [1, None, 2, 3, 4, 5])
        self.assertIn("Name: Follow-up Keeper", responses[5]["result"]["content"][0]["text"])
        self.assertEqual(responses[1]["error"]["code"], -32700)
        self.assertIn("Name: Job Hunter", responses[3]["result"]["content"][0]["text"])
        self.assertEqual(responses[4]["result"], {})

    def test_batch_allowed_on_older_protocol(self):
        responses = self.run_session([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2025-03-26"}}),
            json.dumps([{"jsonrpc": "2.0", "id": 6, "method": "ping"},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}]),
        ])
        self.assertEqual(responses[1], [{"jsonrpc": "2.0", "id": 6, "result": {}}])

    def test_hostile_input_never_kills_the_process(self):
        responses = self.run_session([
            "[" * 3000 + "]" * 3000,                           # deeper than Python's parser allows
            "[" * 100 + "]" * 100,                             # parseable, but deeper than MAX_NESTING
            "x" * (70 * 1024),                                 # over the 64 KB cap
            '{"jsonrpc":"2.0","id":NaN,"method":"ping"}',      # not valid JSON
            '{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":Infinity}}',
            json.dumps({"jsonrpc": "2.0", "id": None, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": True, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": 2 ** 60, "method": "ping"}),
            json.dumps({"jsonrpc": "2.0", "id": "last", "method": "ping"}),
        ])
        codes = [r.get("error", {}).get("code") for r in responses]
        self.assertEqual(codes, [-32700, -32700, -32600, -32700, -32700, -32600, -32600, -32600, None])
        self.assertTrue(all(r["id"] is None for r in responses[:-1]))
        self.assertEqual(responses[-1], {"jsonrpc": "2.0", "id": "last", "result": {}})

    def test_tools_are_marked_read_only(self):
        responses = self.run_session([json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})])
        for tool in responses[0]["result"]["tools"]:
            self.assertTrue(tool["annotations"]["readOnlyHint"])
            self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_logging_is_off_by_default(self):
        log_file = os.path.join(os.path.dirname(LOCAL_SERVER), "connector.log")
        env = {k: v for k, v in os.environ.items() if k != "SHARE_A_CLICKY_LOG"}
        subprocess.run([sys.executable, LOCAL_SERVER], input='{"jsonrpc":"2.0","id":1,"method":"ping"}\n',
                       capture_output=True, text=True, timeout=10, env=env)
        self.assertFalse(os.path.exists(log_file))

    def test_missing_data_file_fails_clearly(self):
        env = dict(os.environ)
        completed = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); import share_a_clicky_mcp as m; "
             "m.DATA_PATH='/nonexistent/clickys.json'; sys.exit(m.main())" % os.path.dirname(LOCAL_SERVER)],
            input="", capture_output=True, text=True, timeout=10, env=env,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("cannot read", completed.stderr)


if __name__ == "__main__":
    unittest.main()
