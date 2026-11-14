# Agent layer: frameworks and the agent loop

Source: Alexey's «Карта каркасов агента» (map 1 of 8; library versions from npm/PyPI on 17 October 2026, the rest checked 12 November 2026). What to write the agent itself with: provider SDKs, independent libraries, durable-execution engines, low-code builders, managed runtimes. Why each harness layer exists is in `../base.md` (layer 05, agent loop). **Frameworks change fast — re-check this file every few months.**

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **Library, engine, runtime are three different things.** The library describes the agent's logic. The durability engine records every step so a run survives a crash. The runtime is where the agent lives: a process, a sandbox, a session. They often come from different vendors.
- **Checkpoint and step replay.** After a crash the agent resumes from the last saved step and **re-runs the interrupted step**. So everything that changes the outside world (a record, a payment, an email) must be safe to repeat (idempotency key, mechanism M11 in `../base.md`).
- **The framework is an attack surface.** Black Hat 2026 showed 12 CVEs in four popular frameworks with one shared cause: untrusted text reached memory, serialisation or code execution. An agent that reads external text and runs code in the same process is dangerous with any framework.

## Rule 0

Start with your own loop or the thinnest library. Take a heavy framework only when you hit a concrete need: pauses for approval, a branching process, several agents. Keep state in your own database. Pin versions and keep them updated: the framework holds keys and runs tools.

## Classes and technologies

### VENDOR — model-provider SDKs
Libraries from the companies that make the models and clouds. Plus: they use "their" model deepest and get new features first (skills, compaction, tool search). Minus: lock-in — a fallback model from another vendor is harder.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Claude Agent SDK** | src (Commercial Terms) · pop | the Claude Code loop as a library (Python 0.2.168, TS 0.3.302); Claude only (Anthropic API, Bedrock, Vertex, Foundry); sessions continue / resume / fork; tool permissions and hooks; ships the whole harness: file and shell tools, subagents, skills, MCP, compaction, hooks; own tools as in-process MCP servers. **Runs the Claude Code binary underneath — it becomes part of your deploy** | an agent working with files and commands; starting without writing a loop; skills and subagents out of the box | a fallback model from another vendor; a light website chatbot (the runtime is heavy); a project that needs a strictly open licence |
| **OpenAI Agents SDK** | open (MIT) · pop | Python 0.24.0, JS 0.20.0; OpenAI by default, others through adapters (beta); four primitives: agent, handoff (pass the conversation to another agent), input/output guardrails, built-in tracing; voice via Realtime; serialisable `RunState`, `needs_approval` on a tool. **Does not save a turn on crash by itself** — plug Temporal, DBOS, Restate or Dapr | a customer chat with handoffs between roles; voice agents; a stack already on OpenAI | long tasks without an external durability engine; a non-OpenAI model as the main one (adapters are beta) |
| **Google ADK** | open (Apache 2.0) · pop | Python 2.12.0, TS 2.3.0, Go, Java, Kotlin; tuned for Gemini, others via `BaseLlm`; Session and State services; `require_confirmation`, long-running tools; agent hierarchy, Sequential / Parallel / Loop, graph workflows since 2.0 (May 2026), built-in evals, live voice and video; A2A experimental; deploys to Agent Runtime, Cloud Run, GKE | Google Cloud and Gemini; Java or Go teams; voice and video agents | outside Google Cloud half the convenience is lost; A2A in production (still an experiment); some third-party integrations do not work with graphs |
| **Microsoft Agent Framework** | open (MIT) · pop | successor of Semantic Kernel and AutoGen, 1.0 since April 2026 (Python 1.22.0); .NET, Python, Go (preview); Foundry, Azure OpenAI, OpenAI, Anthropic, Bedrock, Gemini, Ollama; checkpoints at step boundaries; `request_info`, `approval_mode` on tools; stable APIs and long support; sequential, parallel, handoff, group chat, Magentic-One, A2A, MCP. AutoGen is now community-maintained without new features; its fork AG2 lives separately | .NET and Azure; enterprise needing long support; complex multi-agent schemes | a small Python project (heavy); Go (preview only) |
| **Strands Agents** | open (Apache 2.0) · grow | AWS SDK, Python and TS; Bedrock and other providers; sessions, in production usually with AgentCore; "model leads": minimum scaffolding, the agent plans its own tool calls; native SDK of Bedrock AgentCore | AWS and Bedrock; simple agents without a rigid scheme | strictly deterministic processes; a young community with few examples |

### FRAME — independent libraries
Not tied to one provider, so a fallback model and your own gateway fit naturally. They differ in how much they decide for you: from "here is a loop and types" to "here is a graph, memory and a studio".

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Own loop on the bare API** | own code · base | about 100 lines: while not done — call the model, parse the tool request, run it, return the result; any model, best through your own gateway; state in your own Postgres table; your own "needs approval" flag on a tool; compaction and memory are API parameters now. Much of the criticism of frameworks boils down to "this takes an evening" | one agent with a couple of tools; full control and minimum dependencies; understanding the mechanics before picking a framework | several agents and complex branching; needing ready pause/resume and a debugging UI |
| **LangGraph** | open (MIT) · base | Python 1.2.16, JS 1.5.1; a state graph mixing plain code and LLM steps; nodes, edges, shared state; checkpointers (Postgres, SQLite, Redis) after every step; `interrupt()` and resume; `create_agent` (LangChain) and Deep Agents (planning, subagents, files) on top. **After `interrupt` the node restarts from the beginning — side effects must be idempotent.** 2026: an SQL injection + unsafe deserialisation chain in checkpointers, CVE-2026-44843 in langchain-core — keep versions fresh | processes where rigid steps alternate with LLM steps; pauses for human approval; the largest community and number of examples | a simple agent (overkill); a team tired of constant churn in the LangChain ecosystem |
| **Pydantic AI** | open (MIT) · pop | Python 3.11+, 2.57.0 (V2 line since June 2026); "FastAPI feel"; any model by `provider:model`; types on input, output and dependencies — the model's answer is validated by schema and **sent back to the model to fix on error**; no own checkpointer, nine external engines (Temporal, DBOS, Restate, Prefect…); deferred tools `requires_approval`; MCP client and server, OTel GenAI traces, Pydantic Evals and Graph in the same repo | a Python backend with strict data structures; one or two well-typed steps around a model; free choice of durability engine | TypeScript; durability out of the box without an external engine |
| **Mastra** | open (Apache 2.0 + Enterprise) · grow | TypeScript 1.78.0; agents, deterministic workflows, memory, evals and a local Studio in one package; model router by `provider/model`; `suspend()` with a snapshot in libSQL, Postgres, Upstash; resume with a response schema. Durable agents are beta — the docs recommend workflows for known steps; part of the features under an enterprise licence (open core) | TypeScript teams; a product where agents and normal processes live together | Python; critical durability of long agents (beta) |
| **Vercel AI SDK** | open (Apache 2.0) · base | TypeScript 7.0.x (AI SDK 7 since June 2026); streaming into the UI, one access to providers, tool calls; `ToolLoopAgent` in memory, `WorkflowAgent` survives restarts; `needsApproval` on a tool. **`stream()` has no default step limit — set `stopWhen` yourself** | a chat in a Next.js or React product; a quick TypeScript start; switching provider in one line | a Python backend; complex orchestration of several agents |
| **LlamaIndex** | open (MIT) · base | Python (TS version exists), core 0.14.25; strength is source connectors, indexes and query engines; agents on Workflows and AgentWorkflow; checks inside Workflows (retrieval is in `knowledge.md`) | an agent whose main work is documents; many different data sources | an agent with almost no documents (dead weight) |
| **CrewAI** | open (MIT) · pop | Python 3.10–3.13, 1.15.28; a Crew is a group of agents with roles and tasks, a Flow controls around them; models by `provider/model`, the rest via LiteLLM; `@persist` (SQLite by default), `@human_feedback`; fastest way to a multi-agent demo. **2026: CERT/CC VU#221883 — a chain of four CVEs takes a prompt injection to code execution on the host through Code Interpreter in the default setup** | a multi-agent prototype in a day; research tasks with roles | an agent that reads external text and has Code Interpreter; several workers on SQLite; a customer-facing production without hard isolation |
| **Agno** | open (Apache 2.0) · grow | ex-Phidata; pure Python, FastAPI runtime AgentOS; 20+ providers; sessions and memory in your DB; tool confirmation; no graphs or chains — agent, team, workflow; many tools, multimodal; less production harness than LangGraph | multimodal agents; many light concurrent agents | complex processes with pauses; conservative enterprise |
| **smolagents** | open (Apache 2.0) · pop | Hugging Face, Python 1.26.0 (May 2026); any model incl. local; CodeAgent — the agent's action is a piece of code run in a sandbox; minimal abstractions, readable in an hour; no built-in durability, few production features | research and prototypes; local models | production under load; running code without isolation |

### DURABLE — durable execution
Engines that record every step. After a crash, a deploy or a three-day wait for approval the agent continues from the same point. By 2026 a mandatory part: almost every framework either built in checkpoints or plugs into one of these. The class overview is in `architecture-guide` → `layers/background.md`.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Temporal** | open (MIT) · base | server + SDKs (Go, Java, Python, TS, .NET); Postgres, MySQL or Cassandra; with OpenAI Agents SDK (GA since March 2026), Pydantic AI; workflow = deterministic code, activity = step with a side effect (model or tool call); event history replays a run. **Heavy to operate: a multi-service cluster**; own cluster or Temporal Cloud | many teams and processes in one company; long approvals and waits | one small project (overkill); a team with no cluster operations experience |
| **DBOS** | open (MIT) · grow | library for Python and TS; checkpoints in **your own Postgres**, no separate server; decorators on functions; with Pydantic AI, OpenAI Agents SDK, Vercel AI SDK (since July 2026); DBOSify (July 2026) replaces Temporal Python over Postgres; free self-hosted, cloud exists | a project that already has Postgres; durability without a new service in the infrastructure | hundreds of workers and complex task routing; languages other than Python and TS |
| **Restate** | src (BSL 1.1) · grow | one binary with a built-in journal; SDKs TS, Python, Java, Go, Rust; with Vercel AI SDK, OpenAI Agents SDK, Google ADK, Pydantic AI, LangChain; model and tool calls wrapped in `ctx.run()`; virtual objects give per-session state without a database; self-hosted or Restate Cloud | durable agents without a big cluster; state per user | strict open-licence requirements |
| **Inngest** | src (SSPL) · pop | service + SDKs TS, Python, Go; a function split into `step.run()`, each step remembered; good on serverless; one 2026 price comparison calls it **costly for agents — too many steps per run**; cloud with a free tier, self-hostable | TypeScript on serverless; event-driven processes | agents with dozens of steps per run (watch the bill) |
| **Trigger.dev** | open (Apache 2.0) · pop | platform + TS SDK on Postgres; background and AI jobs without time limits, queues, retries, a clear runs dashboard; cloud or self-hosted; works with Vercel AI SDK and any TS library | Next.js and TypeScript backends; needing a visible runs dashboard | Python |

### LOWCODE — visual builders
The agent is built from blocks in an editor. For a client often the most understandable option: they edit the prompt and see the process. 2026: **Flowise was archived in August — do not start new projects on it.** Unauthenticated code execution was found in the Langflow and Flowise editors, so **an editor is never exposed to the internet**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Dify** | src (Apache 2.0 + conditions) · pop | platform on Docker Compose / Helm; any model; agent nodes, RAG, prompt management, data labelling; Dify Cloud; the most "ready" builder — an agent with a knowledge base immediately gets a chat and an API. **Licence forbids reselling as a multi-tenant service and removing the logo without a contract**; needs more memory than n8n | an internal assistant with a knowledge base in a week; prompts edited by non-programmers | selling it to clients as your own SaaS (licence); complex access-rights logic |
| **n8n** | src (Sustainable Use) · base | Docker; hundreds of integrations (CRM, mail, sheets, messengers), an AI Agent node, triggers; the agent is one node of a process; SSO and environments only on paid plans; licence allows internal use, not resale as a service; n8n Cloud | a background process "email arrives → parse → put into CRM"; a client who wants to edit processes themselves | a customer chat under load; selling under your own brand |
| **Langflow** | open (MIT) · pop | pip / Docker; components editable in Python; owned by IBM via DataStax; managed Astra version closed in April 2026 (self-hosted only); **CVE-2026-48519: unauthenticated code execution in the editor** | retrieval and agent prototypes for Python teams; needing an MIT licence | an editor reachable from the internet; needing a managed service |

### RUNTIME — managed runtimes from model vendors
The model provider holds the loop, the sandbox and the session state. Cloud equivalents (AWS, Google, Microsoft, Cloudflare) are under Clouds. **Not for data that cannot leave the country.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Claude Managed Agents** | prop (SaaS) · grow | launched April 2026; Claude models; the agent is a configuration, Anthropic holds the loop, sandbox and session state; $0.08 per session hour plus tokens | launching an agent quickly without own infrastructure | data that cannot leave the country; a model from another vendor |
| **OpenAI AgentKit** | prop (SaaS) · pop | Agent Builder, ChatKit, evals; shortest path from a prompt to a chat in a product, with a built-in eval-and-improve loop; no fully managed runtime for arbitrary code — you run Agents SDK yourself | a chat in a product on the OpenAI stack | data in your own jurisdiction; another model provider |

## Clouds

Cloud runtimes are convenient, but the agent's memory and traces end up with the provider. Yandex Cloud has a Kazakhstan region, but which AI Studio services are available **in it** was not confirmed — check before choosing. The other six clouds have no Kazakhstan region as far as known.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | AI Studio: Agent Atelier | no-code text and voice agents. Per a Habr review, Atelier agents have **no deploy API and no LLM tracing** | a simple agent, a quick demo for a client |
| | Responses API / Realtime API | agent APIs for text and voice, OpenAI-compatible — OpenAI SDK, LangChain, LangGraph connect by changing the base URL | own code on OpenAI SDK or LangGraph |
| | MCP Hub | connect and create MCP servers | tools over your own APIs |
| | Workflows | process builder with agents | deterministic pipelines |
| DigitalOcean | Gradient AI ADK (public preview) | deploys your Python agent in one command, exposes HTTP `/run` | a Python agent without own infrastructure |
| | Gradient AI Platform | agents, knowledge bases, evals, serverless models | a quick agent with retrieval |
| | App Platform / Droplet | containers and VPS | any framework next to Managed Postgres |
| Railway | service from Docker or GitHub | no agent service of its own; a long-running process — LangGraph or DBOS checkpoints go into the same Postgres | agent and worker |
| | Postgres / Redis | state and queues | checkpoints and sessions |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Bedrock AgentCore — parts taken together or one by one: Runtime (a microVM per session), Memory, Gateway, Identity, Observability; accepts any framework, native SDK is Strands; Step Functions / Lambda Durable Functions for durable steps |
| Google Cloud | Gemini Enterprise Agent Platform (Vertex AI renamed in April 2026; Agent Engine is now Agent Runtime); Sessions and Memory Bank; native SDK is ADK; Cloud Run for any framework |
| Azure | Foundry Agent Service (the runtime itself is free — you pay for tokens and tool calls); hosted agents accept Agent Framework and LangGraph in an isolated session; identity via Entra ID; Durable Task for long processes |
| Cloudflare | Agents SDK — an agent is a Durable Object with its own state, Workflows for long steps, preview of the next SDK (Project Think) for long multi-step tasks; needs Wrangler and the Workers model; Workers AI / AI Gateway in the same network |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| First agent with one to three tools | own loop or Pydantic AI | TypeScript → Vercel AI SDK |
| Internal assistant with a knowledge base, fast | Dify self-hosted | code and control needed → Pydantic AI or LangGraph |
| Customer chat with booking | Pydantic AI or OpenAI Agents SDK through own gateway | Next.js web → Vercel AI SDK |
| Simple background processing of requests | n8n with an AI node | complex logic → LangGraph with checkpoints in Postgres |
| Agent must not lose its turn on a crash | DBOS if Postgres is already there | many teams → Temporal; a light server → Restate |
| Rigid steps mixed with LLM steps | LangGraph | TypeScript → Mastra workflow |
| Agent works with files and commands | Claude Agent SDK in a sandbox | another model → own loop + sandbox from `tools.md` |
| Several agents | one agent first; then LangGraph or Agent Framework | prototype → CrewAI in isolation |
| .NET and Azure | Microsoft Agent Framework | — |
| Google Cloud, voice and video | Google ADK | — |
| Customer data in Kazakhstan | own code and own gateway, hosted by the client or a local provider | only masked text leaves → any runtime fits |
| Leaving Flowise | Dify or Langflow | processes with integrations → n8n |
| Leaving AutoGen | Microsoft Agent Framework | want to stay on the same API → AG2 |
