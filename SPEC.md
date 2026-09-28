# Share-a-Clicky: spec

## Problem
HeyClicky relaunched as Clickys on Sep 12, 2026. New users answer four questions and get three Clickys made for them, and New Clicky runs a short interview. Both start from what HeyClicky guesses about you. There is no way to start from a Clicky a friend already runs for a real job. The Skills library (about 100 community skills at launch in v1.0.33) was paused, with a plan to bring skills back in a new form. Invite & Earn (Sep 24) pays a sharer 25% of a friend's plan for up to 12 months and gives the friend 25% off their first month, so there's a reason to share; a shared Clicky gives the link something specific to carry.

## Bet
Let people share a Clicky that already does a real job. A friend starts from a Clicky someone they trust has set up, alongside HeyClicky's own suggestions, and the sharer's invite link rides along. Whether that improves activation and retention is the hypothesis to test (see Metrics).

## Users and jobs
| Who | Job |
|---|---|
| Sharer | Help me show a friend the exact Clicky that saves me time, and get credit for the invite |
| Receiver | Help me start with a Clicky that already works, without figuring out what to ask for |
| Existing user | Help me find a Clicky for a job I have, from inside HeyClicky |

## Scope (v0.1)
| Part | What it does |
|---|---|
| `data/clickys.source.json` | Single source of truth: sharers (with optional invite link) and shared Clickys (name, job, personality, instructions, routine, apps, messages per run, first task, example flag) |
| Share page (static site) | Gallery plus one page per Clicky, and a small link page per Clicky (`/c/<slug>/`) so a shared link previews that Clicky. Shows what it does, schedule, apps, monthly message estimate against Free and Pro (with a "Needs Pro" note above the Free limit), sharer, and an Example label where the sharer doesn't run it. "Copy setup" copies the paste-ready setup. "Get HeyClicky" uses the sharer's invite link when one is set, otherwise heyclicky.com |
| Local connector (`connector/local`) | MCP over stdio, zero dependencies, for "Command on this Mac" |
| Remote connector (`connector/worker`) | MCP over HTTP on Cloudflare Workers, for "Remote URL". Anyone can paste one URL to try it |
| Connector tools | `list_shared_clickys`, `get_shared_clicky(slug)` |

Out of scope: accounts, uploading your own Clicky, analytics, one-click install (needs a HeyClicky hook, see Known limits).

## Install flow (tested live on HeyClicky 1.0.52, Sep 28, 2026)
1. Receiver opens the share page and taps Copy setup.
2. In HeyClicky, taps + (New Clicky) and pastes.
3. HeyClicky creates the Clicky with the right job and first tasks (about 20 seconds in my test).
4. The new Clicky asks to connect the apps it needs; the receiver connects them and tells it to create its routine. (Creating the Clicky and turning on its routine are separate steps in HeyClicky.)
5. Inside any Clicky, the user can also say "show me shared Clickys" and the connector lists and returns setups.

## Acceptance checks
| # | Check | Pass when |
|---|---|---|
| A1 | Page renders the gallery from `clickys.json` | All Clickys listed, no console errors |
| A2 | Page renders one Clicky via `?c=slug` | Name, job, schedule, apps, message estimate, sharer shown |
| A3 | Unknown slug | Friendly "not found" with link back to gallery |
| A4 | Copy setup | Clipboard gets the exact setup text; button confirms; falls back to a selectable text box if clipboard is blocked |
| A5 | Phone width (390px) | No horizontal scroll, buttons tappable |
| A6 | Dark and light mode | Small text reaches 4.5:1 contrast in both (measured by the page test) |
| C1 | Connector `initialize`, `tools/list` | Valid MCP responses, echoes protocol version |
| C2 | `get_shared_clicky` with valid slug, any case or spaces | Returns setup text plus hand-off instruction |
| C3 | Unknown or empty slug | `isError: true`, lists available slugs |
| C4 | Unknown method / bad JSON | JSON-RPC error or ignored, server keeps running (including NaN, deep nesting, huge bodies) |
| C5 | Notifications | No reply (stdio) or 202 (HTTP) |
| C6 | Tool output tells the Clicky not to operate the HeyClicky app itself | Present in every setup response |
| C7 | Setup text and page text come from the same data | One generator; `build.py --check` fails on stale output |
| C8 | Python and Worker connectors behave the same | Parity test over normal and malformed messages |
| C9 | Protocol edge cases | Unsupported version in initialize falls back to 2025-06-18; an unsupported `MCP-Protocol-Version` header gets 400; batches are refused on 2025-06-18 and allowed on older versions; ids must be strings or integers; client responses get no reply (202 over HTTP); missing method is -32600; unknown tool is -32602; bodies over 64 KB (bytes) get 413 without being read in full |
| C10 | Tools are marked read-only | `readOnlyHint: true`, `destructiveHint: false` on both tools |
| L1 | Live: paste setup into New Clicky | Clicky created with correct job |
| L2 | Live: connector added in HeyClicky and a Clicky fetches a setup | Local passes on the first turn of a chat; remote must pass two turns in one chat |

## Known limits (found in live testing)
| Limit | Why | What HeyClicky could add |
|---|---|---|
| Install is one paste, not one click | Clickys have no tool to create another Clicky; when asked, a Clicky tried to drive HeyClicky's own UI and stalled | A `create_clicky` hook, or a heyclicky://new?setup= deep link |
| New Clicky screen can't use connectors | The creation interview doesn't call tools | Let creation read a shared setup |
| Local stdio connector only answers the first turn of each chat | HeyClicky 1.0.52 reports "Transport closed" on later turns without contacting the process | Keep the stdio session alive across turns, or respawn it |
| Routines can't run at a set weekday time | Scheduler supports intervals only | Weekday + time schedules |
| Message estimates are estimates | One agent message per routine run, for the routine alone; other chats and retries add more | Show real usage on shared Clickys |
| A shared setup is instructions for an agent that can reach your apps | Anyone could share a setup that asks for more than it says | Show the full text before install (the page does), list the apps and actions a setup touches, and review or verify shared Clickys |

## Metrics I'd watch if this shipped
Share page views to installs; installs to first routine run; 7-day retention of shared-Clicky installs vs Clickys made from HeyClicky's own onboarding; invite-link signups per shared Clicky; agent messages per installed Clicky vs plan limits.
