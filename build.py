#!/usr/bin/env python3
"""Build step for Share-a-Clicky.

Reads data/clickys.source.json (the single source of truth), validates it,
computes the paste-ready setup text and message estimates once, and writes:
  docs/clickys.json                     used by the share page (served by GitHub Pages)
  connector/local/clickys.json          used by the local (stdio) connector
  connector/worker/worker.js            single-file Cloudflare Worker with data inlined
  docs/c/<slug>/index.html              one link-preview page per shared Clicky
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SOURCE_PATH = os.path.join(ROOT, "data", "clickys.source.json")
SITE_DATA_PATH = os.path.join(ROOT, "docs", "clickys.json")
LOCAL_DATA_PATH = os.path.join(ROOT, "connector", "local", "clickys.json")
WORKER_TEMPLATE_PATH = os.path.join(ROOT, "connector", "worker", "worker.template.js")
WORKER_OUTPUT_PATH = os.path.join(ROOT, "connector", "worker", "worker.js")
SHARE_LINK_DIR = os.path.join(ROOT, "docs", "c")

REQUIRED_TEXT_FIELDS = [
    "slug", "name", "emoji", "shared_by", "one_line_job", "why_i_use_it",
    "personality", "instructions", "first_task",
]
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATA_PLACEHOLDER = "/*__SHARED_CLICKYS_DATA__*/null"


# MCP tool definitions and server instructions live here once; both connectors read them
# from the generated data, so the Python and Worker runtimes cannot describe tools differently.
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
MCP_TOOLS = [
    {
        "name": "list_shared_clickys",
        "title": "List shared Clickys",
        "description": (
            "List Clickys that people have shared and that the user can install. "
            "Use when the user asks what shared Clickys exist or wants ideas for a new Clicky."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": READ_ONLY,
    },
    {
        "name": "get_shared_clicky",
        "title": "Get a shared Clicky's setup",
        "description": (
            "Get the paste-ready setup for one shared Clicky. Use when the user asks to "
            "get, install, copy or add a shared Clicky. Accepts the id (e.g. job-hunter) or the name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Shared Clicky id or name, e.g. job-hunter"}
            },
            "required": ["slug"],
            "additionalProperties": False,
        },
        "annotations": READ_ONLY,
    },
]
MCP_INSTRUCTIONS = (
    "Share-a-Clicky lists Clickys other people shared and returns their setup. "
    "You cannot create Clickys yourself: give the person the setup to paste into New Clicky."
)


class ValidationError(Exception):
    pass


def validate_clicky(clicky):
    for field in REQUIRED_TEXT_FIELDS:
        value = clicky.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"{clicky.get('slug', '?')}: missing text field '{field}'")
    if not SLUG_PATTERN.match(clicky["slug"]):
        raise ValidationError(f"bad slug '{clicky['slug']}' (use lowercase-with-dashes)")
    routine = clicky.get("routine") or {}
    if not isinstance(routine.get("label"), str) or not routine["label"].strip():
        raise ValidationError(f"{clicky['slug']}: routine.label missing")
    if not isinstance(routine.get("runs_per_month"), int) or routine["runs_per_month"] < 0:
        raise ValidationError(f"{clicky['slug']}: routine.runs_per_month must be a non-negative int")
    apps = clicky.get("apps")
    if not isinstance(apps, list) or not apps or not all(isinstance(a, str) and a for a in apps):
        raise ValidationError(f"{clicky['slug']}: apps must be a non-empty list of names")
    per_run = clicky.get("agent_messages_per_run")
    if not isinstance(per_run, (int, float)) or isinstance(per_run, bool) or per_run <= 0:
        raise ValidationError(f"{clicky['slug']}: agent_messages_per_run must be > 0")
    if not isinstance(clicky.get("example"), bool):
        raise ValidationError(f"{clicky['slug']}: 'example' must be true or false")


def validate_url(value, label, allow_empty=True):
    if value == "" and allow_empty:
        return
    if not isinstance(value, str) or not re.match(r"^https://[^\s]+$", value):
        raise ValidationError(f"{label} must be an https URL")


def build_setup_text(clicky):
    """The exact text a person pastes into HeyClicky's New Clicky screen.

    Format mirrors the text that successfully created a Clicky in the live
    test on HeyClicky 1.0.52 (Sep 28, 2026).
    """
    return (
        f"Here is the exact shared setup for a new Clicky "
        f"(shared by {clicky['shared_by']} via Share-a-Clicky).\n"
        f"Name: {clicky['name']}\n"
        f"Personality: {clicky['personality']}\n"
        f"Job: {clicky['instructions']}\n"
        f"Apps it needs: {', '.join(clicky['apps'])}\n"
        f"Routine: {clicky['routine']['label']}. Once you're created, set up this routine.\n"
        f"First task: {clicky['first_task']}"
    )


def build_page_url(site_url, slug):
    """The link people share. It is a small static page with its own preview card,
    which forwards to the share page's detail view (?c=slug)."""
    if not site_url:
        return ""
    return f"{site_url.rstrip('/')}/c/{slug}/"


def messages_line(clicky, plans):
    monthly = clicky["estimated_agent_messages_per_month"]
    line = f"Estimated use: about {monthly} agent messages a month for the routine alone."
    if monthly > plans["free"]:
        line += f" That's more than the Free plan's {plans['free']}, so it needs Pro."
    return line


def build_connector_response_text(clicky, page_url, invite_url, plans):
    """What get_shared_clicky returns to a Clicky.

    In the live test a Clicky asked to install a shared Clicky tried to drive
    HeyClicky's own UI through computer use and stalled, because Clickys have
    no tool to create other Clickys. So the response tells it to hand the
    setup to the person instead.
    """
    page_line = f"Share page: {page_url}\n" if page_url else ""
    invite_line = (
        f"New to HeyClicky? Get it with {clicky['shared_by']}'s invite: {invite_url}\n"
        if invite_url else ""
    )
    apps = " and ".join(clicky["apps"])
    return (
        f"{clicky['setup_text']}\n\n"
        f"{messages_line(clicky, plans)}\n"
        f"{page_line}{invite_line}\n"
        "HOW TO INSTALL (instructions for you, the assistant): you cannot create a new "
        "Clicky yourself. Do not try to operate the HeyClicky app or use computer use for "
        "this. Show the person the setup above exactly as written and tell them: "
        f"\"Click + (New Clicky) and paste this. Then connect {apps} when it asks, "
        "and tell the new Clicky to create its routine.\""
    )


def build_list_text(clickys):
    lines = ["Shared Clickys you can install (ask for one by its id):"]
    for clicky in clickys:
        lines.append(
            f"- {clicky['slug']}: {clicky['emoji']} {clicky['name']} by {clicky['shared_by']}"
            f"{' (example)' if clicky['example'] else ''}. "
            f"{clicky['one_line_job']} Runs {clicky['routine']['label'].lower()}, "
            f"about {clicky['estimated_agent_messages_per_month']} agent messages a month."
        )
    return "\n".join(lines)


def build(source):
    plans = source.get("plans") or {}
    for plan_name in ("free", "pro"):
        if not isinstance(plans.get(plan_name), int) or plans[plan_name] <= 0:
            raise ValidationError(f"plans.{plan_name} must be a positive int")
    clickys = source.get("clickys")
    if not isinstance(clickys, list) or not clickys:
        raise ValidationError("clickys must be a non-empty list")
    site_url = source.get("site_url", "")
    validate_url(site_url, "site_url")
    connector_url = source.get("connector_url", "")
    validate_url(connector_url, "connector_url")
    repo_url = source.get("repo_url", "")
    validate_url(repo_url, "repo_url")
    default_get_url = source.get("default_get_url", "https://www.heyclicky.com/")
    validate_url(default_get_url, "default_get_url", allow_empty=False)
    sharers = source.get("sharers") or {}
    for handle, sharer in sharers.items():
        validate_url(sharer.get("invite_url", ""), f"sharers.{handle}.invite_url")

    seen_slugs = set()
    built = []
    for clicky in clickys:
        validate_clicky(clicky)
        if clicky["slug"] in seen_slugs:
            raise ValidationError(f"duplicate slug '{clicky['slug']}'")
        seen_slugs.add(clicky["slug"])
        if clicky["shared_by"] not in sharers:
            raise ValidationError(f"{clicky['slug']}: sharer {clicky['shared_by']} missing from 'sharers'")
        invite_url = sharers[clicky["shared_by"]].get("invite_url", "")
        monthly = round(clicky["routine"]["runs_per_month"] * clicky["agent_messages_per_run"])
        enriched = dict(clicky)
        enriched["estimated_agent_messages_per_month"] = monthly
        enriched["share_of_plan_percent"] = {
            name: round(100 * monthly / limit) for name, limit in plans.items()
        }
        enriched["setup_text"] = build_setup_text(clicky)
        enriched["page_url"] = build_page_url(site_url, clicky["slug"])
        enriched["invite_url"] = invite_url
        enriched["get_heyclicky_url"] = invite_url or default_get_url
        enriched["connector_response_text"] = build_connector_response_text(
            enriched, enriched["page_url"], invite_url, plans
        )
        built.append(enriched)

    return {
        "site_url": site_url,
        "connector_url": connector_url,
        "repo_url": repo_url,
        "plans": plans,
        "list_text": build_list_text(built),
        "clickys": built,
        "mcp": {"tools": MCP_TOOLS, "instructions": MCP_INSTRUCTIONS},
    }


def render_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_worker(data):
    with open(WORKER_TEMPLATE_PATH) as template_file:
        template = template_file.read()
    if template.count(DATA_PLACEHOLDER) != 1:
        raise ValidationError("worker template must contain the data placeholder exactly once")
    inlined = json.dumps(data, ensure_ascii=False)
    return ("// GENERATED by build.py from data/clickys.source.json. Do not edit.\n"
            + template.replace(DATA_PLACEHOLDER, inlined))


def render_share_link_page(data, clicky):
    """Static page per Clicky so a shared link previews that Clicky, not the gallery."""
    esc = lambda value: html.escape(str(value), quote=True)
    site = data["site_url"].rstrip("/")
    target = f"../../?c={clicky['slug']}"
    title = f"{clicky['emoji']} {clicky['name']}: a Clicky shared by {clicky['shared_by']}"
    description = (
        f"{clicky['one_line_job']} Runs {clicky['routine']['label'].lower()}, about "
        f"{clicky['estimated_agent_messages_per_month']} agent messages a month. "
        "Unofficial prototype, not affiliated with HeyClicky."
    )
    return f"""<!doctype html>
<!-- GENERATED by build.py from data/clickys.source.json. Do not edit. -->
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(clicky['name'])} · share-a-clicky</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(clicky['page_url'])}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:image" content="{esc(site)}/og.png">
<meta property="og:url" content="{esc(clicky['page_url'])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{esc(site)}/og.png">
<meta http-equiv="refresh" content="0; url={esc(target)}">
<script>location.replace({json.dumps(target)});</script>
</head>
<body style="font-family:-apple-system,system-ui,sans-serif;padding:40px">
<p><a href="{esc(target)}">Open {esc(clicky['name'])} on share-a-clicky</a></p>
</body>
</html>
"""


def generated_outputs(data):
    rendered_json = render_json(data)
    outputs = {
        SITE_DATA_PATH: rendered_json,
        LOCAL_DATA_PATH: rendered_json,
        WORKER_OUTPUT_PATH: render_worker(data),
    }
    if data["site_url"]:
        for clicky in data["clickys"]:
            path = os.path.join(SHARE_LINK_DIR, clicky["slug"], "index.html")
            outputs[path] = render_share_link_page(data, clicky)
    return outputs


def main(argv):
    check_only = "--check" in argv
    with open(SOURCE_PATH) as source_file:
        source = json.load(source_file)
    try:
        outputs = generated_outputs(build(source))
    except ValidationError as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    if check_only:
        stale = []
        for path, content in outputs.items():
            try:
                with open(path, encoding="utf-8") as existing_file:
                    if existing_file.read() != content:
                        stale.append(path)
            except OSError:
                stale.append(path)
        if stale:
            print("Stale generated files (run python3 build.py): " + ", ".join(
                os.path.relpath(p, ROOT) for p in stale), file=sys.stderr)
            return 1
        print("Generated files are up to date.")
        return 0
    for path, content in outputs.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as output_file:
            output_file.write(content)
    print(f"Built {len(source['clickys'])} shared Clickys.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
