# Agent layer: model gateway

Source: Alexey's «Шлюз моделей» (map 5 of 8, checked 13 November 2026; prices, provider counts and speed numbers in reviews are mostly vendor-claimed, so they are mostly left out). One point between your code and all models: open and cloud gateways, picking a model per request, three kinds of cache, limits and budgets, servers for your own models. Why the layer exists is in `../base.md` (mechanisms M1–M5); MCP gateways for tools are in `tools.md`; inference internals in `architecture-guide` → `layers/ai.md`.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **The gateway holds every key.** Every request passes through it and it stores every provider key — the main attack target. **In 2026 the release of LiteLLM, the most popular open gateway, was replaced twice with a credential-stealing version: in March and in October.**
- **Three caches, three risks.** The provider's prefix cache makes a repeating prompt start cheaper and cannot be wrong. An exact cache returns the answer to a verbatim identical request. A semantic cache returns the answer to a *similar* request and can be confidently wrong. **Turn them on in this order.**
- **Count tokens and money.** A request-count limit does not protect the budget: one agent request can cost as much as a thousand ordinary ones. Working scheme: a virtual key per team, product or user, a limit in tokens or money, and clear behaviour on exhaustion.

## Rule 0

Agent code does not know model names or provider keys: it asks for "fast" or "smart", and the gateway decides. **Pin the gateway version by hash and update through a check.** Keep provider keys in a secrets store, short-lived and narrow. Prefix cache and simple model-selection rules first; smart routing only afterwards.

## Classes and technologies

### LLMGW — open model gateways
A self-hosted proxy: one OpenAI-format API outside, provider keys, fallback models, cost accounting and cache inside. Data does not go to a third party. The main difference between them: provider coverage versus speed and ease of operation.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **LiteLLM** | open (MIT, open core) · pop | Python library and proxy; 140+ providers; virtual keys, budgets per key / user / team, fallbacks, cache; provider keys in PostgreSQL; the de-facto self-hosted standard. **2026 was hard: in March and October credential-stealing versions shipped through its own release pipeline, and in June a vulnerability chain allowing proxy takeover was disclosed**; the `enterprise` folder is licensed separately | many different providers behind one API; team budgets without a paid tier | updating without pinned versions; high load where gateway milliseconds matter |
| **Bifrost** | open (Apache 2.0, open core) · grow | Maxim AI; Go single binary; fallbacks, hierarchical budgets, exact and semantic cache, **MCP gateway**, complexity-based routing; microsecond overhead per the vendor's own test; named the best choice for most teams in an independent autumn 2026 comparison of open gateways; fewer providers than LiteLLM. Speed numbers come from the owner, and half the market reviews are written by them | a new project without LiteLLM legacy; load where gateway latency is noticeable | a rare provider; SSO and advanced management (paid tier) |
| **Portkey Gateway** | open (MIT) · pop | TypeScript server, runs at the network edge too; owned by Palo Alto Networks since May 2026; config routes, guardrails, PII hiding, logging; strength is control, not speed; the open repo slowed after the acquisition (moving into Prisma AIRS) | guardrails right in the gateway; when the paid Portkey cloud is planned | betting on a long life of the open version |
| **Helicone AI Gateway** | open (Apache 2.0) · pop | Rust server and cloud; logs every request, cost, cache; **maintenance mode after the company was acquired** — taken for observability, the gateway comes along; do not expect new features | already in use and satisfactory | a new project (take a live gateway and separate observability) |

### APIGW — on top of an API gateway
If the company already runs Envoy, Kong or APISIX, model traffic goes there. Gain: auth, network and observability are already set up. Loss: money accounting and budgets are usually weaker than in gateways grown from the model side.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Envoy AI Gateway** | open (Apache 2.0) · grow | Envoy Gateway extension for Kubernetes, 1.0 since June 2026, started by Tetrate and Bloomberg; configured with Gateway API resources; quotas in tokens per route and backend; **no money budgets out of the box** — build them yourself | a platform team with Envoy and Kubernetes | no Kubernetes; team budgets without own work |
| **agentgateway** | open (Apache 2.0) · grow | Rust, Linux Foundation; model routes, per-key budgets, CEL policies; covers models **and** tools at one point (as an MCP gateway see `tools.md`) | one gateway for models and tools | needing a ready management UI |
| **Kong AI Gateway** | src (open core) · pop | plugins for Kong Gateway: model routes, semantic cache, moderation; **token limits only in the paid version** | companies standardised on Kong | a small team; free token limits |
| **Apache APISIX** | open (Apache 2.0) · pop | API gateway; proxy to several providers, token limits via a plugin; budgets are your own work; fully open Kong alternative — does less than model gateways but hides nothing behind a tier | one open gateway for both APIs and models | per-team cost accounting out of the box |

### HOSTED — cloud gateways
A gateway as a service: one key, hundreds of models, nothing to deploy. **The price: every prompt and answer passes through one more company.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenRouter** | prop (SaaS) · pop | 500+ models from 80+ providers, one bill with a top-up mark-up, Auto Router; picks the provider for open models by price and availability; per one report bought by Stripe in August 2026 | prototyping and comparing models; models without a contract with each provider | client personal data; controlling where a request physically went |
| **Cloudflare AI Gateway** | prop (SaaS) · pop | main features free with your own keys; cache, fallbacks, logs, DLP, spend limits (open beta); connects by changing the base URL; **its rate limit counts requests, not tokens** — protect the budget with separate spend limits | a product already on Cloudflare; a gateway in five minutes for free | data that must not cross a foreign network; per-team budgets |
| **Vercel AI Gateway** | prop (SaaS) · pop | no token mark-up; pairs with AI SDK and Vercel apps; few advantages outside that stack | Next.js and AI SDK | a Python backend; self-hosting |

### ROUTE — picking a model per request
Most requests do not need the most expensive model. Routing decides **before** the call which model will cope. Signals go from simple to complex: rules, embedding similarity, a trained router. **Savings in articles come from benchmarks; yours depend on your request mix.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Rules and aliases** | open (technique) · base | gateway configuration; signals: task type, channel, length, user plan; aliases `fast`, `smart`, `vision` instead of model names; classifying a request goes to a cheap model, a complex contract review to a strong one — known in advance, no judge model; **covers most of the saving and does not break** | any agent, from day one | one stream of requests of very different complexity |
| **Cascade** | open (technique) · base | cheap model first, expensive only on failure; switch condition = an answer check (schema, confidence, rule); double latency on hard requests; **works only when answer quality can be checked automatically** (passed the schema, citations found, the sum matches) — without such a check a cascade is a lottery | data extraction and classification with a verifiable result | a live chat where speed matters; nothing to check the answer with |
| **Semantic Router** | open (MIT) · pop | Aurelio, Python; compares the query embedding with examples per route, milliseconds, no big-model call; also for choosing an agent branch or a fast refusal on a forbidden topic | a dozen clear request types with examples | blurred, frequently changing request types |
| **RouteLLM** | open (Apache 2.0) · pop | LMSYS library and local server; predicts whether the weak model will cope against a cost threshold; up to 85% saving at 95% of the strong model's quality on one benchmark, **35–45% on others in the same paper**; trained on old model pairs — re-check on your data for new ones | a large homogeneous stream with an evaluation set | little traffic (savings will not cover the work) |
| **Built-in auto-routers** | prop (SaaS) · grow | OpenRouter Auto Router, Not Diamond, Azure Model Router, Bedrock Intelligent Prompt Routing; own classifiers, usually closed; **an academic check in early 2026: several routers, incl. a commercial one, did not beat the simple "always the one best model" strategy** — test on your requests | a quick check whether routing saves you anything at all | needing to explain why a request went to this model |

### CACHE — cache
Three mechanisms with one name, working at different levels and failing differently. The prefix cache lives at the model provider; exact and semantic caches in the gateway or your code.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Provider prefix cache** | prop (API feature) · base | caches processing of the prompt start (instructions, tools, documents); the answer is generated anew — nothing to get wrong; requires a byte-exact matching start. **The first thing to switch on. One rule: stable at the start, changing at the end — a timestamp or user name in the system prompt zeroes the hits.** vLLM and SGLang do the same in GPU memory | any agent with a long system prompt and tools | short one-off requests |
| **Exact cache** | open (technique) · base | Redis or the gateway's cache; key = hash of model, prompt and parameters; pays off from about 5% hits; almost free and almost harmless; **the key must include everything the answer depends on: the user or their rights, knowledge-base version, language** | repeating service calls: classification, extraction; background processing with restarts | answers that depend on fresh data without a version in the key |
| **GPTCache** | open (MIT) · pop | Python library that started the category; FAISS, Qdrant, Redis, Milvus…; SQLite by default (change for load); today the gateway's built-in semantic cache (LiteLLM, Bifrost, Kong) over Redis or Qdrant is more common | own code without a gateway | when the gateway already does it |
| **Redis LangCache** | prop (managed) · grow | Redis Cloud service, preview; vector search, TTL on entries; the same mechanism as a service — **user questions sit in a foreign cloud** | Redis Cloud already in use | questions containing personal data |
| **Semantic cache (technique)** | open (technique) · grow | a similar question gets a ready answer — sometimes the wrong one; **the main knob is the similarity threshold, controlling both savings and error rate**; pays off from about 15–20% hits; mandatory: **separate cache per access rights and the source version in each entry**. "How to cancel a booking" and "how to cancel a subscription" are close in embedding and need different answers; a high hit rate at a low threshold means many confident errors | a public FAQ bot with repeating questions | answers with client data; an agent with tools (the answer depends on system state) |

### BUDGET — limits, budgets and the registry
What finance and security install the gateway for. Hardly any separate products: these are gateway functions and techniques to configure consciously.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Virtual keys** | open (technique) · base | a gateway function (LiteLLM, Bifrost, Portkey); per key: allowed models, budget, limits, TTL; **real provider keys stay only in the gateway** — services and developers never see them; a leaked virtual key is revoked alone; gives cost accounting per team and product | more than one service or team calling models | no case where it is redundant |
| **Hierarchical budgets** | open (technique) · base | company → team → product → user; money or tokens per period; on exhaustion: refuse, cheap model or queue; a smart limit counts cost, not requests; **a soft threshold for a customer bot moves the user to a cheap model instead of an error**; a separate ceiling per agent task so a loop does not eat the monthly budget | a customer product with plans; protection against a looping agent | no case where it is redundant |
| **Fallbacks and retries** | open (technique) · base | retry with exponential backoff and jitter, **only for transient errors**; fallback path: another region → another provider of the same model → another model; a circuit breaker takes load off a provider returning errors. **The fallback model must pass the same tests as the main one** — a prompt written for one model can behave differently on another | any agent in production | no case where it is redundant |
| **Model registry** | open (technique) · base | gateway config in git; per model: alias, provider, price, context window, tool and schema support, **where the data is processed**; changes through review and a test run; changing a model becomes a one-line edit; the "where processed" field lets a rule forbid sending personal data to models outside the country | from the first model in the product | no case where it is redundant |

### LOCAL — own models behind the gateway
When data cannot leave, the model is installed in-house and connected to the gateway as one more provider. All servers below expose an OpenAI-format API, so nothing changes for the agent code.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **vLLM** | open (Apache 2.0) · base | Python inference server, NVIDIA and AMD GPUs; continuous batching, high throughput; the production default; needs a dedicated GPU and takes all its memory | a service with dozens of concurrent requests | a laptop or a machine without a GPU |
| **SGLang** | open (Apache 2.0) · grow | reuses the shared prompt start between requests, structured output; beats vLLM with many requests sharing a long start — exactly agents with a big system prompt and tool set | agent load on own hardware | needing the widest model and hardware support |
| **llama.cpp** | open (MIT) · base | C++ engine and `llama-server`; GGUF quantised models; CPU, any GPU, Apple Silicon; the only sensible option without a GPU and the base of Ollama and LM Studio; on one card with light load enough for production | one GPU or none; a small model for masking and classification | many concurrent users |
| **Ollama** | open (MIT) · pop | wrapper over llama.cpp with a model catalogue, one-command install; noticeably slower than vLLM under load; usual chain: Ollama on a laptop, vLLM or SGLang in production, same weights. **TGI is not taken for new projects (maintenance mode since March 2026)** | development and trying an idea | production with parallel load |

## Clouds

A cloud gateway sees every prompt and answer. **For Kazakhstan client data the gateway is self-hosted: it is the convenient place to mask personal data before a foreign model and to send sensitive requests to your own one.**

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | AI Studio Model Gallery, shared instances | YandexGPT and open models (Qwen, DeepSeek, gpt-oss) per token | start without own hardware |
| | dedicated instances | a model on separate capacity | predictable speed |
| | OpenAI-format API | connects to any open gateway as a provider; **no managed gateway with per-team budgets found** | LiteLLM or Bifrost in front of AI Studio |
| DigitalOcean | Gradient Serverless Inference | models per token | no own hardware |
| | GPU Droplets | rented GPUs | vLLM with own model |
| | App Platform | containers | own gateway |
| Railway | service from Docker | LiteLLM or Bifrost next to Postgres and Redis (keys, accounting, cache); **no GPUs** — own models live elsewhere | own gateway in an evening |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Bedrock acts as a gateway to many vendors inside AWS: Converse API (one API), IAM rights, Intelligent Prompt Routing (within a model family), cross-region inference (resilience to limits), prompt caching |
| Google Cloud | Model Garden (Google and partner models behind one entry); Apigee as the gateway with token quotas per consumer in large companies; context caching |
| Azure | Foundry Model Router (one endpoint picks the model); API Management (token quotas, balancing — **not money budgets**); Foundry Models catalogue |
| Cloudflare | AI Gateway (cache, fallbacks, logs, spend limits — a product's first gateway); Workers AI (open models on the same network, small models near the user) |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| First gateway for a small product | Bifrost self-hosted | many rare providers → LiteLLM with a pinned version |
| A gateway in five minutes, non-sensitive data | Cloudflare AI Gateway | AI SDK stack → Vercel AI Gateway |
| Try and compare many models | OpenRouter | — |
| Envoy, Kong or APISIX already in the company | route models through the existing gateway | per-team budgets needed → a dedicated model gateway behind it |
| One gateway for models and MCP tools | agentgateway | Bifrost has an MCP gateway too |
| Cut the bill, step one | prefix cache and prompt ordering | — |
| Cut the bill, step two | rules and model aliases by task type | verifiable result → cascade |
| Cut the bill, step three | exact cache for service calls | public FAQ → semantic cache with a high threshold |
| One stream of requests of varying complexity | RouteLLM checked on own data | quick effect estimate → a service auto-router |
| Limit a user's spend | virtual key and a money budget | past the threshold a cheap model instead of refusal |
| Agent may loop | token ceiling per task | — |
| Provider goes down or throttles | fallback models in the gateway, passing the same tests | — |
| Data cannot leave | vLLM or SGLang behind own gateway | one GPU and light load → llama.cpp |
| Customer data in Kazakhstan | own gateway: masking before a foreign model, sensitive requests to own model | model registry with a "where processed" field |
