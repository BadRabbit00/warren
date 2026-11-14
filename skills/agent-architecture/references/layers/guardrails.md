# Agent layer: protection — PII, guardrails, injection architecture, rights, approvals

Source: Alexey's «Защита агента» (map 6 of 8, checked 13 November 2026; vendor-claimed filter accuracy is deliberately left out). How to lock the agent down: PII masking, input/output guardrails, architecture against prompt injection, agent rights and identity, approvals with a log, attacking yourself. Why the layers exist is in `../base.md` (layers 06 identity/permissions and 07 guardrails, mechanisms M6–M8, N7). Foreign tool and skill risks are in `tools.md`; keys and the gateway in `gateway.md`.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **A filter does not stop injection.** In a 2025 paper twelve published defences that claimed near-zero attack success were broken by an adaptive attacker in more than 90% of cases. Classifiers catch 7–37% of indirect attacks against agents. A filter is useful as one layer and useless as the only one.
- **Rule of two.** In one session an agent may have at most two of three properties: (A) reads untrusted text, (B) has access to private data or systems, (C) can change state or send something out. **All three needed → a human confirms the decision.**
- **Code checks the rights.** The model does not decide whether an action is allowed. Plain code outside does: who the user is, what they delegated to the agent, what amount, what time. "Do not do X" in the prompt is a wish, not access control.

## Rule 0

Design as if the injection has already succeeded: what can the agent do and where can it send it? Keep keys and secrets outside the agent. Close outbound network with an allowlist of addresses. Pass dangerous actions through a rights check in code and a human confirmation. Mask personal data **before the model and before the log**.

## Classes and technologies

### PII — personal data masking
Finds personal data and replaces it before the text goes to the model, search or the log. Two passes: exact rules for anything with a format (numbers, email) and a model for anything without one (names, addresses). **Masking lowers the risk but does not automatically make data anonymised in the legal sense.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Presidio** | open (MIT) · base | Python library and service; Analyzer finds (regex, lists, checksums, NER model, context words), Anonymizer replaces (replace, redact, hash, encrypt); started at Microsoft, moving in 2026 to the independent Data Privacy Stack organisation under the same licence; the built-in model is weak — usually swapped for GLiNER; **Russian and Kazakh need your own model and recognisers** | the base of your own anonymisation core; custom data types and full control | expecting it to find everything in Russian out of the box |
| **GLiNER for PII** | open (Apache 2.0) · pop | NER model on CPU; **entity types are given as a list of words** ("person", "address", "contract number") — no fine-tuning for a new type; variants from Knowledgator, NVIDIA, Gretel, a multilingual one by the author; most trained mainly on English — measure on your Russian and Kazakh texts; plugs into Presidio as the recognition engine | names, addresses, job titles in free text; own server without a GPU | formatted numbers (rules are more reliable and faster) |
| **OpenAI Privacy Filter** | open (open weights) · grow | small local model, eight fixed categories, English first; strong on context; categories cannot be changed | English texts | Russian and Kazakh; custom data types |
| **Own recognisers** | open (technique) · base | own code, usually as Presidio recognisers: **IIN and BIN with check digit**, phones, IBAN, ID numbers, internal client and contract numbers; tested on a labelled set from your own requests. Ready tools do not know Kazakhstan formats; a checksummed format is caught by a rule almost without errors. **The key metric is misses** — how much real data passed unnoticed | any project with Kazakhstan client data | no case where it is redundant |
| **Reversible substitution** | open (technique) · base | before the model "Ivan Petrov" becomes `PERSON_1`, the same across the whole dialogue; after the model, labels are swapped back at the output boundary; the mapping table lives only with you, for the session. Plain redaction breaks meaning (the model cannot tell two mentions are one person); stable labels keep it. **Logs and traces receive the masked text, not the original** | a foreign model with client data; support chat, request triage | tasks that need the data itself (verify a number, compute from a birth date) |

### GUARD — input and output guardrails
Checks around a model call: what came in, what goes out, did the conversation drift. Some are rules, others are themselves a judge model. **All are probabilistic: they lower the frequency of problems and guarantee nothing.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **NeMo Guardrails** | open (Apache 2.0) · pop | NVIDIA, Python; rules in its own language Colang; rails on input, dialogue, retrieval, **tool call**, output — the only open one reaching the action level, not just text; price: a separate language and the heaviest setup; some rails make extra model calls | a multi-turn chat with hard topic limits; checks before a tool call | a small team and a simple bot |
| **Guardrails AI** | open (Apache 2.0) · pop | Python; dozens of ready validators assembled in code; closer to answer-quality checks than security: format, forbidden topics, grounding in sources; does not check tool calls as a separate entity | strict answer requirements in a customer channel | protecting an agent with tools |
| **Llama Guard and PromptGuard** | src (Llama licence) · pop | Meta judge models run in-house; Llama Guard labels input/output safe or not by category list; PromptGuard 2 is a small injection/jailbreak classifier; data stays on your server; licence not fully open. **2026 check: both transferred poorly to new attack sets and almost missed injections via tools** | content moderation in-house, without an external API | the only defence against injection |
| **LlamaFirewall** | open (MIT) · grow | Meta, Python; layers PromptGuard 2, **AlignmentCheck** (watches whether the agent's reasoning was led away from the user's task — looks at what the agent is about to do, not the input text), CodeShield (checks code the agent writes) | an agent with tools on own infrastructure | a simple chat without actions |
| **Lakera Guard** | prop (SaaS) · pop | API, container variant exists; Check Point since 2025; injections, jailbreaks, system-prompt leaks; most often named the best injection detector in overviews; text only — does not cover tool rights or identity; **the request text goes to an external service** | a strong ready detection layer where an external service is allowed | client data that cannot be sent out |
| **LLM Guard** | open (MIT) · pop | Python, 30+ scanners (injections, secrets, toxicity, PII); **repository archived since July 2026** — after Palo Alto Networks bought Protect AI development moved to the paid product; the code works but gets no updates | already in use and pinned | a new project |

### ARCH — architecture against injection
Techniques that do not try to tell a bad instruction from a good one. The system is built so untrusted text **cannot trigger a dangerous action**. Each technique takes something away from the agent — that is the protection.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Rule of two** | open (technique) · base | design rule, Meta, October 2025; properties: untrusted input; access to private data; changing state or sending out; all three only with a human in the loop; extends Simon Willison's "lethal trifecta" (which covered only exfiltration) to data corruption. **Simplest project check: write down for each agent which of the three it has** | reviewing any agent before launch | no case where it is redundant |
| **Action selector** | open (technique) · base | the model turns a request into one of pre-described calls; **the tool result is not returned to the model**; the strictest of six patterns from a 2025 paper — injection has nowhere to land, the model reads only the user's request | a customer bot: book, cancel, show status | tasks where the agent must reason over what it found |
| **Plan then execute** | open (technique) · base | the agent decides which tools and in what order while the context holds only the user's request; then plain code executes the plan; **untrusted text cannot add a new step** (an injection in an email cannot make it send another email if that was not in the plan); remaining risk: argument substitution inside an allowed step | multi-step tasks of a known shape | tasks where the next step depends on what was found |
| **Dual LLM** | open (technique) · base | Willison, 2023; a privileged model sees the request and tools but never untrusted text; a quarantined model reads untrusted text and has no tools; they communicate **through variables, not text** — the quarantined one can be fooled but can do nothing | email, documents, web pages as a data source for actions | plain search over your own verified base |
| **CaMeL** | open (Apache 2.0) · grow | Google DeepMind 2025 research implementation; the privileged model writes code, a custom interpreter tags every value with its source and checks policies ("recipient address cannot come from an untrusted source"); 77% tasks solved vs 84% without defence in AgentDojo; **the first defence with provable properties, not a detection percentage**; no product, but the provenance-tag idea can be moved into your code | an agent with access to email, files and payments; understanding what real protection looks like | a quick launch (research code) |
| **Closed egress** | open (technique) · base | network allowlist for the agent and sandbox; **do not render images and links to foreign domains in the answer**; the recipient address only from a trusted source; most known agent leaks went one way — the model put data into an image or link URL. If the agent physically cannot reach an arbitrary address, the trifecta loses its third side | any agent with access to private data | no case where it is redundant |
| **Spotlighting untrusted text** | open (technique) · pop | in the prompt: delimiters, encoding, a "this is data, not instructions" label; cheap, helps a little against random and mass attacks; **broken in more than 95% of cases by an adaptive attack** — turn it on, never rely on it | a free extra layer | the only defence |

### AUTHZ — agent rights and identity
An agent is neither a user nor an ordinary service: it acts on someone's behalf, for a limited purpose and a limited time. Authorisation engines answer "is this action allowed" outside the model. **One shared service account for all agents breaks both least privilege and incident analysis.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenFGA** | open (Apache 2.0) · pop | CNCF, created at Auth0; ReBAC after Google Zanzibar; conditions (amount limits, time, context) inside the check; fits delegation well ("the agent acts for Aliya", "Aliya manages this client"); "refund up to an amount" is expressed in the rights model itself; **the same engine filters documents at search time** | rights that depend on who is whom to whom; one engine for the agent and knowledge-base search | simple roles for three user groups |
| **Open Policy Agent** | open (Apache 2.0) · base | CNCF; server and library, Rego; already in Kubernetes, API gateways, CI — write agent tool policies there too; Rego is powerful but hard to read; relationship rules are expressed worse than in OpenFGA | a platform team with OPA; policy as code next to the rest of the infrastructure | rights over a relationship graph |
| **Cedar** | open (Apache 2.0) · pop | AWS; language and engine in Rust; readable policies (who, which action, on what, under which condition) with automatic contradiction analysis; easy to show to security and auditors; AWS's managed authorisation service is built on it | policies that non-developers must read | needing a ready UI and integrations without assembly |
| **Cerbos** | open (Apache 2.0) · pop | authorisation server with YAML policies and conditions; easy start, policies in git tested as code; fewer capabilities than OPA, lower entry bar | a small team moving rights out of application code | complex relationship-based rights |
| **Identity and delegation** | open (technique, OAuth standards) · base | the token carries the agent as actor, the user as subject, purpose and expiry (minutes, per task); **agent rights = intersection of the user's rights and what this agent is allowed**; the other side sees "agent X for user Y", not an anonymous service account; agent rights can be revoked without touching the person | an agent working with different users' data | no case where it is redundant |
| **Keys outside the agent** | open (technique) · base | a tool gateway checks the policy and **injects credentials itself**; the agent sees only the call result. A short-lived key in a hijacked agent is still a working key; if there is no key in the agent's environment there is nothing to steal; same idea as the model gateway's virtual keys, for tools | any agent with access to payments, email, databases | no case where it is redundant |

### APPROVE — approvals and the log
The last line: a human before an irreversible action and a record of what happened. Few products here — these are techniques built into the agent loop and tools.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Confirmation before an action** | open (technique) · base | a pause in the loop; show the action, its arguments, where the data came from, what will change; for irreversible, money, external sending, bulk changes. **Approvals work while they are few: a human pressing "yes" fifty times a day stops reading** — confirm by risk level, show concrete values, not the model's retelling | refunds, payments, mailings, deletion | reads and drafts (there it only gets in the way) |
| **Action risk levels** | open (technique) · base | a field in the tool description: read → immediately; reversible write → with a limit and log; irreversible or external → only with confirmation; **the level is set by a human when the tool is added, not by the model at run time**; limits come from the same place: amount, recipients, records per call | any agent with write tools | no case where it is redundant |
| **Decision log** | open (technique) · base | append-only store: user, agent, tool, arguments, policy decision, who confirmed, prompt and model versions; **no raw personal data**; retention by law and contract; not the same as debugging traces (`evals.md`) — shorter, kept longer, never rewritten; policy violations and guardrail triggers go here too — they show the agent is being attacked | customer and financial agents; incident analysis and audits | no case where it is redundant |
| **Kill switch** | open (technique) · base | a flag in the gateway or config at three levels: whole agent, one tool, one user; automatic on a spike of cost, errors or policy denials; needed at the worst moment, so built and tested in advance; **disabling one tool is more useful than a full stop** — the agent keeps answering but cannot pay | any agent in production | no case where it is redundant |

### REDTEAM — testing protection by attack
Tools that attack your agent before others do. The result is not "vulnerable or not" but **the share of successful attacks per category**. Ready sets test common weaknesses; attacks on your prompt, tools and data you write yourself.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **garak** | open (Apache 2.0) · pop | NVIDIA CLI; runs a catalogue of ready probes and counts failures — like a vulnerability scanner: wide, fast, known patterns; fits CI worse than Promptfoo; does not adapt to your business logic | a first wide check of a model or bot | attacks on the agent's specific tools |
| **PyRIT** | open (MIT) · pop | Microsoft AI Red Team, Python; multi-turn attacks, own scenarios and scorers, text, images, audio; a construction kit, not a scanner — needs a person with time and skill | an in-house security engineer, deep scenarios | a quick check without preparation |
| **Promptfoo** | open (MIT) · pop | CLI, owned by OpenAI since March 2026; attacks generated for your application, RAG and agents, runs in CI — prompt changed → attacks re-run; attacks knowledge-base retrieval and tool calls; core stays MIT, but the owner is now a model vendor | regular checks on every prompt or tool change | when independence from model vendors matters |
| **DeepTeam** | open (Apache 2.0) · grow | Python on DeepEval, local, a few lines; hits known weak spots by OWASP lists, does not adapt to your logic | a team already on DeepEval | deep product-specific scenarios |
| **AgentDojo** | open (MIT) · grow | ETH Zurich task-and-attack set; measures how many tasks the agent solves **and** how many injections pass; academic defences (incl. CaMeL) are compared on it; a model for building your own stand that counts usefulness and safety together | comparing two defence schemes on the same tasks | checking a finished product without adaptation |
| **OWASP lists** | open (open project) · base | LLM Top 10 (model applications), Agentic Top 10 (ASI01–ASI10), Agentic Skills Top 10 (`tools.md`); a base for the threat model and the client conversation — for each item write down how you cover it | a threat model before launch; requirements for a contractor | replacing your own testing |

## Clouds

A cloud filter or DLP service receives the original text together with the personal data. **For Kazakhstan client data, masking is done in-house before any external call.** Legal requirements must be checked with a lawyer.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Lockbox | secrets store (no ready guardrail or masking service for agents found) | keys outside the agent |
| | Audit Trails | log of cloud actions | part of the decision log |
| | Compute / Serverless Containers | own masking service | Presidio with IIN recognisers |
| DigitalOcean | Guardrails in Gradient | basic filters for platform agents | an agent fully in Gradient |
| | App Platform | containers for own masking and authorisation | everything else |
| Railway | service from Docker | no ready protection: Presidio, OpenFGA, Cerbos as plain services | own protection layer |
| | private network | services without outbound access | closed egress for the agent |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Bedrock Guardrails (content filters, PII, prompt attacks in one service, also for third-party models); Comprehend (PII detection); Verified Permissions (Cedar as a service); AgentCore Identity and Policy (agent identity, policies on tool calls, delegation from the user) |
| Google Cloud | Model Armor (injections and leaks — **among the filters broken >90% in the 2025 paper: a layer, not a wall**); Sensitive Data Protection (corporate DLP); IAM and Agent Identity |
| Azure | Prompt Shields (direct and indirect injection detector) and Content Safety; AI Language PII; Entra Agent ID (the agent's own identity in the company directory, conditional access) |
| Cloudflare | Firewall for AI (checks model requests at the network edge — for a public bot); AI Gateway Guardrails and DLP; Zero Trust for agent access to internal services; all work on traffic that passes through Cloudflare |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Review an agent's risks before launch | rule of two and the OWASP lists | — |
| Client data goes to a foreign model | Presidio with own recognisers and reversible substitution | names and addresses in free text → add GLiNER |
| IIN, phones, contract numbers | own recognisers with a checksum | — |
| Customer bot with fixed operations | action selector | — |
| Agent reads email, documents or the web | dual LLM and closed egress | high stakes → provenance tags after CaMeL |
| Multi-step task of a known shape | plan then execute | — |
| A ready injection-detection layer | LlamaFirewall in-house | external service allowed → Lakera Guard |
| Content moderation without an external API | Llama Guard | hard dialogue limits → NeMo Guardrails |
| Agent rights depend on relations of people and objects | OpenFGA | OPA already there → policies in it; readability for audit → Cedar |
| Agent acts on behalf of different users | identity and delegation, keys outside the agent | — |
| Payments, refunds, mailings | risk levels and confirmation before the action | plus an amount limit in the rights check |
| Incident analysis and audits | decision log without raw personal data | — |
| Test protection on every change | Promptfoo in CI | wide first run → garak; deep scenarios → PyRIT |
| Bot answers clients in Kazakhstan | disclose that an AI answers, mask data in-house | check the AI-law requirements with a lawyer |
