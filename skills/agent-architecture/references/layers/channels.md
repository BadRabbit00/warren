# Agent layer: channels and human handoff

Source: Alexey's «Каналы и передача человеку» (map 7 of 8, checked 13 November 2026; WhatsApp prices change quarterly and sources disagree about service-message billing since October 2026 — check Meta's pricing page). How the agent meets people: website chat, messengers, voice, the support desk, passing the conversation to an operator, outbound reminders. Why the layer exists is in `../base.md` (layer 08 handoff); human confirmation of dangerous actions is in `guardrails.md`; voice transport in `architecture-guide` → `layers/realtime.md`.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **The channel dictates the rules.** Each channel has its limits and the agent adapts. Since January 2026 WhatsApp does not admit "about anything" bots, charges per message and allows writing first only with an approved template. Telegram is free, but a bot cannot write to someone who never started it. In voice, latency decides everything.
- **A handoff without context is worse than no bot.** If the operator gets a client without history, the client explains everything a second time. A 2026 check found this break in 4 of 15 live deployments. The operator needs the reason for the handoff, what was already tried and a short summary — not the raw transcript.
- **One core, thin channels.** The agent's logic lives in one service. A channel only normalises the message into a common shape and renders the answer in its own format. A new channel is then a one-day adapter, not a second bot with different behaviour.

## Rule 0

A request for a human is fulfilled **immediately, without persuasion**. In the first message the bot says it is an AI. When an operator takes the dialogue, the bot is silent. If there are no operators, the bot honestly names the response time and leaves a ticket. Write first only to those who agreed, and only on business.

## Classes and technologies

### WEBUI — chat on a website and in an app
Libraries for building the chat window: word-by-word streaming, showing tool calls, confirmation buttons, attachments. For staff a ready web chat is often enough; for clients the window is usually embedded into your site and branded.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **AI SDK UI and AI Elements** | open (Apache 2.0) · pop | Vercel, TypeScript; hooks and ready chat blocks for React, Vue, Svelte; message stream, chat state, components for messages and tools; the most common way to build a chat on React; its stream protocol became almost common (understood by other libraries and Chat SDK) — a Python backend works if it emits that format | own chat in a React or Next.js product | needing a ready chat without UI development |
| **assistant-ui** | open (MIT) · pop | React; product-grade components: dialogue branches, message editing, attachments, voice input, tool display; works with AI SDK, LangGraph, own backend; covers the details that take the most time (scroll while streaming, regenerate, edit a past message); own styles | a polished customer chat; UI for an agent on LangGraph | not React |
| **CopilotKit and AG-UI** | open (MIT) · pop | React library and an open event protocol between agent and UI; shared state of agent and screen, actions in the UI, confirmations; an assistant that **sees the screen and fills the form together with the human**; AG-UI is supported by several frameworks, so the backend can change | a CRM companion: an assistant inside the working screen | a simple Q&A chat |
| **ChatKit** | prop (OpenAI SDK) · grow | embeddable widget and SDK tied to Agents SDK and the OpenAI platform; stream, widgets, attachments, tool display; fastest if the agent is already on OpenAI | an agent on OpenAI's platform needing a chat in a day | several model vendors; own gateway and models |
| **Chainlit** | open (Apache 2.0) · pop | Python framework: write a handler, get a working web chat with agent steps, file upload, login; community-maintained since 2025; limited styling | an internal assistant; a demo prototype | a branded customer chat |
| **Open WebUI and LibreChat** | src (various) · pop | self-hosted web apps, a ready "own ChatGPT": many models, users and groups, files, search, MCP; Open WebUI has its own licence with a **branding condition** (read it before using under your brand), LibreChat is MIT; install, connect the model gateway, hand to staff | a chat with models for staff on own server | a customer channel; an agent with a rigid scenario |

### MSG — messengers
Clients write where they already are. Each messenger has its own API, rules and price. One shared scheme: a webhook receives a message, the agent core answers, an adapter sends the answer in the channel's format.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Telegram Bot API** | prop (API, free) · base | HTTP API, no per-message fee; streaming answers for all bots since Bot API 9.5 (March 2026), topics in a private chat with a bot, managed bots, connecting a bot to the owner's business account; **a bot writes only to those who started it**; libraries: aiogram, python-telegram-bot (Python), grammY (TS) | the first channel for a customer bot; internal assistants and alerts | an audience that does not use Telegram |
| **WhatsApp Cloud API** | prop (API, paid) · base | Meta's HTTP API; per-message billing since July 2025 by country and category; free-form answers only within **24 h after the client's message**; first message only by approved template. **General-purpose bots banned since 15 January 2026** — a bot about your products, bookings and orders is allowed; needs Meta business verification (takes time) | clients mostly on WhatsApp; bookings, order status, support | a chit-chat bot on any topic; mass mailings without consent |
| **WhatsApp API providers** | prop (SaaS) · pop | official Meta partners: 360dialog, Twilio (for developers), WATI, respond.io (with a ready workspace); subscription or mark-up over Meta prices; handle number onboarding, templates, support; **the provider sees all correspondence** — for API access only, a thin provider or direct Cloud API is enough | not wanting to go through Meta onboarding yourself; local support and billing in local currency | correspondence that must not pass through a third party |
| **Unofficial WhatsApp gateways** | prop (SaaS) · pop | services over WhatsApp Web through an ordinary account; no Meta fee and no business verification; **violates WhatsApp rules — the number can be banned any moment**; common on our market, so the client will almost certainly ask; a bot with a noticeable number of dialogues sooner or later loses the number, and the channel goes together with its history | testing an idea on your own number | a company's working channel; a number that cannot be lost |
| **Chat SDK** | open (open source) · grow | Vercel, TypeScript, 2026; handlers written once, adapters for Slack, Teams, Google Chat, Discord, Telegram, WhatsApp, web chat; adapters translate cards and tables into each platform's format; state in Redis and other stores; the web adapter serves the same bot over the AI SDK protocol | a bot in several messengers at once; a TypeScript team | a Python backend; a single channel (the native library is enough) |
| **Slack and Microsoft Teams** | prop (API) · base | corporate messenger APIs; login already set up, rights come from the company; threads, cards, confirmation buttons (handy for confirming agent actions); the best channel for an internal assistant — no separate UI and login | an assistant for staff where they already work | a customer channel |

### VOICE — voice
A phone or voice agent: speech recognition + model + synthesis, or one speech-to-speech model. **The key number is answer latency: past one second a conversation stops being a conversation.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **LiveKit Agents** | open (Apache 2.0) · pop | Python and TS framework; WebRTC through the LiveKit media server, telephony over SIP; the agent joins a room as a normal participant — group calls and transfer to a human come naturally; many concurrent conversations, several participants, video; self-hostable media server; the choice for growing load | hundreds of concurrent calls; transferring a call to an operator in the same room | a simple prototype (more setup than Pipecat) |
| **Pipecat** | open (BSD 2-Clause) · pop | Daily, Python; a pipeline of blocks carrying audio and text frames; every step visible and replaceable (STT, model, TTS, own processors between); you manage conversation state; the largest library of ready integrations; named the best open choice for most teams in a 2026 review | own Python voice agent with full control; trying different speech models | needing ready telephony without assembly |
| **Vapi and Retell** | prop (SaaS) · pop | cloud platforms: a number, telephony, speech pipeline, dashboard; per-minute billing; fastest path to a working number — at the cost of less control over latency and logic, **call recordings stored at the vendor** | a phone bot in a week; no own voice team | recordings that must be stored in-house; Kazakh without a quality check |
| **Speech-to-speech models** | prop (API) · grow | vendors' Realtime APIs; one model listens and speaks instead of a chain of three; lower latency, hears intonation, sounds livelier; more expensive, harder to control and check the answer text; **guardrails and masking from `guardrails.md` are harder to fit — there is no text between steps** | when conversational naturalness matters | a strict scenario with each answer checked |
| **Russian and Kazakh in voice** | open (technique) · base | measure recognition errors on real recordings, especially names, addresses and mixed speech; candidates: Yandex SpeechKit, cloud models, open models in-house. Clients in Kazakhstan often switch between Russian and Kazakh within one phrase; **claimed language support does not mean such speech is recognised** — a set of a hundred own recordings settles it faster than any review | any voice project on our market | no case where it is redundant |

### DESK — the support desk
Where operators sit: a shared inbox across channels, queues, assignment, client history. The agent connects as one more participant: answers first, passes the dialogue to a human. **Without such a system there is nowhere to hand the conversation to.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Chatwoot** | open (MIT, open core) · base | web app, self-hosted or cloud; site widget, email, WhatsApp, Telegram, social networks and more; agent-bot API — the bot answers and switches the dialogue to "open" for an operator; own AI Captain; the best-known open Intercom replacement; **removes half the work of this layer** (channels connected, handoff built in); own agent via webhook and API; deployment and updates are on you | a customer bot with operators on own server; several channels in one window | nobody to maintain the server |
| **Zammad** | open (AGPL) · pop | web app; tickets, response deadlines, roles, reports; email, phone, chat, messengers; stronger than Chatwoot where a request lives for days across departments, weaker as live chat | technical support with tickets and SLAs | fast messenger dialogues |
| **FreeScout** | open (AGPL) · pop | PHP web app; email and simple collaboration, paid modules; runs on the simplest hosting | a small team with email as the main channel | many channels and live chat |
| **Tiledesk** | open (open source) · grow | platform, self-hosted or cloud; live chat turned towards AI agents with a human in the loop; visual scenario builder | bot scenarios built by a non-developer | own agent with own logic (Chatwoot + API is simpler) |
| **Chat in the CRM** | prop (various) · base | CRM modules: Bitrix24, amoCRM and others; the dialogue is attached to the client and deal at once; own chatbot and open-line APIs; if the company lives in its CRM, no second dialogue system is needed; **bot capabilities differ a lot between CRMs — check that first** | sales and bookings where a dialogue leads to a deal; a CRM already in place | no CRM, or nobody works in it |
| **Closed AI platforms** | prop (SaaS) · pop | Intercom, Zendesk and others; built-in agents billed per resolved request; your own agent connects but the vendor pushes theirs; strong ready products — **client data and correspondence live abroad** | an international product with a support team already on the platform | data that must stay in the country; your own agent as the main one |

### HANDOFF — passing to a human
The moment where most bots break. No products here: rules and one data structure the agent assembles at handoff. **A handoff is not the bot's failure but its normal function.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **When to hand off** | open (technique) · base | four triggers, each fires on its own: **direct request → immediately, no exceptions**; rules → complaint, money, legal questions, identity verification; uncertainty → no answer in the knowledge base, two rounds without a result; mood → growing irritation. **The first two are checked by code, not by the model.** Most frequent break: the bot ignores "call a human" and keeps offering options; second: the bot goes in circles without realising it is stuck | any customer bot | no case where it is redundant |
| **Operator package** | open (technique) · base | a structure at handoff: who the client is, what they want, what the bot already did, why it hands off, order and contract numbers; full transcript next to it, not instead of the summary. Nobody reads a raw transcript under load (one estimate: ~15 minutes of preparation from it). **A summary missing the order number is worse than none — the operator trusts it. Numbers and amounts are put in by code, not the model's retelling** | every handoff | no case where it is redundant |
| **The bot goes silent** | open (technique) · base | dialogue state: bot → waiting for operator → operator → closed; back to the bot only explicitly (operator closed or returned it); state kept in the support desk or own DB and **checked before the model call**. Frequent break: the operator already answers and the bot keeps writing in the same chat | any bot with operators | no case where it is redundant |
| **No operators** | open (technique) · base | an honest answer instead of "connecting you": say nobody is here now and when they will answer; create a ticket with the context package, offer a callback. The bot announced a handoff that never happened and the client waits in an empty chat — the second most common failure after lost context; **design the night and weekend path as carefully as the daytime one** | support that is not 24/7 | no case where it is redundant |
| **Operator assistant** | open (technique) · pop | the same agent with the same knowledge, but the answer goes to the operator: draft reply, knowledge-base search, filling the card; the operator decides. **Often where a rollout starts:** lower risk, visible value, and approved answers become evaluation material | the first rollout stage in support; complex requests | no operators |
| **What to measure** | open (technique) · base | not the handoff rate but its appropriateness: how many handoffs were needed and how many needed ones did not happen; lateness — turns from the first signal to the handoff (look at the worst cases, not the average); after handoff — did the operator re-ask what the client already said. A low handoff rate can mean a good bot or a bot that does not let clients go (evaluation in `evals.md`) | any bot with operators | no case where it is redundant |

### NOTIFY — outbound and reminders
The agent writes first: booking reminders, order status, a request to confirm. Channel rules are strictest here and a mistake costs a banned number. The reminder text is usually a template; the model is needed to parse the client's reply.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **WhatsApp templates** | prop (channel rule) · base | outside the 24 h window only an approved template; categories marketing, utility, authentication; billed per delivered message; Meta reviews the template in advance; a booking reminder is utility and cheaper than marketing; **free model text cannot be the first message** — after the client replies, the window opens and the agent writes freely | reminders and statuses in WhatsApp | mailing without consent (complaints lower the number's limits) |
| **Reminder scheduler** | open (technique) · base | a queue or durable execution (`frameworks.md`); exact time, cancellation when a booking moves, protection from double sending (idempotency key against two identical messages after a crash); quiet hours by the client's time. **A reminder is an ordinary delayed job, not agent work** | auto-booking, delivery, payment | no case where it is redundant |
| **Consent and unsubscribe** | open (technique) · base | a rule and a DB field: who, when, which channel, what they agreed to; unsubscribe by one word or button, effective immediately; **unsubscribe is parsed by code (keywords and button), not by the model by meaning**; consent to service messages does not allow advertising | any outbound messages | no case where it is redundant |
| **Fallback channel** | open (technique) · pop | a channel chain from cheap and convenient to reliable; triggers on "not delivered" or no read within a set time; set in advance, **never duplicate the message to all channels at once** | reminders that money or a booking depends on | optional notifications |

## Clouds

A cloud support desk and voice platform store correspondence and call recordings with themselves. **For clients in Kazakhstan an open-source support desk is easier to put on your own server in the country.** Storage requirements must be checked with a lawyer.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | SpeechKit | speech recognition and synthesis | Russian and Kazakh voice after a check |
| | AI Studio Realtime API | voice agents | speech-to-speech |
| | Compute / Managed PostgreSQL | own Chatwoot (no ready support desk) | support desk in-house |
| DigitalOcean | Marketplace: Chatwoot | ready image | a support desk in an hour |
| | App Platform | receiving messenger webhooks | channel adapters |
| Railway | service from Docker + Postgres and Redis | Chatwoot and bots as plain services; dialogue state ("who runs the chat now") | quick start |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Amazon Connect (cloud contact centre: voice, chat, operator queues); End User Messaging (SMS and WhatsApp for outbound reminders); Lex (dialogue bots in Connect) |
| Google Cloud | Customer Engagement Suite: Conversational Agents (chat and voice bots), Agent Assist (operator hints after handoff), conversation analytics |
| Azure | Communication Services (chat, voice, SMS, WhatsApp via one API); Copilot Studio (agents in Teams and on a site); Bot Service (own bot in Teams) |
| Cloudflare | Workers (receiving messenger webhooks, thin adapters); Realtime (WebRTC transport for voice in the browser); Durable Objects (dialogue state) |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Customer bot with operators | Chatwoot self-hosted, agent via the agent-bot API | the company lives in its CRM → CRM channels |
| First channel for the bot | Telegram Bot API | clients on WhatsApp → Cloud API or an official provider |
| WhatsApp without risking the number | official API, bot only about company business | unofficial gateway → only to test an idea |
| A bot in several messengers at once | Chatwoot as the common entrance | TypeScript without operators → Chat SDK |
| Branded chat on own site | AI SDK UI with assistant-ui | a standard window is enough → Chatwoot widget |
| Assistant inside the CRM screen | CopilotKit and AG-UI | — |
| Chat with models for staff | Open WebUI or LibreChat behind own gateway | staff live in Slack or Teams → a bot there |
| Internal tool in Python | Chainlit | — |
| Phone bot | Pipecat | hundreds of calls → LiveKit Agents; urgent and no team → Vapi or Retell |
| Client asks for a human | hand off at once with the operator package | nobody there → ticket and an honest time |
| Where to start in support | operator assistant | then the bot answers simple requests first |
| Booking reminder | scheduler and a WhatsApp utility template | plus a fallback channel: SMS |
| Is the bot handing off well | appropriateness and lateness of handoffs | — |
| Clients in Kazakhstan | support desk on own server, bot introduces itself as an AI | voice → check mixed speech on own recordings |
