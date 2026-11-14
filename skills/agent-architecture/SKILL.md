---
name: agent-architecture
description: Use when a system includes an AI agent or LLM feature and you are designing, choosing components for, or critiquing its harness - nine layers (instructions, knowledge, memory, tools, agent loop, rights, guardrails, handoff, observation), thirteen mechanisms, a per-layer decision (needed? → choice → why → rejected) across frameworks, knowledge base, memory, tools and skills, model gateway, protection, channels and handoff, evaluation, with the rule of two, Kazakhstan data rules and supply-chain red flags.
---

# Agent architecture

Alexey's business-agent base and his eight harness maps (November 2026) in one place. The orchestrator uses it at the architecture stage when the system has an AI agent, an LLM feature or an assistant; `architect-critic` uses it to check the agent part of a draft. It sits next to `architecture-guide`: that skill decides the services and infrastructure (including inference and MLOps in `layers/ai.md`), this one decides the harness around the model. Load only the reference files the decision needs.

## Contents

1. [When to use](#when-to-use) · 2. [Precedence](#precedence) · 3. [Procedure](#procedure) · 4. [Decision record](#decision-record) · 5. [Layers](#layers) · 6. [Data and clouds](#data-and-clouds) · 7. [Red flags](#red-flags-checked-14-november-2026) · 8. [Reference files](#reference-files)

## When to use

- Stage 2 (architecture) of a project with an agent: a staff assistant, a customer chat or voice bot, a background agent that triages requests, a RAG search, any LLM call in the product.
- Reviewing the agent part of a draft architecture (`architect-critic`).
- A question like "do we need a framework / a vector database / long-term memory / a multi-agent scheme / a semantic cache here?".

Not for model serving, GPUs and MLOps — that is `architecture-guide` → `layers/ai.md`; not for the code of the agent — that is the stack rules and `rules/layers.md`.

## Precedence

1. The user's explicit request.
2. Project rules (`AGENTS.md`, `CLAUDE.md`, existing `docs/`).
3. House rules: `architecture-guide` → `references/architecture.md` (`04`), skills `stack-choice`, `auth-service`, `sops`.
4. This skill's defaults (`references/base.md`, `references/layers/*.md`).
5. `architecture-guide` → `layers/ai.md` defaults for the parts both cover — the agent maps are newer (13–14 November vs 30 October 2026).

Known overlaps:

| Topic | Elsewhere | Here | Do |
|---|---|---|---|
| Model gateway default | `ai.md`: LiteLLM with pinned versions | `gateway.md`: Bifrost first; LiteLLM only for many rare providers, pinned by hash — its releases were replaced with credential stealers in **March and October** 2026 | this skill; an existing LiteLLM stays if pinned by hash and isolated from unrelated secrets |
| Who the agent acts for | house `auth` service, RS256/ES256 JWT via JWKS | `guardrails.md`: agent as actor, user as subject, purpose, minutes-long expiry | the house `auth` service issues the delegation token; the agent never gets a user's full role |
| Provider keys, tool credentials | SOPS in git, a manager at runtime (`sops`, `access.md`) | keys outside the agent: the gateway injects them | both: SOPS for storage, injection at the gateway, nothing in the agent's env, prompt or memory |
| Durable agent runs | Python background jobs: Celery + Redis | `frameworks.md` DURABLE: DBOS on the project's Postgres, Temporal for many teams | Celery for ordinary jobs and reminders; a durability engine only for multi-step agent runs that must survive a crash or wait for approval |
| Agent traces | OTel, RED metrics, JSON logs (`observability.md`) | `evals.md`: OTel GenAI/OpenInference through own collector, Langfuse | the same OTel Collector carries both; the agent part adds the masking processor and the five agent metrics |
| Vectors | `databases.md`: Postgres first | `knowledge.md`: pgvector + full text + reranker | same answer; a separate vector DB only after a measurement |

## Procedure

0. **Facts first.** Who the agent serves (staff, clients, nobody — background), channels, request volume and peaks, languages (Russian, Kazakh, mixed), which systems it must read and which it must change, what is irreversible (money, deletion, external sending), sensitivity and residency (KZ/RU), whether operators exist and their hours, budget per request or per month, who edits the prompts. Unknown facts are ❓ questions, not guesses.
1. **Is an agent needed at all?** A fixed form, a rule or a plain LLM call with a schema beats an agent loop when the steps are known. An agent only when the next step depends on what was found.
2. **Type and shape.** Classify each agent as staff / client / background and read its column in `references/base.md` → *Three agent types*: that says which layers cannot be saved on. **One agent first**; several agents only when the task really splits (context isolation via subagents is fine, multi-agent for fashion is an objection).
3. **Rule of two per agent.** Write down which of (A) untrusted input, (B) private data or systems, (C) changes state or sends out it has. All three → a human confirms, or the design removes one (action selector, plan-then-execute, dual LLM, closed egress — `layers/guardrails.md` ARCH).
4. **Per layer**, in this order, open the layer file only if the layer may be needed:
   1. **Needed?** Apply the layer's Rule 0. Many layers end at the minimum from `base.md` → *Nine layers*.
   2. **Choice.** Start from the default in the layer's *Task → default* table. Move to "switch when" only when a stated fact meets it.
   3. **Why.** Cite the facts (`~3 000 chats/day`, `clients in KZ`, `refunds over 50 000 ₸`).
   4. **Rejected.** The nearest alternative and the fact that rules it out.
   5. **Fit.** Self-hosted or cloud and where data is processed; licence (open / source-available / proprietary) and status (base / pop / grow, archived); take or write (`base.md` → *Take or write*).
5. **Cross-check** against `base.md` → *Rules almost everyone repeats* (every "never" is an objection if the design does it) and *Build order* (read-only tools, traces and rights come before write tools; routing and cache last). Every box maps to a stated need.

Simplest harness that meets the stated facts wins. A framework, a graph, a second store or a router for unnamed future needs is an objection, not a feature.

## Decision record

One line per agent layer, after the infrastructure lines from `architecture-guide`, in the architecture slides and in `docs/SPECIFICATION.md` → *Tech stack*; first a line per agent with its type and rule-of-two profile:

```text
agent <name>: <staff|client|background>; rule of two: <A,B,C held> → <how the third is closed | human confirms>
agent/<layer>: minimum — <what> | not needed — <why> | <choice> (<licence>, <status>, <self-hosted|cloud, where data is processed>) — <why, with facts>; rejected: <alt> — <fact>
```

Layers: `loop`, `instructions`, `knowledge`, `memory`, `tools`, `gateway`, `protection`, `handoff`, `evals`.

Example:

```text
agent clinic-chat: client; rule of two: A (client text), C (books slots) — no access beyond the client's own bookings
agent/loop: Pydantic AI through own gateway (open, pop, self-hosted KZ) — 2 tools, Python backend; rejected: LangGraph — no pauses or branches
agent/knowledge: Postgres pgvector + full text, BGE-M3, bge-reranker-v2-m3 (open, base, self-hosted) — 300 pages of price lists and rules in Russian/Kazakh; rejected: Qdrant — 4 000 chunks
agent/memory: history in Postgres + profile in the prompt — clients return monthly; rejected: Mem0 — 5 facts per client
agent/gateway: Bifrost pinned by hash (open, grow, self-hosted KZ) — masking before the foreign model, budget per session; rejected: Cloudflare AI Gateway — data crosses a foreign network
agent/protection: Presidio + own IIN/phone recognisers, reversible labels; OpenFGA not needed — rights = "own bookings only", checked in the tool
agent/handoff: Chatwoot self-hosted, agent-bot API — 3 operators 9–18, night path creates a ticket
agent/evals: Langfuse self-hosted + OTel collector with masking; 40 cases from real chats as a CI gate
```

## Layers

| Layer | File | Rule 0 in one line |
|---|---|---|
| Base: nine layers, mechanisms M1–M13, 2026 shifts, agent types, rules, build order | `references/base.md` | agent = model + harness; see before you let it change anything |
| Frameworks and agent loop | `references/layers/frameworks.md` | own loop or the thinnest library; a heavy framework only for pauses, branches or several agents; state in your DB; pin versions |
| Knowledge base (RAG) | `references/layers/knowledge.md` | 30–50 real questions with answers first; Postgres (pgvector + full text + reranker); rights checked at search time |
| Memory and context | `references/layers/memory.md` | history in Postgres + a short profile in the prompt; long memory when you see what is forgotten; every record has owner, source, date; write only from trusted steps |
| Tools and skills | `references/layers/tools.md` | foreign MCP servers and skills are untrusted code; pin and hash descriptions; 1–3 own narrow read-only tools first; agent code only in a sandbox without network or secrets |
| Model gateway | `references/layers/gateway.md` | agent code knows aliases, not models or keys; gateway pinned by hash; prefix cache and rules before smart routing |
| Protection | `references/layers/guardrails.md` | design as if the injection already succeeded; keys outside the agent; egress allowlist; rights in code + human confirmation; mask before the model and the log |
| Channels and handoff | `references/layers/channels.md` | "call a human" works at once; the bot says it is an AI; silent while an operator holds the chat; honest time when nobody is there; write first only with consent |
| Observation and evaluation | `references/layers/evals.md` | read traces by eye, then code checks, then a calibrated judge; same checks as a release gate and on live traffic; mask before tracing |

Each layer file has: concepts, Rule 0, classes with every option's licence, status, internals, **good for and bad for**, clouds, and the *Task → default → when to switch* table.

## Data and clouds

- **Migration targets** (Alexey's projects move here): **Yandex Cloud**, **DigitalOcean**, **Railway**. Each layer file lists their services first, then AWS, Google Cloud, Azure, Cloudflare. Railway: **no GPUs, no managed search, no code sandbox**. Yandex Cloud has a KZ region, but which AI Studio services run in it is unconfirmed — check.
- **Kazakhstan** (not legal advice): the AI law (since 18 January 2026) — the first message says an AI answers; personal data stored in the country, clouds included (since 25 August 2026); sending correspondence to a foreign model needs a basis — consent, masking before sending, or a model in the country. So the gateway with masking, memory, traces and cache live at the client or a local provider; only masked text leaves; **embedding through a foreign API is also sending text abroad**; managed agent runtimes, cloud memory, cloud trace platforms and cloud support desks are out for such data.
- **Portable seams:** OpenAI-compatible API behind own gateway; aliases in a model registry with a "where processed" field; MCP for tools; SKILL.md for instructions; OTel traces through own collector; agent state in own Postgres.

## Red flags (checked 14 November 2026)

A draft that names one of these needs a stated reason:

- **Archived, frozen or closing:** Flowise (archived August 2026), LLM Guard (archived July 2026), Helicone AI Gateway (maintenance mode), Hugging Face TGI (archived March 2026), Zep open edition (retired; only Graphiti self-hosted), Daytona open repository (archived; self-hosted only enterprise), Langflow managed service (closed April 2026), AutoGen (community maintenance only).
- **Supply-chain incidents:** LiteLLM releases replaced with credential stealers (March and October 2026) and a proxy-takeover chain (June 2026); CrewAI VU#221883 (injection → host code execution via default Code Interpreter); Langflow CVE-2026-48519 and Flowise unauthenticated code execution in the editor; LangGraph checkpointer SQL injection + deserialisation, langchain-core CVE-2026-44843; 5.5% of 1 899 MCP servers with poisoned tool descriptions; 13.4% of open-catalogue skills with critical issues, every public skill scanner bypassed in under an hour.
- **Licence limits:** Dify (no multi-tenant resale, logo), n8n (Sustainable Use, no resale as a service), Restate (BSL), Inngest (SSPL), Phoenix and Nango (Elastic 2.0), Jina Embeddings v4 (non-commercial weights), Marker (paid above a revenue threshold), MinerU (own licence), Open WebUI (branding condition), Llama Guard (Llama licence), Kong AI Gateway token limits (paid only).
- **Unsafe defaults:** agentgateway serving every tool to anyone reaching the port; Ollama without auth; low-code editors exposed to the internet; Vercel AI SDK `stream()` without a step limit; CrewAI Code Interpreter on by default; agent code run outside a sandbox; tool or memory writes from untrusted text; a semantic cache shared across users or rights.
- **Claims to verify, not to trust:** memory benchmark scores (Mem0 92.5 vs 29.3 reproduced), gateway speed numbers from their vendors, routing and semantic-cache savings, injection-detector catch rates ("95%" is a failure), "OTel GenAI is stable" (it is not, as of November 2026).
- **Design smells:** multi-agent as the starting scheme; rights or "do not do X" only in the prompt; one shared service account for all agents; keys in the prompt, env or memory of the agent; a customer agent without a path to a human; write tools before traces, rights and read-only tools; a model name hard-coded in code; a fallback model never run on the eval set.

## Reference files

| File | Covers |
|---|---|
| `references/base.md` | agent = model + harness; request path with three example runs; nine layers (does / without it / minimum); mechanisms M1–M13 (simple / smart / pitfall); injection lines; 2026 shifts N1–N7; take or write per layer; Kazakhstan data; three agent types; always / never rules; build order |
| `references/layers/frameworks.md` | provider SDKs, independent libraries, durable execution, low-code builders, managed runtimes; clouds; task table |
| `references/layers/knowledge.md` | embeddings, hybrid search and rerankers, vector stores, graph approaches, document parsing, platforms, agentic search; clouds; task table |
| `references/layers/memory.md` | long-term memory layers, simple approaches, API-built-in compaction and memory, own compression, session storage, memory poisoning defence; clouds; task table |
| `references/layers/tools.md` | MCP server SDKs and tool design, MCP gateways and registries, code sandboxes, browser and screen, skills, integration platforms; clouds; task table |
| `references/layers/gateway.md` | open gateways, gateways on API gateways, hosted gateways, routing, three caches, virtual keys and budgets, fallbacks, model registry, own models; clouds; task table |
| `references/layers/guardrails.md` | PII masking, input/output guardrails, architecture against injection, authorisation and agent identity, approvals and decision log, red teaming; clouds; task table |
| `references/layers/channels.md` | web chat UI, messengers, voice, support desks, handoff rules and package, outbound reminders; clouds; task table |
| `references/layers/evals.md` | trace platforms, OTel conventions and collection, eval libraries, evaluation methods, versions and rollout, feedback and agent metrics; clouds; task table |
