# Layer: AI infrastructure

Source: Alexey's «ИИ-слой» (checked 30 October 2026). Infrastructure around models: inference servers, LLM gateways, agent infrastructure (MCP gateways, memory, sandboxes), LLM observability and evaluation, MLOps. Vector databases are in `databases.md`; durable execution for agents is in `background.md`. **This layer changes faster than the others — re-check it every few months.**

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **Throughput and latency.** TTFT = time to first token (what the user feels). Tokens/s per request = typing speed. Throughput per GPU = concurrent requests. Continuous batching and PagedAttention raise throughput several times.
- **KV cache and prefixes.** The model keeps "memory" of the context it read in the KV cache. Requests sharing a prefix (system prompt, RAG documents, agent history) can reuse it — **the main speed and cost lever for agents**.
- **AI supply chain.** In 2026 attackers hit AI tools: a malicious LiteLLM on PyPI stole provider keys, cloud credentials and Vault tokens. **An LLM gateway holds every key at once — the most valuable target in the stack.**

## Rule 0

Do not run your own inference until you have done the maths: a provider API is almost always cheaper under irregular load. Own GPUs pay off with constant load, data requirements, or your own fine-tuned models. **All LLM calls go through one gateway** (keys, limits, logs, fallbacks), with tracing and quality evaluation from day one. **Pin AI-stack dependencies by version and hash.**

## Classes and technologies

### INFER — inference servers
Run models behind an OpenAI-compatible API. Techniques: continuous batching, PagedAttention, prefix cache, quantisation (FP8, AWQ, GGUF), speculative decoding, tensor parallelism.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **vLLM** | open (Apache 2.0, PyTorch Foundation) · base | NVIDIA, AMD, Intel, TPU, AWS Neuron; widest Hugging Face model support incl. multimodal; PagedAttention, prefix caching, FP8, **many LoRA adapters on one base model hot-swapped**, structured output; Hugging Face itself recommends it as the TGI replacement | production inference on own GPUs; many LoRA adapters on one model (hot-swapping personas); large batch processing | a laptop or one weak GPU (llama.cpp or Ollama are simpler) |
| **SGLang** | open (Apache 2.0) · pop | NVIDIA, AMD; RadixAttention (prefix-cache tree) cuts TTFT by 20–40% when over half the prompt is shared; fast structured output; otherwise ≈ vLLM | agents with long shared history; RAG over repeated context | exotic models (vLLM supports more) |
| **llama.cpp** | open (MIT) · base | CPU, Metal, CUDA, Vulkan, ROCm; GGUF with 2–8-bit quantisation (a 12B model in 16 GB VRAM); llama-server, grammars, speculative decoding; base of Ollama, LM Studio and many edge solutions | local models on a laptop or workstation; edge and offline devices | high concurrency on data-centre GPUs |
| **Ollama** | open (MIT) · pop | wrapper over llama.cpp with a model catalogue, Modelfile, `pull`/`run`, tool calling, embeddings; own + OpenAI API. **Listens without auth by default — never expose the port** | development and prototypes; a local assistant on your own GPU | high-load production; an internet-facing port without an auth proxy |
| **NVIDIA Dynamo / Triton** | open (Apache 2.0 / BSD-3) · pop | NVIDIA only; Dynamo splits prefill and decode across GPUs and routes by KV cache, over vLLM, SGLang, TensorRT-LLM; Triton serves any ML models (CV, speech, recsys); OpenAI API, gRPC | large GPU clusters; mixed ML models in one server (Triton) | one or two GPUs |
| **TGI** | open (Apache 2.0, **archived**) · base | maintenance mode December 2025, archived 21 March 2026; migrate to vLLM (`--num-shard` → `--tensor-parallel-size`) | old installs during migration only | any new project |

### LLM-GW — LLM gateways and routing
One API to all providers and own models: virtual keys per team, budgets and token limits, provider fallbacks, cache, logging, guardrails. **The gateway holds all provider keys, so isolation and version pinning are critical.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **LiteLLM** | open (MIT + Enterprise) · pop | Python SDK + proxy; 100+ providers; virtual keys, budgets, fallbacks, cache, logging, guardrails. **March 2026: PyPI versions 1.82.7 and 1.82.8 were malicious** (TeamPCP, the Trivy attackers; `litellm_init.pth` ran on every Python start); proxy Docker images reportedly unaffected thanks to pinned versions | one team access point to many providers; cost tracking per team and project | installs without pinned versions and hashes; a gateway with access to unrelated env secrets |
| **Bifrost** | open (Apache 2.0) · grow | Go binary, no Python deps at runtime; virtual keys, RBAC, guardrails, audit, **LLM + MCP gateway**; microsecond overhead claimed mostly by the vendor | low overhead at high RPS | LiteLLM's huge integration ecosystem |
| **Portkey Gateway** | open (MIT gateway) · pop | small fast TypeScript gateway, runs at the edge; fallbacks, retries, balancing, cache, guardrails; observability and prompt management in the paid platform | a gateway at the edge or in serverless | everything self-hosted including analytics |
| **Envoy AI Gateway** | open (Apache 2.0) · grow | on Envoy Gateway CRDs; OpenAI, Bedrock, Azure, Vertex…; token limits, routing, authz, MCP | a k8s platform already on Envoy Gateway (same stack for normal and AI traffic) | no Kubernetes |
| **OpenRouter** | prop (SaaS) · pop | hundreds of models from many vendors, one key and bill, automatic provider choice; data passes through an intermediary | experiments and model comparison | sensitive customer data |

### AGENTS — agent infrastructure
Everything an agent needs besides the model: tool access through **MCP** with authorization, long-term memory, isolated code execution.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **agentgateway** | open (Apache 2.0, Linux Foundation) · grow | Rust MCP gateway and A2A proxy between agents and MCP servers; JWT, OIDC, mTLS, policies; HTTP, SSE, gRPC; one point of authz, audit, routing | many agents and MCP servers in a company | one agent with a couple of local tools |
| **IBM ContextForge** | open (Apache 2.0) · grow | Python MCP registry and gateway with admin UI; **publishes existing REST/gRPC APIs as MCP tools** without writing a server; 35+ plugins incl. PII filtering | quickly opening internal APIs to agents | minimal latency (Rust/Go gateways are faster) |
| **Docker MCP Gateway** | open (Apache 2.0) · pop | each MCP server in its own container with limited file access; stdio, SSE, Streamable HTTP; developer-machine oriented | safe agent work with third-party MCP servers on a dev machine | multi-node production |
| **Mem0 / Letta / Zep (Graphiti)** | open (Apache 2.0) · grow | Mem0 extracts facts into a vector DB and graph; Letta (ex-MemGPT) is an agent managing its own memory; Graphiti builds a **temporal knowledge graph** (facts with appear/expire dates); SDK, API, MCP; changing fast | personal assistants that remember the user; a fact graph about contacts | needing a predictable schema (a plain facts table is simpler) |
| **E2B / Daytona** | open (Apache 2.0 / AGPLv3) · grow | on-demand isolated VMs/containers starting in fractions of a second, destroyed after; E2B on Firecracker microVMs; cloud + self-hosted. **Without this, LLM-generated code runs next to your secrets** | code interpreters, analyst agents, vibe-coding platforms | trusted code (extra overhead) |

### LLM-OBS — LLM observability and evaluation
Traces of model calls and agent steps, cost, latency, versioned prompts, datasets, automatic evaluation (LLM-as-a-judge), red teaming. **Without it agent quality is judged by eye.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Langfuse** | open (MIT core) · pop | traces, cost, sessions, versioned prompts; datasets, LLM-as-a-judge, manual labelling; OTel, LangChain, LlamaIndex, OpenAI SDK, LiteLLM; Postgres + ClickHouse; bought by ClickHouse in January 2026, no licence change planned, self-hosting stays primary | tracing and evaluating any LLM app; prompt management | — |
| **Arize Phoenix** | src (Elastic License 2.0 — no managed-service offering) · pop | OpenInference/OTel traces, built-in evals, experiments; SQLite/Postgres; good in notebooks | researching and debugging RAG and agent quality | needing an OSI licence |
| **Helicone / OpenLIT** | open (Apache 2.0) · pop | Helicone = proxy (change base URL, see all requests); OpenLIT = OTel SDK incl. GPU metrics into Grafana/SigNoz; ClickHouse; basic evals | seeing LLM spend fast; LLM metrics in an existing OTel stack | deep quality evaluation |
| **promptfoo** | open (MIT) · pop | YAML test cases, model comparison, attacks (prompt injection, jailbreak, leaks); CI/CD; local; bought by OpenAI in March 2026 | prompt quality regression in CI; red teaming agents | production monitoring (that is Langfuse) |

### MLOPS — experiments, registries, features
Experiment tracking, model registry with versions and stages, **feature store** (same features in training and production). Needed when you train or fine-tune your own models.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **MLflow** | open (Apache 2.0, Linux Foundation) · base | tracking, model registry, deploy; MLflow 3 adds agent tracing and GenAI evals (overlaps Langfuse); Postgres + S3 | training and fine-tuning own models; a versioned model registry | only calling external APIs (Langfuse fits better) |
| **Weights & Biases** | prop (SaaS, self-managed exists; bought by CoreWeave in 2025) · pop | experiments, artifacts, sweeps, Weave for LLMs; best training visualisations; research standard | team research and model training | data that cannot leave, with self-managed too expensive |
| **ClearML** | open (Apache 2.0) · pop | experiments, **GPU job queues** (agents on GPU machines pull tasks), datasets, serving; own server | own GPU fleet without Kubernetes | LLM APIs only |
| **Feast** | open (Apache 2.0) · pop | offline store (DWH) + online store (Valkey, Postgres); guarantees "purchases in 30 days" is computed the same in training and production | real-time recommendations and scoring, anti-fraud | LLM-only work without tabular features |

## Clouds

Almost every platform exposes an OpenAI-compatible API, so **going through your own gateway means code does not change on a move**. They differ in model set, GPU availability and where data is processed.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | AI Studio | YandexGPT and open models, OpenAI-compatible API, assistants/agents, RAG, fine-tuning; data processed in Yandex infrastructure | LLM with data in Russian jurisdiction |
| | DataSphere | notebooks, GPU training, model deploy | training and fine-tuning |
| | Compute Cloud (GPU) | GPU VMs | own vLLM |
| | SpeechKit | STT and TTS | voice agents |
| DigitalOcean (Gradient) | GPU Droplets / Bare Metal GPUs | GPU machines | own vLLM, fine-tuning |
| | Gradient Platform | agents, RAG, function calling, serverless models, built-in evals | quick agents without own infrastructure |
| | Knowledge Bases / Inference Engine | knowledge base and serverless inference | RAG and model calls |
| Railway | CPU services | LiteLLM, Langfuse, agents, MCP servers | the stack around models |
| | Qdrant / pgvector templates | vector search | RAG |
| | (**no confirmed GPU** — requested on the forum, absent from pricing) | models stay with a provider or a GPU cloud | — |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Bedrock (Anthropic, Meta, Mistral, Amazon models; Guardrails, Knowledge Bases — data stays in the account); Bedrock AgentCore (runtime, memory, gateway, identity for agents); SageMaker; EC2 GPU / Trainium / Inferentia |
| Google Cloud | Vertex AI (Gemini, Model Garden); Agent Engine / ADK; Cloud Run GPU / GKE / TPU |
| Azure | AI Foundry / Azure OpenAI (+ catalogue, evals, content filters; data regions and Entra ID matter for enterprise); Foundry Agent Service; AKS / ND-series GPUs |
| Cloudflare | Workers AI (open models serverless on edge GPUs); AI Gateway (cache, limits, logs, fallbacks for any provider); Vectorize / AI Search; Agents SDK (stateful agents on Durable Objects with MCP) |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| LLM calls in a product | provider API through our own gateway | constant load, own models or data requirements → own vLLM |
| Own inference on a GPU server | vLLM | agents with shared prefixes → SGLang; large cluster → Dynamo |
| Local model on own GPU | Ollama (dev) / llama.cpp (edge) | high concurrency → vLLM |
| Leaving TGI | vLLM | — |
| Hot-swapping LoRA adapters | vLLM multi-LoRA | — |
| One model gateway for the team | LiteLLM with pinned versions | minimal overhead → Bifrost; k8s on Envoy → Envoy AI Gateway; on Cloudflare → AI Gateway |
| Agent access to company tools | MCP gateway (agentgateway or ContextForge) | developer machine only → Docker MCP Gateway |
| Agent memory about the user | own facts table in Postgres | temporal knowledge graph → Graphiti; ready API → Mem0 |
| Running agent-generated code | E2B or Daytona sandbox | own microVMs |
| Tracing and evaluating an LLM app | Langfuse | metrics in an existing OTel stack → OpenLIT |
| Prompt regression and red teaming | promptfoo in CI | — |
| Training and fine-tuning own models | MLflow | own GPU fleet without k8s → ClearML; research → W&B |
| Real-time recommendations and scoring | Feast + Valkey | — |
| LLM with data in Russian jurisdiction | Yandex AI Studio | own models on Yandex Compute GPUs |
