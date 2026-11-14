# Agent layer: tools and skills

Source: Alexey's «Инструменты и навыки» (map 4 of 8, checked 13 November 2026; star counts, versions and catalogue sizes change weekly, so they are mostly left out). How to give the agent hands: SDKs for your own MCP servers, gateways and registries, code sandboxes, browser work, skills, ready integrations with authorisation. Why the layer exists is in `../base.md` (layer 04, mechanism M11, shifts N1–N3). **The most dangerous part of the harness: here the agent gets the ability to change things.**

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **A tool description is a prompt.** The model reads tool descriptions as instructions. A server can hide a command in a description (*tool poisoning*) or swap the description after your approval (*rug pull*). A check of 1 899 MCP servers found poisoned descriptions in 5.5%.
- **Three ways to give an action.** A function in the agent's code: simple, only for that agent. An MCP server: written once, every agent and editor can connect. Code in a sandbox: the model writes a script that calls the tools itself. The choice depends on the number of tools and who else will use them.
- **A skill is not a tool.** A tool performs an action; a skill explains how to do a task and loads on demand. A foreign skill is a foreign prompt plus foreign code: a Snyk audit found critical issues in 13.4% of skills in open catalogues, and researchers bypassed catalogue scanners in under an hour.

## Rule 0

Any foreign MCP server, skill or package is untrusted code with your agent's rights. Pin versions, hash tool descriptions and review them when they change. **Start with one to three of your own narrow read-only tools.** Run agent-written code only in a sandbox, by default **without network and without secrets**.

## Classes and technologies

### MCPBUILD — writing your own MCP servers
MCP became the common way to connect tools: one server works with any agent and editor. The summer 2026 spec removed sessions at the protocol level, and the official SDKs broke compatibility in v2 for it. Production bar now: **Streamable HTTP and OAuth 2.1 authorisation**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Official SDKs** | open (MIT / Apache 2.0) · base | reference implementations: tier-one TypeScript, Python, C#, Go, Rust, Ruby; v2 for spec 2026-07-28; Streamable HTTP and stdio; low-level protocol control; new spec features land in TS and Python first; **v1 → v2 needs code changes** (sessionless API) | full control over transport and auth; languages other than Python (TS, Go, C#, Rust) | a quick Python start (FastMCP is shorter) |
| **FastMCP** | open (Apache 2.0) · pop | Prefect; Python framework on the official Python SDK v2; tool schema inferred from the function signature and types; auth, proxy, build from OpenAPI, tests; LangChain's MCP support stands on it; the community de-facto standard for Python. Not the old SDK module of the same name, nor the separate TS `fastmcp` | own MCP server to an internal system in an evening; a Python team | needing fine protocol control |
| **FastAPI-MCP** | open (MIT) · pop | turns an existing FastAPI app into an MCP server without code, reuses FastAPI dependencies for auth. **Main risk: exposing the whole API as is — a hundred endpoints become a hundred tools the model drowns in.** Pick what the agent needs by hand | a FastAPI backend that needs a quick demo | a large API without endpoint selection |
| **mcp-go and the official Go SDK** | open (MIT) · pop | mcp-go (community) is a year older and more widespread; the official SDK (maintained with Google) has support guarantees and tier one — for a new service take the official one | a server as one binary without a runtime; infrastructure tools | a team writing Python or TypeScript |
| **Tool design** | open (technique) · base | name and description say what it does and when to call it in one or two sentences; strict input schema with enums instead of free strings; short output, an error says what to fix; **designed for the agent's task, not the API endpoint** ("find a master's free slots" instead of three schedule calls); long output cut in the tool; write actions separated from reads and marked as needing confirmation | any own tool | no case where it is redundant |

### GATEWAY — MCP gateways and registries
A gateway sits between agents and MCP servers: one point for auth, rights, limits and the call log. A registry only lists servers and does not sit in the call path. **A gateway is needed when there are more than a few servers or a team uses them.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **agentgateway** | open (Apache 2.0) · grow | Linux Foundation project, handed over by Solo.io; Rust single binary / Kubernetes proxy for MCP, A2A and models; OAuth, CEL policies, per-key budgets, guardrail hooks; ~0.4 ms per call in an independent test — the fastest open one in an autumn 2026 comparison. **Same test: in the default setup it served all tools to anyone who reached the port — enable auth immediately** | a fast gateway with policy as code; Kubernetes and Envoy already there | needing ready teams, a catalogue and an admin UI |
| **ContextForge** | open (Apache 2.0) · pop | IBM; Python, Docker, Kubernetes; MCP servers, A2A agents, REST and gRPC behind one point (translates REST/gRPC to MCP); teams, SSO, dozens of plugins, admin UI, limits; denies without a token and blocks servers on private addresses by default; ~47 ms per call and 847 MB idle in the same test — you pay with weight and setup | many teams and servers needing one catalogue; old REST services to show agents as tools | critical latency; a small team (too much configuration) |
| **Docker MCP Gateway** | open (MIT) · pop | Docker plugin and runtime; **a container per server** with network and resource limits; Docker MCP Catalog with signed images; secrets injected by the gateway; removes the risk of running a foreign server via `npx` on the host; remote servers only over HTTPS | a developer machine and a test stand; foreign servers you do not want on the host | multi-user production with roles and audit |
| **Obot** | open (MIT, open core) · grow | platform on Docker, Kubernetes, cloud; runs servers itself (not only proxies), a catalogue for staff, a gateway, a chat client, SSO; solves "give staff a vetted tool list" | an internal company catalogue of approved servers | needing only a thin proxy |
| **Official MCP Registry** | open (open project) · grow | preview; stores metadata only; **does no security checks** (leaves them to package registries and aggregators); does not accept private servers and suggests running your own registry. Being listed says nothing about safety | finding which servers exist | a source of trust; a catalogue of internal servers |

### SANDBOX — code sandboxes
An isolated environment where model-written code runs. They differ by isolation boundary: *microVM* with its own kernel, *gVisor* with a user-space kernel, or a hardened container. Second question: is state kept between calls and how long does wake-up take.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **E2B** | open (Apache 2.0) · pop | cloud with open runtime and SDK; a Firecracker microVM per sandbox; per-sandbox egress firewall; pause and resume (~0.7 s in a test); the most examples and integrations; session length limited by plan; no GPU inside | data analysis and running agent code; an open base with the option to self-host | needing a GPU; sessions longer than a day |
| **Daytona** | src (open repository archived) · pop | cloud, enterprise install; containers by default — **weaker isolation than microVM**; starts in tens of ms from a warm pool; state persists with configurable retention; turned to AI code execution in 2025; per autumn 2026 the open repo is archived — self-hosting only in the enterprise version | an agent needing a work environment that lives between runs; start speed | running known-hostile code; needing an open licence |
| **Modal Sandboxes** | prop (SaaS) · pop | cloud, gVisor, **GPU inside** (the only large option with it), Python-first SDK; slower start than E2B and Daytona; high parallelism | agent code that trains or runs models; high parallelism | self-hosting; a TypeScript team |
| **Vercel Sandbox** | prop (SaaS) · grow | Firecracker microVM next to a Vercel app, own network policies, TS-first SDK; designed for minutes and hours, not days | AI features in a Next.js app | long sessions; Python as the main language |
| **Code execution in the model API** | prop (API) · pop | built-in tool at Anthropic and OpenAI: a container for the request or session, nothing to deploy; programmatic tool calling and skills run on the same mechanism. **Data put into that container is at the provider** | calculations and charts on small data; a quick start without infrastructure | client data that cannot leave; code that must reach internal systems |
| **Own isolation** | open (technique) · base | Firecracker, gVisor, Kata or bubblewrap on your own server; microVM, gVisor or kernel namespaces; **network closed by default, egress through your own proxy; secrets never inside — actions go through tools outside**; the main work is the boundaries: what is visible from the sandbox, where it may go, what happens to it after the task; on NixOS the sandbox environment can be declarative and reproducible. The only option when neither code nor data may leave your network | client data in your own jurisdiction; isolation experience and own hardware | a small team without operations experience |

### BROWSER — browser and screen
Needed when a system has no API. **A last resort, not a first:** a browser agent is slower, costlier and more fragile than an ordinary tool. Two approaches: via the page accessibility tree (fast and precise) or via screenshots (universal but expensive).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Playwright MCP** | open (Apache 2.0) · base | Microsoft MCP server; Chromium, Firefox, WebKit; sees the page as an accessibility tree, no screenshots; local, no keys; a pure tool layer with no agent logic; for coding agents Microsoft also pushes Playwright CLI, several times fewer tokens than the MCP variant | filling a form, walking a scenario on a site; testing your own UI | sites with hard bot protection; hundreds of parallel sessions |
| **Chrome DevTools MCP** | open (Apache 2.0) · pop | Chrome team; Chrome only; console, network, performance traces of a live tab; built for debugging | an agent debugging a frontend; page performance analysis | automating actions on other people's sites |
| **browser-use** | open (MIT) · pop | Python library and cloud; the model observes the page and decides what to do; isolated browser, real Chrome profile or cloud; give a goal, it walks several pages itself; flexible but **less predictable than a scenario with explicit steps** | one-off multi-step tasks on unfamiliar sites | a repeatable business process that needs stability |
| **Stagehand** | open (MIT) · pop | TypeScript SDK; Playwright with three AI commands `act`, `extract`, `observe`; pairs with Browserbase; rigid steps in code, fragile spots ("click the checkout button") to the model | repeatable data extraction and scenarios; a TypeScript team | a Python stack |
| **Browserbase** | prop (SaaS) · pop | cloud browsers for agents: managed sessions, recording, parallelism, proxies; driven by Stagehand, Playwright or own MCP server. **Everything the agent sees on the page passes through a foreign cloud** | many parallel and night runs | logging into systems with client data |
| **Computer use** | prop (API) · grow | Anthropic and OpenAI API tool; looks at screenshots, moves the mouse; works with any application; the most universal and most expensive (a screenshot and a model call per step); **the whole screen goes to the model provider** | an old desktop app without an API or web version | anything doable with a tool or Playwright |

### SKILLS — skills
A folder with `SKILL.md`, scripts and references. Only a short description sits in the context permanently; the rest loads when the task matches. In 2026 the format became common to dozens of agents, and open catalogues grew to hundreds of thousands of skills — **a new supply chain**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **SKILL.md format** | open (open standard) · base | folder format; name and description in the frontmatter are mandatory; instructions, scripts, reference files; read by Claude Code, Codex, Copilot, Cursor and dozens more. **The frontmatter description decides whether the skill fires:** too generic never fires, too broad fires in the wrong place; one skill = one repeatable procedure | company regulations and procedures for an agent; moving knowledge between different agents | a one-off task (the skill will not pay off) |
| **Own skill catalogue** | open (technique) · base | company skills in your own git repo with review and pinned versions; **a foreign skill is never linked to a mutable branch — read it, copy it in whole, update only through review** (same logic as pinning dependencies by hash); revoke = delete from the repo, gone for everyone | any company where more than one person uses agents | no case where it is redundant |
| **skills.sh** | prop (public catalogue) · pop | Vercel; catalogue and `npx skills` installer; hundreds of thousands of skills; automatic audits by Gen, Socket and Snyk since February 2026; no moderation at publish, ranking by installs; flagged-malicious ones hidden, installer shows a risk level — **but scanners disagree by multiples and install counters get inflated** | finding an idea and a base for your own skill | installing into a working agent without reading the code |
| **Skill scanners** | open (various) · grow | Cisco Skill Scanner, Snyk's scanner, catalogue-built-in ones; look for injections, secret theft, hidden downloads. **In June 2026 Trail of Bits bypassed every public scanner in under an hour** (padding that triggers truncation, logic in binary files, injection into the scanner's judge model) — useful as a first filter, useless as admission | weeding out the obviously bad at the entrance | being the only check before installation |
| **OWASP Agentic Skills Top 10** | open (open project) · grow | risk reference AST01–AST10; first risks: malicious skills, excessive permissions; measures: content signing, registry scanning, a least-privilege manifest, inventory of what is installed; a ready base for an internal policy (what skills are allowed, who approves, how to revoke) | writing the company's rules for working with skills | replacing your own review |

### CONNECT — ready integrations with authorisation
Platforms that take the dullest part: per-user OAuth, storing and refreshing tokens, hundreds of ready SaaS connectors. Needed for customer products where the agent acts on behalf of different people in their own accounts. Market overviews are mostly written by the market participants themselves.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Nango** | src (Elastic License) · pop | server and cloud; hundreds of APIs; per-user OAuth, own tools in code, data sync, webhooks, MCP server; code-first — you write tools and syncs over ready auth; **self-hostable, so client tokens do not go to a third party** | a customer product integrating into users' accounts; tokens that must stay with you | needing ready-made without code |
| **Composio** | prop (SaaS) · pop | cloud; 500+ apps; managed OAuth, ready tool descriptions, MCP gateway, triggers; shortest path to "the agent works with the user's mail, calendar and CRM"; basic execution logs | a quick prototype with many SaaS at once | client tokens and data that cannot go to an intermediary; fine-tuning tools |
| **Arcade** | prop (SaaS) · grow | cloud, self-hosting for large clients; **rights checked at call time on behalf of a specific person** (did this user delegate this action), not just token storage; ~100 own integrations; no data sync or webhooks | regulated industries where per-user rights separation matters | rare integrations; data sync for search |
| **Pipedream Connect** | prop (SaaS) · pop | cloud, ~3 000 apps, owned by Workday since December 2025; grew from an automation platform — stronger in internal processes than customer products | internal automation with rare services | a customer product with strict data requirements |
| **Own thin MCP servers** | open (technique) · base | own code on FastMCP or the official SDK, 3–5 tools per system; a narrow service account or the user's token; **local CRMs, accounting systems, banks and marketplaces are usually missing from Western catalogues** — a server with a few tools takes a day or two and stays under your control | the client's internal and local systems; data that must not pass through an intermediary | dozens of popular SaaS at once (a platform is cheaper) |

## Clouds

Cloud browsers, sandboxes and integration catalogues see everything that passes through them. **For Kazakhstan client data, MCP servers to internal systems and sandboxes stay in-house; external services only for de-identified tasks.**

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | AI Studio MCP Hub | connects ready MCP servers and helps create your own | tools for AI Studio agents |
| | Serverless Containers / Cloud Functions | hosting own MCP servers | a thin server to an internal system |
| | Compute Cloud | VMs — **no managed sandbox found**, build it yourself | own sandbox |
| DigitalOcean | App Platform | containers; no ready sandbox or MCP gateway service | own MCP servers and gateway |
| | Functions | functions as agent tools (Gradient agents call them) | simple actions |
| | Droplet | VMs | own sandbox |
| Railway | service from Docker | MCP servers and open gateways as plain services; **no code sandbox** — use an external one or a separate server | quick start |
| | private network | agent ↔ servers without going outside | internal tools |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | AgentCore Gateway (APIs and Lambda functions as MCP tools with auth); AgentCore Code Interpreter (sandbox); AgentCore Browser (managed browser); AgentCore Identity (agent credentials, access on behalf of a user) |
| Google Cloud | Cloud Run for MCP servers; code execution in Agent Runtime (ADK agents); Apigee as an API and tool gateway where it already exists |
| Azure | 1 000+ Logic Apps connectors for Foundry agents; Microsoft MCP Gateway (open, for Kubernetes/AKS); Container Apps dynamic sessions (code sandbox in your Azure) |
| Cloudflare | remote MCP servers on Workers with OAuth; Sandbox SDK (isolated containers, short execution — not for agents needing saved state after a pause); Browser Rendering |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Give the agent access to your CRM | own FastMCP server: 3–5 narrow tools | backend already on FastAPI → FastAPI-MCP with hand-picked endpoints |
| The client's local and internal systems | own thin MCP servers | — |
| Agent acts in different users' accounts | Nango self-hosted | speed over control → Composio; strict per-call rights → Arcade |
| Many MCP servers | agentgateway with auth enabled | catalogue, teams and SSO → ContextForge or Obot |
| A foreign MCP server on a developer machine | Docker MCP Gateway | — |
| Agent must run code | E2B | GPU needed → Modal; data cannot leave → own isolation |
| A calculation or chart on small data | code execution in the model API | sensitive data → own sandbox |
| System has no API, has a website | Playwright MCP | many parallel runs and non-sensitive data → Browserbase |
| Autonomous task on unfamiliar sites | browser-use (Python) or Stagehand (TypeScript) | — |
| An old desktop application | computer use | — |
| Company regulations for the agent | own skills in own git catalogue | — |
| Want a skill from an open catalogue | read the code, copy it in, pin the version | a scanner as a first filter, not as admission |
| More than a couple of dozen tools | tool search and programmatic tool calling | split across subagents with narrow tool sets |
| Customer data in Kazakhstan | MCP servers and sandbox in-house | external browsers and catalogues only for de-identified tasks |
