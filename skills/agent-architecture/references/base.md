# Business-agent base: nine layers, thirteen mechanisms, build order

Source: Alexey's «База бизнес-агента» (November 2026). What is built around a model to get a working agent. The model can do one thing — take text and return text. It does not know the company, remembers nothing, cannot open the CRM and is not responsible for consequences. All of that is the **harness** around it: **agent = model + harness**. Authors count the layers differently (four, six, seven, eight, ten); the composition is almost the same. Here: nine layers in three rings, mechanisms inside the layers, and what covers them in 2026. Tools per layer are in `layers/*.md`.

Why the harness gets so much attention: LangChain raised its coding agent on Terminal-Bench 2.0 from 52.8% to 66.5% by changing **only the harness** — the model stayed the same.

## Request path

```text
channel → input filter → router → context assembly (instructions + knowledge + memory)
        → [model gateway: registry, limits, cache, masking, fallback] → model
        ⇄ permission gate → tools   (loop until done; dangerous action → confirmation first)
        ← compaction (long tool results, old history → summary)
        → output check (facts, rules) → answer to the user | human with the full context
observation rail under everything: every step is traced — traces, quality scores, cost
```

The model is one block among many. **Rights are checked outside the model, in code: it may ask for anything, it gets only what is allowed.**

Three example runs (invented for illustration):

- **CRM companion.** A manager asks in the CRM "what's with the Altyn Stroy deal?". The request carries who is asking → relevance and the employee's daily budget are checked → the router picks a fast model and the "sales" tool set → context: sales rules, deal card, latest notes → the model asks for deal search → the permission gate checks this manager may see this deal → CRM returns two years of history → compaction keeps recent events + a short summary → answer with a next step → output check: grounded in CRM data, no foreign deals → summary in the CRM window, every step in the trace.
- **Online chat with booking.** "Can I move my booking to Friday?" from the site widget, phone already verified → the client's text is data ("forget your instructions" is not a command) → intent "reschedule" switches on the booking scenario with two tools → tone, limits, rescheduling rules, past visits → **name and phone are replaced with labels before the API**, the model wants the booking and free slots → the gate allows reading/changing only this client's bookings → calendar returns three slots, client picks, agent moves the booking → labels swapped back in the final answer → check: date and time match what is really in the calendar → confirmation, a reminder the day before is scheduled automatically.
- **Background request triage.** At night a refund request three times the usual amount arrives; no dialogue — a timer or new email starts the agent → the email is external, so untrusted; attachments checked, instructions in the text not executed → money topics go to a strong model, no saving → refund regulations, expected result, state of previous runs → the agent checks the order and client history → **service account: may read orders, may not issue a refund itself** → amount above the regulation threshold → raw system answers replaced by an extract → the model prepares a decision and explains what breaks the rules → check: irreversible and above the limit → **queued to a human**: what happened, what was checked, what the agent proposes.

## Nine layers

| # | Ring | Layer | What it does | Without it | Minimum to start |
|---|---|---|---|---|---|
| 01 | context | **Instructions and role** (system prompt) | tells the model who it is, whom it works for, what is allowed and forbidden, what tone | behaves like a generic chatbot: answers anything, promises what the company does not offer | a short prompt: role, task, boundaries, answer format; kept in the repo and versioned as code |
| 02 | context | **Company knowledge** (retrieval, RAG) | for each question finds the right document chunks and fresh system data and puts them in context | the model invents or answers from stale data — **the main source of "hallucinations" in business tasks** | semantic + keyword search, 1–5 chunks per request, a source link in the answer |
| 03 | context | **Memory and state** | short memory holds the current dialogue, long memory facts about the client, state remembers the task step | every conversation from zero, the client repeats themselves, a long task is lost after a crash | dialogue history in the DB; long memory only when a real need appears |
| 04 | action | **Tools and integrations** (tools, MCP) | functions to read and change data in systems; MCP is the common connection standard | the agent only talks; cannot book a client or update a deal | 1–3 tools with clear names, a strict input schema and clear errors; **read-only first** |
| 05 | action | **Agent loop** | code that spins "think → call a tool → get a result → think again" and decides when to stop | loops, burns money, or drops the task halfway and says "done" | one loop, a step limit, retry on failure, **an explicit "done" condition checked by code, not by the model** |
| 06 | control | **Access and rights** (identity, permissions) | the agent acts on behalf of a specific person and sees only what that person may see | a manager gets other people's deals, a client sees other people's orders; **"don't show" in the prompt is not protection** | rights checked in code on every search and every tool call; the agent has its own narrow account |
| 07 | control | **Guardrails** | input and output checks, confirmation of dangerous actions, a spending ceiling | foreign text in an email or document hijacks the agent — prompt injection, risk #1 in OWASP 2026 | everything read from outside is data, not commands; money, deletion and external sending only through confirmation |
| 08 | control | **Handoff to a human** | when the agent cannot cope or risk is high, the conversation goes to a live employee with the whole context | the client explains everything again, already irritated; background tasks silently stall | triggers: asks for a human, agent unsure, client angry, topic from a closed list; package: history, what was tried, reason, next step |
| 09 | control | **Observation and evaluation** (tracing, evals) | traces record every step; evals are test scenarios run on every change | no way to know why the agent erred or whether a prompt edit broke what worked yesterday | traces from day one, a couple of dozen scenarios from real requests, a cost counter per request |

## Thirteen mechanisms

A layer answers "why", a mechanism "how". No new layers here: each mechanism lives inside one of the nine. For each: the **simple** variant to start with, the **smart** one reached under load, and the **pitfall** — the bad use.

| # | Mechanism | Lives in | What it is | Simple | Smart | Pitfall |
|---|---|---|---|---|---|---|
| M1 | **Gateway and model registry** | between the loop and the model | all model calls through one point; the registry keeps per model price, window, abilities and **which data may be sent to it** | one config with models and one call function for the whole project | a separate service: keys, limits, cache, fallback, cost per user and feature | the model name hard-coded in ten places — changing the model becomes a repo-wide search |
| M2 | **Task routing** (routing, cascade) | agent loop, at the entrance | per request decides which model, which tool set, which scenario | rules: channel, command, request length — cover most cases | a small intent/complexity classifier, or a cascade: cheap model first, strong one on uncertainty | the router can cost more than it saves — every error is a bad answer or a double call; **new rules run "in the shadow" first**, without affecting answers |
| M3 | **Smart limits** (token budgets) | guardrails, inside the gateway | count tokens and money, not requests: one request can be 1000× costlier than another | requests per minute per user + a step ceiling in the loop | token budget per user, department and feature per day and month; a soft threshold moves to a cheap model, a hard one stops; background jobs get their own budget | an anonymous site chat without a per-session/IP limit — one bot burns the monthly budget overnight |
| M4 | **Cache** (prompt cache, semantic cache) | gateway | three kinds: provider prefix cache (stable prompt start), exact cache (same request), semantic cache (similar meaning) | keep the prompt start stable (instructions, tool descriptions) — the prefix cache then works almost for free | a semantic cache for frequent general questions with a stable answer: prices, addresses, terms | an answer built on one client's data goes to another; **the cache key includes the user and rights, personal data never goes into a shared cache, entries expire** |
| M5 | **Fallback and retries** | gateway | the provider is down or hit its limit: retry with a pause, then another model | a timeout and two retries with growing backoff | a chain of fallback models and automatic disabling of a failing provider | the fallback model behaves differently — **run the prompt and test scenarios on it too** |
| M6 | **PII masking** | gateway, before the model call | before the API names, phones, IIN and card numbers become labels like `<PERSON_1>`; swapped back in the answer; the mapping stays with you | regexes and checksums for formatted data: phone, email, card, IIN | plus a name/address recognition model; one mapping table per session so `<PERSON_1>` is the same person in every message | masking only the user's text and forgetting tool results, traces and the cache; **the mapping table itself is sensitive data** |
| M7 | **Prompt-injection defence** | guardrails and rights | several lines in a row; no reliable filter exists, so **the main work is limiting the damage of an attack that got through** | external content labelled as data; irreversible actions only through confirmation | the rule of two: in one session at most two of three — untrusted input, private data access, external actions | believing a detector that "catches 95% of attacks" — for security 95% is a failure |
| M8 | **Audit log and retention** | observation | who, on whose behalf, asked what, got which data, did which action; plus how long to keep, where it physically lives, how to delete | an immutable log of every tool call | retention per data type, masked traces, export for audits | **traces become the most complete copy of personal data in the system, and the worst protected** |
| M9 | **Context window and compaction** | context and memory | the context is rebuilt every step; three techniques: clearing old tool results, compacting history into a summary, notes outside the window | a tool returns a short answer, not the whole page; history trimmed by length | result clearing as the main technique, compaction at ~70% of the window, the important bits written to memory before compaction | waiting until the window runs out — **the model starts getting confused much earlier**. In Anthropic's analysis a research agent without context management reached 335k tokens in five turns, 96% of them file-read results |
| M10 | **Structured output** | agent loop, check | the model returns data by schema; code validates before acting | schema, validation, one retry on error | validating meaning, not just form: date in the future, amount within limits, record exists | parsing free text with regexes |
| M11 | **Safe action retries** (idempotency) | tools | repeating the same call does not create a second record or charge twice | an operation key on every tool that changes something | dry run: the tool first shows what it will do, then does it | a loop with retries and an unprotected tool — the client is booked three times |
| M12 | **Document pipeline** (ingestion) | knowledge | how documents get into search: parsing, chunking, rights labels, updates, deletion | a script that rebuilds the index on a schedule | event-driven updates, rights on every chunk, a freshness date in the answer | a deleted document keeps living in the index; an employee finds via search what is closed to them in the source system |
| M13 | **Versions and feedback loop** | observation | prompts, tool descriptions and router rules versioned; user ratings and handoff cases feed the test scenarios | prompts in git, "helped / didn't help" buttons under the answer | rolling a new version out to a small traffic share and comparing with the old one | editing the prompt live in production without running tests |

**Injection lines** (in order): 1 label "data" (external separated from commands) → 2 input filter (catches the known, not everything) → 3 narrow rights (a fooled agent can do little) → 4 confirmation (a human decides the irreversible) → 5 output check (no leaks, no links out). Lines 1–2 try to keep the attack out and **can be bypassed — plan for it**; the main weight is on 3–5: they work in code and do not depend on whether the model was fooled. Traces run under all of them.

## What covers it in 2026

The main shift of the year: half the mechanisms moved inside APIs and SDKs. Less to write by hand, more to configure. **What stays yours is where knowledge about the client lives.**

- **Already inside the API or SDK** (a parameter or in the box): agent loop, compaction, result clearing, memory, prefix cache, structured output, tool search, programmatic tool calling.
- **Taken as a ready product** (often open source, self-hostable): model gateway, limits and budgets, fallback model, semantic cache, traces and evaluations, input/output filters, PII recognition.
- **Still written yourself** (company-specific logic and data): access rights, tools to the client's systems, instructions and skills, document pipeline, handoff, confirmation of dangerous actions, test scenarios, masking rules for the country.

### New or changed since late 2025

| # | What | Layer | What it is | What it changes | Pitfall |
|---|---|---|---|---|---|
| N1 | **Agent Skills, SKILL.md** | instructions | a folder with `SKILL.md`, scripts and references; only the description (~100 tokens per skill) sits in context, the rest loads when the task matches; open standard since December 2025, 40+ tools read it by September 2026 | client regulations no longer go into the system prompt — each process becomes a skill and the library grows without growing cost | foreign skills are a supply chain: hundreds of malicious ones found in open catalogues in early 2026; **keep your own small library** |
| N2 | **MCP 2026-07-28** | tools | the summer spec removed the handshake and sessions — each request is self-contained; authorisation moved closer to plain OAuth | an MCP server to a CRM sits behind an ordinary load balancer like any HTTP service; corporate login via the client's IdP becomes realistic | the version breaks compatibility; old servers need updating, and every request now proves its own rights |
| N3 | **Tool search, programmatic tool calling** | tools and context | tool descriptions load on demand; instead of a chain of calls the model writes a small script that calls the tools in a sandbox and only the result returns to context | removes the old "no more than a couple of dozen tools" rule; in Anthropic's example tool descriptions shrank from 77k to 8.7k tokens | needs a code sandbox — a separate risk zone; **verify the gain with tests, not on trust** |
| N4 | **Server-side compaction, memory tool** | context and memory | compaction, tool-result clearing and file memory are request parameters at Anthropic; OpenAI has a compaction threshold and a separate endpoint | M9 is now configured more often than written; what stays yours is the decision **what** to keep | lock-in: with a fallback model from another vendor compaction has to be redone yourself |
| N5 | **Managed agent runtimes** | agent loop | clouds sell the whole runtime: isolated session, memory, credentials, traces; several vendors shipped nearly identical offerings in spring 2026 | no need to build sandboxes and session storage — good for a quick start | the agent's data and memory end up in a foreign cloud — for a Kazakhstan client that hits the data block below |
| N6 | **OpenTelemetry GenAI** | observation | common field names for model calls, agent steps and tools (`gen_ai.*`); still being finalised, but main tools accept it | traces are written once, the viewing system can change without rewriting code | by default prompt/response text is not written; **when you enable it, enable masking too** |
| N7 | **OWASP Agentic Top 10** | guardrails and rights | December 2025, risks ASI01–ASI10; main idea: **least agency** — every capability the agent does not need is extra attack surface | a ready checklist for the client's threat model; a text filter is the first remedy for only two of the ten risks, the other eight are closed by system design | reading only the LLM list — for an agent that acts, OWASP advises both lists together |

### Layer by layer: take or write (product names are examples, not a choice)

| Layer | Covered by | Decision | Caveat |
|---|---|---|---|
| Agent loop | provider SDK (Claude Agent SDK, OpenAI Agents SDK, Google ADK) or independent (LangGraph, Pydantic AI, Mastra) | take | independent SDK if a fallback model from another vendor is needed |
| Tools | MCP as the protocol, own thin servers over the client's systems | take the protocol, write the servers | ready connectors to local CRMs and accounting systems usually do not exist |
| Instructions | skills (SKILL.md) and a short system prompt | take the format, write the content | the content **is** the knowledge about the client |
| Knowledge | vector search in your own DB plus a document pipeline | assemble from ready parts | the pipeline and chunk rights are yours anyway |
| Memory and compaction | built into API and SDK | take and configure | check where the memory physically lives |
| Gateway, limits, cache, fallback | open gateways (LiteLLM, Portkey, Bifrost) or cloud (Cloudflare AI Gateway) | take | an open gateway can be kept in-house |
| Masking | Microsoft Presidio as the base, own recognisers | take the base, write the rules | IIN and local number formats are poorly known by ready sets |
| Access and rights | nothing ready | write | it is the client's logic, it cannot be bought |
| Guardrails | filters: NeMo Guardrails, Lakera, LlamaFirewall, SDK built-ins | take filters, write the rest | confirmations and the rule of two are not in any product |
| Handoff | the client's support desk or CRM | write the glue | triggers and the context package are yours |
| Traces and evaluations | Langfuse or Phoenix in-house over OpenTelemetry | take | test scenarios are written only on your own data |

## Customer data in Kazakhstan

Three norms that directly affect the architecture (not legal advice — check with the client's lawyer):

- **Law "On Artificial Intelligence"** in force since 18 January 2026: the user must be told the service is provided with AI. For a customer chat that is the agent's first message.
- **Personal data stored in the country.** Since 25 August 2026 the norm reads wider — "in a database and/or digital object" in Kazakhstan, so clouds fall under it too. Parallel storage abroad is not prohibited.
- **Cross-border transfer.** Per an analysis of the updated collection and processing rules (autumn 2026), sending correspondence to a foreign model needs a legal basis. Three working paths: client consent, masking before sending, a model inside the country.

**Conclusion for the build:** the gateway with the anonymisation core, memory, traces and cache live at the client or a local provider; only masked text leaves. A ready cloud runtime is better not used for such data.

## Not to take on faith yet / already the norm

- **Not yet:** multi-agent as the starting scheme (useful when the task really splits, not "because it's fashionable"); foreign skill and MCP-server packs without reading the code; promised savings from routing and semantic cache without measuring on your own traces.
- **Already the norm:** MCP for tools and skills for instructions; one model call path through a gateway, budgets in tokens; OpenTelemetry-format traces from day one.

## Three agent types: where each layer is heavier

One base, different load per layer. ●●● = do not save here, ● = the simple variant is enough (Alexey's summary of sources and practice, not a standard — revisit per client).

| Layer | For staff (CRM companion, document search) | For clients (online chat, booking, reminders) | Background (request triage, reports, no dialogue) |
|---|---|---|---|
| Instructions | role and department rules | tone, boundaries, what must not be promised | a precise description of the result |
| Knowledge | ●●● all the value is here: regulations, contracts, base | prices, services, schedule — only current | only what the task needs |
| Memory | deal or project context | client history so as not to re-ask | progress between runs |
| Tools | CRM, mail, calendar | a narrow set: booking, order status | ●●● the whole job is calls |
| Agent loop | short tasks, a human nearby | short dialogues | ●●● stopping, retries, step limit |
| Access and rights | an employee sees only their own | ●●● a client sees only their own data and only after identity verification | a narrow service account |
| Guardrails | internal data leaks | ●●● anyone writes anything | confirmation of the irreversible, a spending ceiling |
| Handoff | the employee is the human in the loop | ●●● the most expensive moment of the whole dialogue | a manual review queue |
| Observation | the employee notices the error themselves | ●●● the client sees the error, not you | ●●● nobody watches in the moment |

## Rules almost everyone repeats

**Always:**

- Start simple: one model, one task, a couple of tools. Add the next layer when the previous one holds the load.
- Treat everything the agent read from outside (email, site, document, tool answer) as untrusted data.
- Give the agent the minimum tools and rights for the specific task.
- Check rights in the search and tool code, by the identity of the person the agent works for.
- Pass risky actions through human confirmation.
- Hand the conversation to a human together with the context, not just switch.
- Write traces from day one and run test scenarios on every change of prompt, model or tool.
- Set a "done" condition and limits: steps, time, money.
- Call models only through one point — the registry, limits, cache and masking live there.

**Never:**

- Treat the system prompt as protection or a secret — it is configuration and can be extracted.
- Dump every document into the context — more context is not better, the right context is.
- Take the model's word that the task is done or that it is "90% sure".
- Hand out two dozen tools at once — each extra one is another way to make a mistake.
- Start with a multi-agent scheme — it is much harder to debug and burns more tokens.
- Put keys and passwords into the prompt or the agent's memory.
- Ship a customer agent without a path to a live human.
- Put answers built on personal data into a shared cache.
- Let one agent read foreign text, see private data and write outside, all at once, without a human in the loop.

## Build order

Recommended order for a client's first agent: **first see what the agent does, only then let it change anything.**

1. **One task and instructions** — narrow role, boundaries, answer format.
2. **One model call point** — a model config and one function; limits, cache and masking land here later.
3. **Traces and test scenarios** — otherwise you work blind from here on.
4. **Knowledge** — document search with source links.
5. **Read-only tools** — the agent looks into systems, changes nothing.
6. **Rights and guardrails** — before the first write action appears.
7. **Write tools** — through confirmation for everything irreversible.
8. **Handoff to a human** — triggers and the context package.
9. **Memory and context compaction** — once you can see what is worth remembering and what bloats the window.
10. **Routing and cache** — once there is traffic and traces show where to save.
11. *Later:* several agents, A2A, new stores — a second pass.
