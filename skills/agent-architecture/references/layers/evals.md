# Agent layer: observability and evaluation

Source: Alexey's «Наблюдение и оценка» (map 8 of 8, checked 14 November 2026; the market changes owners fast — check licence and owner before choosing). How to know the agent works well and notice when it got worse: trace platforms, recording standards, evaluation libraries, methods, prompt versions and feedback. Why the layer exists is in `../base.md` (layer 09, mechanisms M8 and M13, N6); attack testing is in `guardrails.md`; handoff metrics in `channels.md`; general service observability in `architecture-guide` → `layers/observability.md`.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **The request passed, the task did not.** Ordinary monitoring sees latency, errors and cost. For an agent every call can return success while the task is unsolved: the wrong tool was chosen, the steps went in circles. **Evaluate the agent's whole path, not a single request.**
- **The judge gets checked too.** A judge model gives a number that looks like a fact. Trust it only after comparing with human labels on the same examples. First measure how much humans agree with each other: if two experts disagree, **fix the criterion, not the judge prompt**.
- **From failure to test.** Every failure found becomes a row in the example set, run on every change of prompt, model or tool. Quality stops depending on who remembers what. Per LangChain's 2026 survey, about half of teams run evaluation on test sets and about a third on live traffic.

## Rule 0

First read traces by eye and write down what exactly breaks. Then write simple checks in code. Add a judge model last and calibrate it against humans. Run **the same checks** before release as a gate and after release on live traffic. **Mask personal data before it is written to a trace.**

## Classes and technologies

### TRACE — trace platforms
A trace records one agent run: every model, tool and retrieval call with input, output, time and cost. A platform stores traces, shows them as a tree and usually adds evaluations, example sets and prompt versions. **Several platforms changed owners in 2026, so licence and owner matter here more than anywhere.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Langfuse** | open (MIT, open core) · base | self-hosted or cloud; owned by ClickHouse since January 2026 (core licence and self-hosting kept, enterprise features separately licensed); traces, evaluations, example sets, prompt versions, labelling; any framework, OTel ingest; **self-hosting is four services (Postgres, ClickHouse, Redis, S3), not one container**; first choice in most 2026 reviews | an open platform on own server; when the agent framework may change | nobody to maintain four services |
| **Arize Phoenix** | src (Elastic License 2.0) · pop | Arize AI; local or server app started with one command; OpenInference over OTel; strong at retrieval and embedding analysis, evaluations; the simplest start next to the code. **Not open in the strict sense: use and self-host yes, sell as a service no**; per one report Arize agreed a deal with Dynatrace | debugging RAG and an agent on your machine; a stack already on OTel | needing an unrestricted licence |
| **Opik** | open (Apache 2.0) · grow | Comet ML; self-hosted or cloud; traces, built-in eval metrics, prompt versions, an agent optimiser; **one licence for the whole platform — nothing behind a licence key, incl. SSO and roles**; smaller community and fewer integrations than Langfuse | a clean open licence without an enterprise part; ready eval metrics out of the box | the widest integration ecosystem |
| **LangSmith** | prop (SaaS) · pop | LangChain; cloud, self-hosted only on the enterprise plan; deep LangGraph integration — one env var, shows the graph as is; multi-step agent debugging; per seat and per trace; only the SDK is open | an agent on LangGraph where the cloud is acceptable | data that must stay in-house without an enterprise contract |
| **Braintrust** | prop (SaaS) · pop | cloud grown from evaluations: experiments, version comparison, evaluations as a release gate; traces secondary; a convenient path from a production failure to a dataset row and a new experiment | teams where evaluation is already the main process | self-hosting; a small team without an eval process |
| **MLflow** | open (Apache 2.0) · pop | self-hosted; traces, evaluation, model and prompt registry; one tool for classic ML and LLMs; the agent-trace UI is simpler than specialised platforms | MLflow already in use | needing the best UI for analysing agents |
| **Observability in APM** | prop (various) · pop | Datadog, Grafana, Logfire and others; one picture — user request, services, DB, model call as one more span; evaluations and example sets weaker; for quality work a separate platform is still usually needed | operations: latency, errors, cost on a shared dashboard where on-call already looks | quality work: evaluations, labelling, experiments |

### OTEL — standards and collection
To avoid lock-in to one platform, traces are written in an open format. The transport is common: OpenTelemetry. **Field names are still split between three rule sets**, and the choice decides which platforms understand your traces without rework.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenTelemetry GenAI** | open (Apache 2.0) · grow | `gen_ai.*` naming conventions for model calls, tools, retrieval, agents, MCP; separate repo since June 2026; status **Development** — as of November 2026 no field is marked stable, and SDKs disagree on some of the most used attributes. Many articles claim it "became stable": **per primary sources it did not**. By default prompt and response text is not written; when you enable it, enable masking too | a long bet on the common standard; traces going to an ordinary observability system | expecting dashboards not to need edits on updates |
| **OpenInference** | open (Apache 2.0) · pop | Arize; conventions and instrumentation libraries (Python, TS, Java); span kinds model, chain, retriever, tool, agent, guardrail, evaluator; older than the official conventions and practically stable; native to Phoenix but goes to any OTel receiver; some libraries write both sets at once | stable field names right now | a platform that understands only `gen_ai.*` |
| **OpenLLMetry** | open (Apache 2.0) · pop | Traceloop, Python and TS; intercepts popular model SDKs and frameworks — traces in one line without touching agent code; part of the official conventions grew from it; some fields written in a deprecated form | traces today without touching code | a custom framework without a ready interceptor |
| **OpenLIT** | open (Apache 2.0) · grow | library and dashboard, Python first; models, vector DBs and **GPUs** in one metric set | own models on own GPUs | a TypeScript stack |
| **Own collector with masking** | open (technique) · base | an OpenTelemetry Collector in-house; masks personal data, cuts long fields, samples the stream, sends to one or more platforms; the agent writes to the collector, not the platform — **changing platform is a config edit**; masking from `guardrails.md` goes exactly here, so raw text never reaches trace storage | client data in traces; freedom to change platform | a one-developer prototype |
| **What to record** | open (technique) · base | per run: user, session, channel, **prompt version, model**, outcome; per step: input, output, duration, tokens, cost, error; **one id through the gateway, tools and subagents**. Without prompt and model versions you cannot tell what got worse after a change; without a shared id a tool call does not link to the user request; cost counted per step, shown per solved task | any agent | no case where it is redundant |

### EVAL — evaluation libraries
Code that runs the agent over an example set and scores it. They differ in form: pytest-style tests, a config file run from the CLI, or tasks for comparing models. Scores move between libraries easily; test formats do not.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **DeepEval** | open (Apache 2.0) · pop | Confident AI; Python, pytest style; dozens of ready metrics for RAG, dialogues, agents — task completion, tool choice, arguments, step count, plan adherence; scores the whole path or one step; **most metrics use a judge model inside, so everything about calibration applies** | a Python team with evaluations next to tests; ready agent metrics | a non-Python service |
| **Promptfoo** | open (MIT) · pop | CLI, owned by OpenAI since March 2026; YAML tests; side-by-side comparison of prompts and models, attacks from `guardrails.md`; the fastest start without code or SDK embedding; language-independent; own config format — leaving means rewriting tests | comparing several models and prompts in an evening; a CI run | complex evaluation of a multi-step agent |
| **Ragas** | open (Apache 2.0) · pop | Python; faithfulness to sources, context precision and recall, answer relevance; the standard entry point for RAG evaluation, often paired with DeepEval (Ragas for retrieval, DeepEval for the rest); **per one report repository activity dropped in 2026 — check the last commit date** | retrieval quality and grounding of answers | an agent with tools but no retrieval |
| **Inspect AI** | open (MIT) · pop | UK AI Security Institute; Python framework: task, solver, scorer; tools run in a sandbox; own log viewer; built for model safety evaluations, good for any serious agent evaluation; stricter and heavier than the rest | comparing models for your task; evaluating an agent that runs code | quick daily product checks |
| **Pydantic Evals** | open (MIT) · grow | Pydantic; Python; datasets and evaluators as typed code; pairs with Pydantic AI and Logfire but works alone; small and clear: dataset, evaluators, report | an agent on Pydantic AI; own checks in plain code | needing a library of ready metrics |
| **Evaluations inside platforms** | open (various) · pop | Langfuse, Phoenix, Opik, LangSmith; evaluation tied to the trace, a dataset from production in two clicks; the platform samples traces and scores them — most convenient for live traffic; platform lock-in. **Checks that must block a release belong in code and git** | evaluation on live traffic; example sets from real dialogues | a release gate (its place is in CI) |

### METHOD — how to evaluate
The tools above only run checks; methods decide what to check and what to trust. **Order matters: from cheap and reliable to expensive and noisy.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Error analysis by eye** | open (technique) · base | open traces in a row and write one sentence per trace on what is wrong → a list of failure types with frequencies; repeat after every big change. **Start here, not with choosing metrics:** ready metrics like "helpfulness on a scale" rarely match what actually breaks for you; usually three to five frequent failures show up, each gets its own check | the start of any quality work | no case where it is redundant |
| **Example set** | open (technique) · base | a file in git or a platform dataset; from real requests, found failures, edge cases; store input, expected outcome or criterion, expected tools; start with dozens, grow from failures. **The main value of the whole evaluation system:** examples from the developer's head test what was already foreseen; production examples test what actually happens; mask personal data in the set | any agent | no case where it is redundant |
| **Checks in code** | open (technique) · base | plain assertions: answer matches schema; the right tool was called; arguments correct; no forbidden strings; a source link present; zero cost, deterministic; the first layer, runs on every trace. **"The agent issued a refund without checking the order" is a code check over the trace, not a question for a judge** | any agent with tools and structured output | judging tone and meaning of free text |
| **Calibrated judge model** | open (technique) · pop | a narrow yes/no question, not a 1–5 scale; calibrated against human labels on the same examples, agreement corrected for chance; known biases: towards the first option, the longer answer, its own model family. A raw judge score is a measurement without an error bar; **the judge cannot be more accurate than its teachers**; recalibrate on any change of judge model, prompt or task; high agreement between several judges says nothing about agreement with humans | faithfulness, completeness, tone, appropriateness | anything checkable in code; a criterion humans themselves disagree on |
| **Agent path evaluation** | open (technique) · pop | checks over the trace: tool choice, arguments, order, step count, repeats and loops; tool errors separately even if the task was finally solved. **An agent that gave the right answer by a wrong path failed silently — next time the lucky recovery will not happen.** Growing step count for the same task week over week is an early sign of degradation | any agent with tools | a chat without actions |
| **Live-traffic evaluation** | open (technique) · pop | a background job or platform feature: code checks on the whole stream, the judge on a sample (expensive); catches what is not in the example set — new phrasing, a new product, a provider-updated model; **a nightly run over yesterday's traces shows degradation in a report, not in a client complaint** | an agent in production | a prototype without users |

### RELEASE — versions and rollout
Prompt, tool set and model change more often than code and break things harder. Treat them as code: version, pre-release check, gradual rollout, rollback.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Prompts in git** | open (technique) · base | version the system prompt, tool descriptions, skills, the model-registry entry; the version of each part goes into the trace; a prompt change goes the same path as a code change and runs the same checks; the simplest and most reliable option for a developer team | developers edit the prompts | prompt editors without git access |
| **Platform prompt registry** | open (various) · pop | Langfuse, Opik, LangSmith, Braintrust, MLflow: versions, "prod"/"test" labels, playground, version ↔ traces link; convenient when a domain expert, not a developer, edits the text; **risk: changes bypass review and checks** — move the "prod" label only after an eval run; the agent caches the prompt and survives the platform being down | analysts or experts edit prompts | a small developer team (git is enough) |
| **CI gate** | open (technique) · base | a CI step on any change of prompt, tool, model or skill; threshold "no worse than the current version on key checks" — **compare with what is in production, not an absolute number**; Promptfoo, DeepEval or an own script; a fast set on every change, the full set before release; attack runs from `guardrails.md` go here too | any agent in production | no case where it is redundant |
| **Gradual rollout** | open (technique) · pop | flags or gateway routes: traffic share → observe → widen or roll back; watch task success, handoff share, cost, complaints; the example set does not cover everything, so real traffic is the final check; **rollback is moving a version label, not a new release** | a customer agent with noticeable traffic | an internal tool for ten people |
| **Model change** | open (technique) · base | when the provider updates or retires a model, or a cheaper one appears: a full eval run on the new model, then gradual rollout; **pin the exact model version, not a "latest" alias**; a prompt written for one model behaves differently on another; the gateway's fallback model passes the same evaluations in advance, not on the day of the outage | any agent | no case where it is redundant |

### FEEDBACK — feedback and metrics
What closes the loop: signals from people go back into the example set and the prompt. Plus a few numbers that show the agent's health without reading traces.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **User signals** | open (technique) · base | events tied to the trace; explicit — thumbs up/down, complaint; implicit — re-asked, asked for a human, abandoned the dialogue, **the operator rewrote the answer** (the most valuable: a ready reference answer); rating buttons are pressed by a small share, mostly the unhappy; implicit signals are in every dialogue | any agent with users | no case where it is redundant |
| **Labelling queue** | open (technique) · pop | platform feature or Label Studio, Argilla; gets negative signals, low scores **and a random sample** (otherwise you never learn of failures no check caught); output: label, failure type, correct answer; the same labels are the reference for judge calibration | a domain expert ready to spend an hour a week | nobody to label (then at least error analysis by eye) |
| **From failure to dataset** | open (technique) · base | found a failure → added an example → confirmed the check fails → fixed → the check passes; **the same day**; the same order as a bug in ordinary code: first a test that catches it; after six months the set knows more about the product than any document | any agent | no case where it is redundant |
| **Agent metrics** | open (technique) · base | five numbers on one dashboard: quality — share of solved tasks; money — **cost per solved task**; speed — worst-case latency, not the mean; people — handoff share and appropriateness; safety — guardrail triggers and policy denials. Cost per request lies: an agent that solves a task in three tries is cheap per request and expensive per result; slice everything by task type and channel — an overall number hides a failure in one scenario | any agent in production | no case where it is redundant |
| **Alerts** | open (technique) · pop | rules in the observability system: rising tool errors, rising step count, falling solved share, cost spike; linked to the kill switch (`guardrails.md`); quality alerts are noisier than server errors — thresholds on a sliding window and compared with last week | an agent in production without constant supervision | little traffic (statistics will not accumulate) |

## Clouds

Traces hold whole prompts and answers, i.e. client correspondence. **For Kazakhstan data the trace platform is self-hosted, or text is masked before sending.** Requirements must be checked with a lawyer.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Managed ClickHouse and PostgreSQL | no ready agent trace platform found; storage for a self-hosted Langfuse | trace platform in-house |
| | Object Storage | attachments and exports | part of the Langfuse install |
| | Monitoring | metrics and alerts | latency, errors, cost |
| DigitalOcean | Managed Databases + App Platform | Langfuse, Opik, a collector on Droplet or App Platform with managed DBs | trace platform in-house |
| | Evaluations in Gradient | basic traces and checks for platform agents | an agent fully in Gradient |
| Railway | service from Docker + Postgres and Redis | Langfuse, Phoenix, a collector in the agent's project; ClickHouse for Langfuse as a container | quick start |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | AgentCore Observability (agent traces to CloudWatch in OTel format); Bedrock Evaluations (models and RAG, incl. judge models); CloudWatch metrics and alerts |
| Google Cloud | Cloud Trace (agent traces for ADK); Gen AI evaluation service (answers and agent path, ready and custom metrics) |
| Azure | Foundry Observability (traces and dashboards in Application Insights); Foundry evaluators (quality and safety, incl. continuous evaluation on live traffic) |
| Cloudflare | AI Gateway log (model requests with cost and latency — **a call log, not an agent trace: tool steps do not get in**); Workers Observability |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Where to start quality work | read a hundred traces and list failure types | — |
| Trace platform on own server | Langfuse | nobody to run four services → Phoenix; licence without an enterprise part → Opik |
| Debugging on your machine | Phoenix | — |
| Agent on LangGraph, cloud acceptable | LangSmith | data must stay in-house → Langfuse |
| Not tying to one platform | OpenTelemetry through own collector | field names: OpenInference now, `gen_ai.*` for the future |
| Client data in traces | masking in the collector before writing | — |
| First automatic checks | code checks over the trace | — |
| Evaluate what code cannot check | yes/no judge model calibrated against humans | humans disagree → refine the criterion |
| Evaluations next to Python tests | DeepEval | own checks without extras → Pydantic Evals |
| Compare models and prompts quickly | Promptfoo | strict comparison with a sandbox → Inspect AI |
| Knowledge-base retrieval quality | Ragas | — |
| Do not ship a regression | CI gate | plus gradual rollout |
| Notice degradation in production | live-traffic evaluation and alerts | — |
| Is the agent healthy | five metrics: solved tasks, cost per task, latency, handoffs, protection triggers | — |
