# Agent layer: memory and context

Source: Alexey's «Память и контекст» (map 3 of 8, checked 13 November 2026). How to make the agent remember: long-term memory layers, simple approaches without a product, what is built into model APIs, context compression, session storage, protecting memory from poisoning. Why the layer exists is in `../base.md` (layer 03, mechanism M9); search over company documents is in `knowledge.md`.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **Three different memories.** *Window*: what the model sees in this request. *Session*: dialogue history and the saved progress of a task. *Long-term memory*: facts that live between sessions. They are stored in different places and cleaned by different rules. **Mixing them up is the main cause of crooked designs.**
- **Who writes to memory.** Either the system extracts facts from the dialogue (Mem0, Graphiti, Cognee): predictable, but it remembers only what the extractor deemed important. Or the agent decides what to write (Letta, memory tool): it learns and corrects itself, but quality depends on the model.
- **Do not trust memory scores.** All LongMemEval and LoCoMo numbers are published by the vendors. Mem0 claims 92.5 on LoCoMo; an independent reproduction on the same test got 29.3. Choose by design and measure on your own dialogues.

## Rule 0

Start with the dialogue history in Postgres and a short client profile in the prompt. Add long-term memory when you can see **what exactly** the agent forgets. Every record has an owner, a source and a date. **Memory is written only from trusted steps, not from any text the agent has read.**

## Classes and technologies

### LONGTERM — long-term memory layers
Products that keep facts about a user between sessions. Three designs: *extract and retrieve* (facts pulled from dialogue, found by similarity), *temporal graph* (each fact has a validity period), *agent-managed memory* (the agent moves what it needs between the window and storage).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Mem0** | open (Apache 2.0) · pop | library and managed service; extract-and-retrieve, optional graph; Postgres, Qdrant, Valkey and others; MCP (OpenMemory, local memory server); the largest community and shortest path — pass messages and a user id, it extracts facts, dedups and searches. Weak at "when was this true"; **claimed scores not independently confirmed** | personalisation: preferences and facts about a client; adding memory to an existing agent without rework | facts that change often where change history matters; needing provable accuracy (you will measure yourself) |
| **Graphiti and Zep** | open (Apache 2.0, Graphiti) · pop | Graphiti is a library, Zep a managed service; a fact graph with start and end dates on Neo4j / FalkorDB; official MCP server; **a stale fact is not overwritten but closed with a date** — one store answers both "what plan now" and "what plan in March". Zep's open edition was retired in April 2025: self-hosted is only the Graphiti engine | client data that changes: plan, address, status; audit of when the agent learned a fact and when it stopped holding | no wish to run a graph database; simple personalisation (dead weight) |
| **Letta** | open (Apache 2.0) · pop | ex-MemGPT; an agent runtime + cloud you **move into**, not a library you plug in; memory blocks in the window plus an archive, background "sleep-time" agents rewrite blocks; Postgres; stores everything incl. reasoning and tool calls; in 2026 the focus moved to Letta Code and versioned file memory under git, some older server tools deprecated | a long-lived agent with its own "personality" and notes; memory that must change between dialogues | an existing framework (you would have to migrate); needing API stability for years |
| **Cognee** | open (Apache 2.0) · grow | Python; graph + vectors, "add, cognify, search" pipeline; choice of graph, vector and relational stores; MCP; on the border between memory and a knowledge base — builds the graph from documents and data too; local by default | memory assembled from different company systems; everything must run in-house | only user-preference history |
| **LangMem** | open (MIT) · pop | Python; vector memory over the LangGraph store (Postgres and others); tied to LangChain — no new infrastructure if you are already on LangGraph | an agent on LangGraph | any other framework |
| **Hindsight** | open (MIT) · grow | Vectorize; a server in one Docker command; passive extraction, four retrieval modes, time awareness, built-in store, own memory-write filter; no migration to a foreign runtime; claims 91.4% on LongMemEval (own measurement) | time-aware memory without a graph database; a quick self-hosted start | when maturity and community size matter |

### SIMPLE — simple approaches
Memory without a separate product. **For most business agents this lasts a long time, and it is where to start.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Facts table in Postgres** | open (technique) · base | a row per fact: owner, fact text, source, written at, revoked at; written by a separate step after the dialogue or by a tool ("client changed address"); before answering the agent gets the client's latest valid facts; search by owner, later pgvector + full text; **deletion is one query by owner**; everything visible in plain SQL, rights and deletion by the database | a customer chat: preferences, past requests; clear audit and deletion on request | thousands of facts per person with complex relations |
| **Profile in the prompt** | open (technique) · base | a 10–20 line client card always at the start of the context, refreshed by a separate step or background job from CRM and the facts table; what is needed in every answer is not searched but put in the window (name, language, plan, last problem) — Letta's "core memory block" without the runtime. **A rule in the window works more reliably than a rule the model has to guess to look up** | any agent that talks to a known person; stable tone and format preferences | data that changes every minute (a tool returns that) |
| **Markdown file memory** | open (technique) · pop | a directory of files, git, an index/table of contents; debug by opening a file; Letta's 2025 test: an agent with dialogue history in plain files scored 74.0% on LoCoMo vs 68.5% for Mem0's graph variant; transparent with edit history, but files grow and the agent **silently starts skipping their content**, and splitting memory per user and per rights is hard | an agent running one project or one owner; internal team tools | thousands of clients with separate memory; memory without regular cleanup |

### NATIVE — built into model APIs
Since late 2025 compaction and memory are request parameters. **The main shift in this layer:** what used to be written is now switched on. The price is provider lock-in — a fallback model from another vendor will not have these mechanisms.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Server-side compaction (Anthropic)** | prop (API) · pop | `context_management` in the Messages API; triggers on a token threshold (default 150k) or on demand; replaces the old part of the dialogue with a summary block written by the same model; custom instructions on what to keep; the client returns the compaction block in the next request; Anthropic's recommended way for long dialogues and agent tasks | long dialogues and multi-hour tasks on Claude; not wanting to write and debug your own summariser | needing to know exactly what survives compaction; a fallback model from another vendor |
| **Tool-result clearing (Anthropic)** | prop (API) · pop | context editing: on a token threshold removes old tool results and thinking blocks, **keeps the record of the call**; no model call; in tool-using agents results eat almost all the space, so this goes first | an agent with dozens of tool calls per task; long search and document reading | when an old result will be needed verbatim (it should have been saved to memory) |
| **Memory tool (Anthropic)** | prop (API) · pop | a client-side tool: the model reads and writes files in a memory directory; **you implement the storage** (disk, DB, S3), so data stays with you; lives between sessions; before compaction the agent can flush what matters into memory | long tasks where notes must not be lost; memory that must live in your own infrastructure | a customer chat with a rigid fact schema (a table is simpler) |
| **Compaction and stored conversation (OpenAI)** | prop (API) · pop | Responses API: `compact_threshold` and a separate `/responses/compact` endpoint (March 2026, compacts without a model request); `store` + `previous_response_id` — send only new messages; the summary is an **encrypted opaque block**; the conversation can be stored entirely at OpenAI — for Kazakhstan personal data that is storage abroad | an OpenAI stack; long coding and research tasks | data that must stay with you; needing to read and check the summary |

### COMPRESS — context compression on your own
When there is no built-in option, it does not fit, or portability between models is needed. **Measure solved tasks and total cost, not the percentage of tokens removed:** too aggressive compression makes the agent re-fetch what was lost, and the total gets more expensive.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Observation masking** | open (technique) · base | a dozen lines of code: an old tool result becomes a placeholder, the call itself and the last 3–5 results stay; zero model calls, any model; on SWE-bench it matched full model-written summarisation; Anthropic's result clearing in your own code | any agent with tools; the first thing to do when the window grows | tasks where verbatim old results matter |
| **Structured summary** | open (technique) · base | own summariser prompt by sections: goal, decisions taken, what changed, constraints, open questions; at about 70% of the window, cheap model; Factory's comparison: 3.70 vs 3.44 for Anthropic's built-in and 3.35 for OpenAI's. **The worst-preserved part under any compaction is the record of what was done** (files changed, checks passed) — keep it as its own section | control over what survives; one scheme for different models | short dialogues (an extra model call) |
| **Subagents with a clean window** | open (technique) · pop | the dirty work (document search, log analysis) goes to a helper with its own window, a short report comes back instead of a hundred pages read; in Claude Agent SDK, LangGraph and others; more tokens in total, a cleaner main window. **Context isolation, not a multi-agent system for fashion** | research and search inside a large task; parallel independent subtasks | a simple dialogue; a subtask that needs the whole main context |
| **Headroom** | open (Apache 2.0) · grow | library, proxy and MCP server (Python, TS), January 2026; compresses tool results, logs, JSON, code, search chunks; reversible (original retrievable on request); claims 60–95% of tokens; proxy mode needs no agent code changes; **may give no gain with a large stable cached context**; very young, changes often — pin the version | an agent drowning in tool output and logs; trying compression without rewriting the agent | when the main saving already comes from the prefix cache; conservative production (too fresh) |
| **LLMLingua** | open (MIT) · base | Microsoft Research, Python; LLMLingua, LongLLMLingua, LLMLingua-2; up to 20× compression on tests; irreversible; a small model drops low-information tokens. **Risk: rules like "answer only in JSON" or "client is on the free plan" look predictable to it and are washed out first, especially on repeated compression** | long reference inserts and examples in the prompt | instructions and constraints (never compress them); code and exact values |

### SESSION — session and task-progress storage
Where the dialogue history and checkpoints live. The boring part people wrongly save on: **a lost session is a client explaining everything again.** Database internals are in `architecture-guide` → `layers/databases.md`.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **PostgreSQL** | open (PostgreSQL License) · base | messages, graph checkpoints, facts, summaries; ready: PostgresSaver in LangGraph, DBOS, Mastra and Agno stores; deletion by a plain query per user; one DB for history, state and memory simplifies backups and client-data deletion. **Do not put large files into state: a checkpoint is written every step — a 50 MB PDF becomes half a gigabyte in ten steps** | almost any agent; pauses for approval and resume after a crash | thousands of rps on a hot session without a cache |
| **Valkey** | open (BSD-3) · base | open Redis fork in memory; current dialogue, intermediate tool state, limit counters; TTL per key; LangGraph checkpointer, Mem0 pairing; sub-millisecond; **without persistence configured, a crash means loss** — usual scheme: Valkey hot, Postgres long | many concurrent dialogues; per-user budget and limit counters | the only history store; a small project (Postgres is enough) |
| **SQLite** | open (public domain) · base | one file, zero infrastructure; checkpoints and history of one process; LangGraph and CrewAI checkpointers, libSQL in Mastra; locks start with several concurrent writing workers | development and prototypes; one process on one server | several workers; fault tolerance |
| **Object storage for artefacts** | open (technique) · base | documents, exports and long tool results go to S3-compatible storage (`architecture-guide` → `layers/files.md`), state holds an id and a short description; the agent reads the needed part when required — offloads both the DB and the window | an agent working with files and large exports | small data (an extra step) |

### SAFETY — protecting memory
A prompt injection lives one session. **A poisoned memory record lives until someone finds it and fires weeks later.** In the MINJA study harmful records were injected through ordinary queries in more than 95% of attempts. OWASP made it a separate risk, ASI06, and ordinary injection filters do not cover it.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Source and owner on every record** | open (technique) · base | a data-schema rule: owner, which step and source, when, trust level; reads only the current user's records; writes only from trusted steps. **The main measure, and it is architectural:** a fact from the client's own words and a "fact" from an email the agent read are not equal; one client's memory physically cannot reach another's answers — the owner filter sits in the read code | any long-term memory; multi-tenant agents | no case where it is redundant |
| **OWASP Agent Memory Guard** | open (Apache 2.0) · grow | Python middleware, 2026 reference implementation against ASI06; checks every read and write against a YAML policy: injections, secrets, tampering, abnormal size; memory snapshots and rollback; LangChain wrapper; versions 0.2–0.3 — early, use as a base and a reference point, not a guarantee | an agent that reads external text and writes to memory; a reference point for your threat model | being the only line of defence (a filter does not catch everything) |
| **TTL and forgetting** | open (technique) · base | revoked-at date on a fact, TTL on sessions, a cleanup job; types of records get their own retention. **A stale fact is worse than a missing one — the agent will confidently say something false.** Deletion on request goes through **every** place: facts, vectors, history, post-compaction summaries, traces and cache | customer agents; personal data | no case where it is redundant |

## Clouds

Memory about a client is personal data in its purest form. For a client in Kazakhstan, managed memory in a foreign cloud hits the same requirements as the customer database: **history, facts and summaries must be stored in the country.**

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Managed PostgreSQL | no separate long-term memory service found in AI Studio; history, checkpoints, facts, pgvector | the main memory store |
| | Managed Valkey | session cache and counters | many concurrent dialogues |
| | Object Storage | artefacts and agent memory files | large results and agent notes |
| DigitalOcean | Managed PostgreSQL / Managed Valkey / Spaces | no memory service of its own; history and checkpoints, session cache, artefacts | main store; hot dialogues; artefacts |
| Railway | Postgres / Redis templates | next to the agent; Mem0 or Graphiti as plain containers | start; load grew |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | AgentCore Memory (short-term raw session events, long-term asynchronously extracts facts, preferences, summaries; event retention up to 365 days; own KMS keys); DynamoDB for sessions; ElastiCache / MemoryDB (Valkey) for hot sessions |
| Google Cloud | Sessions and Memory Bank (builds long-term memories from conversations, for ADK agents); Memorystore for Valkey (active sessions) + AlloyDB / Cloud SQL (long-term memory in Postgres) for your own scheme |
| Azure | Foundry Memory (managed long-term memory with automatic extraction and merging; public preview in spring 2026 — check status); Cosmos DB for sessions; Azure Managed Redis for hot dialogues |
| Cloudflare | Durable Objects (per-agent state with built-in SQLite, one agent per user); Agent Memory (2026, managed long-term memory); KV / R2 for cache and artefacts |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Chat must remember the current dialogue | history in Postgres: last turns + summary of older ones | many concurrent dialogues → hot cache in Valkey |
| Client returned after a month | facts table in Postgres + profile in the prompt | many facts, ready extraction needed → Mem0 self-hosted |
| What did the client prefer six months ago | Graphiti | no graph DB → revoked-at date in the facts table |
| Agent runs a long project and learns | file memory: memory tool or Markdown under git | ready runtime needed → Letta |
| Agent already on LangGraph | LangMem | — |
| Memory from many company systems | Cognee | — |
| Window clogged with tool results | API result clearing or own observation masking | middleware without touching the agent → Headroom |
| Dialogue does not fit the window | server-side compaction | control over the summary → structured summary |
| Search and analysis inside a large task | subagent with a clean window | — |
| Agent reads external text and writes to memory | source and owner on every record, writes only from trusted steps | additionally → Agent Memory Guard |
| Client asks to delete their data | delete by owner in every store, incl. vectors, summaries and traces | — |
| Customer data in Kazakhstan | memory and history in own database in the country | — |
| A fallback model from another vendor exists | own compaction and own memory, not the API-built-in ones | — |
