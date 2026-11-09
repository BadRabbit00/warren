# Layer: realtime and communications

Source: Alexey's «Realtime и коммуникации» (checked 30 October 2026). Delivering data to the user instantly or reaching them outside the app: WebSocket servers, state sync and local-first, WebRTC voice and video, voice AI agents, camera video streams, email and notifications. Voice AI frameworks update almost weekly — pin versions and measure latency on your own data.

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **SSE · WebSocket · WebRTC.** SSE = server → client event stream over plain HTTP, simplest (how LLM answers are streamed). WebSocket = two-way channel for chat and collaboration. WebRTC = media and data with minimal latency over UDP, for voice and video.
- **SFU and TURN.** SFU = media server that takes each participant's stream and forwards it to the others without transcoding. TURN = relay for clients behind strict NAT or corporate firewalls; **without TURN some users simply cannot connect**.
- **Local-first and CRDT.** Data lives on the client and syncs in the background: instant UI, works offline. CRDTs merge concurrent edits without conflicts, as in Google Docs.

## Rule 0

For streaming answers and UI notifications, **SSE from your own backend is enough**. A separate realtime server is needed for tens of thousands of connections or rooms, presence and history. Run your own media server and TURN only if you have people to operate UDP infrastructure. **Send app email through a delivery service, not your own server**: IP reputation and DKIM, SPF, DMARC decide whether a message reaches the inbox.

## Classes and technologies

### PUSH — WebSocket and pub/sub for clients
Servers holding thousands of persistent connections and fanning out events by channel; the backend publishes via API. Key features: **presence**, channel history, recovery of missed messages after reconnect.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Centrifugo** | open (Apache 2.0 OSS) + PRO (commercial since November 2025; no reselling as hosting or multi-tenant) · pop | one Go binary next to any backend; v6 (January 2025); WebSocket, SSE, HTTP-streaming, WebTransport, gRPC; channels, presence, history, stream recovery; Valkey/Redis or NATS broker, millions of connections; publish via HTTP/gRPC API, JWT auth, proxy hooks to the backend | chat, notifications, live feeds for any stack; tens to hundreds of thousands of concurrent connections | collaborative editing (needs CRDTs); a few hundred users (SSE from the backend is simpler) |
| **Socket.IO** | open (MIT) · base | own protocol over WebSocket with long-polling fallback (needs the Socket.IO client); rooms, namespaces, acks; Redis/Valkey, Postgres, MongoDB adapters; ports to other languages | a Node app with chat or live updates | bare WebSocket clients and IoT; non-JS backends (→ Centrifugo) |
| **Phoenix Channels / LiveView** | open (MIT) · base | Elixir/BEAM: each connection a light process, millions of them, cluster without a broker; topics, Presence synced via CRDT | Elixir projects, chats, dashboards | outside Elixir |
| **Soketi** | open (AGPLv3) · pop | Pusher protocol (public, private, presence channels); Redis cluster; Laravel Echo and Pusher clients; **authors warn of rare updates** | Laravel and Pusher-protocol code | a long-term bet (abandonment risk → Laravel Reverb or Centrifugo) |
| **Mercure** | open (AGPLv3 hub) · pop | SSE with URL topics and JWT auth; passes any proxy; one node in open source, cluster paid; built into Caddy, popular in Symfony | Symfony/PHP, one-way live data updates | two-way exchange |
| **Ably / Pusher** | prop (SaaS) · pop | channels, presence, history, global network, SDKs everywhere, delivery guarantees and SLA; pay per message and connection | fast, no infrastructure | large volumes on a small budget |

### SYNC — state sync and local-first
The client holds part of the database and an engine syncs it: instant UI, offline, others' changes appear by themselves. Most engines sync **Postgres** via logical replication.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **ElectricSQL** | open (Apache 2.0) · pop | 1.0 March 2025; Postgres logical replication → "shapes" (table subsets) streamed over plain HTTP, so **CDN-cacheable**; writes go through your API; pairs with PGlite and TanStack DB | live Postgres data in the UI without your own WebSocket layer; large-scale reads via CDN | ready offline writes with conflict handling |
| **Zero** | open (Rocicorp) · grow | 1.0 June 2026; Postgres → zero-cache replica; ZQL queries run on the client, results synced; client and server mutators; the author calls it "a fancy cache". Limits: Postgres only, no views and some column types, large client bundle | apps where every action must feel instant (like Linear) | non-Postgres; small bundle requirements |
| **PowerSync** | src (FSL service; SDKs Apache/MIT) · pop | Postgres, MongoDB, MySQL → sync rules → SQLite on device; change queue → your backend; full offline-first; SDKs for Flutter, React Native, Kotlin, Swift, web | mobile apps working without a connection (field staff, warehouses, couriers) | an open-licence service |
| **Yjs + Hocuspocus** | open (MIT) · base | the most popular CRDT library (text, arrays, maps) behind Tiptap, BlockNote, Lexical collaboration; Hocuspocus = ready WebSocket server with storage and auth; offline | collaborative text, whiteboard, diagram editors | plain CRUD data (a sync engine is simpler) |
| **Automerge** | open (MIT) · pop | Rust core, JS and other bindings; JSON document with full change history; conflict-free merge, peer-to-peer | local-first apps with version history | huge documents with very frequent edits (Yjs is faster) |
| **Convex** | src (FSL → Apache 2.0) · grow | own transactional DB; TypeScript query functions, the client subscribes to results; ACID mutations; no offline; self-hosted version exists; popular with AI app generators | fast full-stack TS with live data | needing plain SQL and familiar Postgres |

### RTC — WebRTC, media servers, video streams
Voice and video in real time need an SFU, STUN/TURN for NAT traversal, and signalling. A subclass: camera and drone video ingest (RTSP, SRT, WebRTC/WHIP).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **LiveKit** | open (Apache 2.0) · pop | Go on Pion; SFU + signalling + built-in TURN; SDKs for web, iOS, Android, Flutter, React Native, Unity, **ESP32**; Redis cluster or LiveKit Cloud; recording, streaming, SIP telephony, data channels; raised $100M at $1B (January 2026), clients include OpenAI and xAI; self-hosted free | voice and video AI agents; calls and conferences in your product; talking devices and toys | platforms without inbound UDP (needs TURN over TCP) |
| **mediasoup** | open (ISC) · base | C++ core, SFU as a Node.js/Rust library; signalling, rooms and TURN are yours to write | your own video platform with special requirements | needing a ready solution |
| **Janus / Jitsi** | open (GPLv3 Janus / Apache 2.0 Jitsi) · base | Janus = universal media gateway with plugins (WebRTC ↔ SIP or RTSP); Jitsi Meet = ready self-hosted Zoom alternative; recording, streaming | own video conferencing (Jitsi); protocol gateways (Janus) | AI agents (LiveKit is easier) |
| **coturn** | open (BSD-3) · base | standard TURN/STUN over UDP, TCP, TLS; servers per region; **issue temporary credentials via REST**, otherwise it becomes a free proxy for others | your own WebRTC without a ready platform | static TURN passwords (abuse) |
| **MediaMTX** | open (MIT) · pop | one binary, runs at the edge; RTSP, RTMP, SRT, WebRTC (WHIP/WHEP), HLS; protocol conversion, recording, auth; camera RTSP/SRT → browser WebRTC under a second | drone and camera video in a web UI; recording streams | video conferences between people |

### VOICE-AI — voice AI agents
"speech → text → LLM → speech" under a second. Hard parts: **turn detection** (did the person finish), barge-in, noise suppression, telephony. Alternative: speech-to-speech models in one call.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **LiveKit Agents** | open (Apache 2.0) · pop | Python, TypeScript; STT → LLM → TTS or realtime models; VAD and own transformer end-of-turn detector, noise suppression, native SIP, agent testing; plugins for OpenAI, Deepgram, ElevenLabs, Cartesia…, LiveKit Inference; 1.5 branch updated almost weekly | voice assistants in apps and by phone; talking devices over WebRTC | one provider without your own infrastructure (SaaS is simpler) |
| **Pipecat** | open (BSD-2, Daily) · pop | Python pipeline of frame processors; transports Daily WebRTC, Twilio, WebSocket (FastAPI), LiveKit; dozens of STT/LLM/TTS providers; telephony and human handoff are DIY | flexible custom pipelines; an agent over WebSocket without WebRTC infrastructure | ready telephony out of the box |
| **Realtime model APIs (OpenAI, Gemini Live)** | prop (SaaS) · pop | speech-to-speech in one call over WebRTC, WebSocket, SIP; minimal latency, natural intonation; vendor lock-in, less step control; often used inside LiveKit Agents or Pipecat | the most natural voice quickly | data localisation requirements; own STT/TTS (e.g. **Kazakh**) |
| **Vapi / Retell** | prop (SaaS) · pop | ready pipeline with model choice, BYO models; telephony and web; call analytics, human handoff; priced per minute | a call centre in a week | your own product with many minutes (expensive) |

### MAIL — email and notifications
Transactional email, newsletters, mobile push, SMS and messengers. A notification service gives one API for all channels, templates, user channel preferences and **digests** (ten events in one email).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Resend / Postmark / SES** | prop (SaaS) · pop | API, delivery and bounce webhooks, DKIM; solve sender reputation; SES cheapest at volume, Postmark known for deliverability, Resend for developer experience (React Email) | any transactional email from the app | personal data that must not leave the country (→ a local service) |
| **Postal** | open (MIT) · pop | self-hosted SendGrid: API, tracking, several IP pools, inbound via webhooks; deliverability depends on your IPs (warm-up, blacklist monitoring) | large volumes with a self-hosted requirement | no one to manage IP reputation |
| **Stalwart** | open (AGPLv3 + Enterprise) · grow | Rust mail server: SMTP, IMAP, JMAP, POP3, CalDAV/CardDAV, spam filter, DKIM/DMARC, encryption at rest; replaces Postfix + Dovecot + Rspamd | own corporate mail for people | sending app email (a delivery service is simpler) |
| **Novu** | open (MIT core + Enterprise) · pop | email, SMS, push, chat, in-app inbox (bell component); workflows as code, digest, delays, subscriber preferences; routes through connected providers; self-hosted | a product with notifications on many channels | one sign-up email |
| **ntfy / Gotify / Apprise** | open (Apache 2.0 + GPLv2 / MIT / BSD-2) · pop | HTTP POST → push to phone/desktop (`curl -d "backup failed" ntfy.example/alerts`); Apprise library sends to Telegram, Slack, email and 100+ more in one call | alerts and service notifications; on-call without PagerDuty | notifications to product users |
| **FCM / APNs / RuStore Push** | prop (platform services) · base | every phone push ends up here; topics, priorities, data messages; **for users in Russia and parts of the CIS add RuStore Push and HMS** — Google services are not everywhere | mobile notifications | — |

## Clouds

For media, check whether the platform allows **inbound UDP**: without it WebRTC works only via TURN over TCP/TLS with more latency. For email and SMS, local operators and sender registration rules in the country matter.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Postbox | transactional email, SES-compatible API | app email |
| | Cloud Notification Service | iOS/Android push, browser push, SMS (messengers promised later) | user notifications |
| | API Gateway (WebSocket) | WebSocket connections to functions and containers | serverless realtime |
| | SpeechKit | STT and TTS, streaming mode | voice agents in **Russian and Kazakh** |
| DigitalOcean | App Platform / Droplets | WebSocket, SSE, own realtime servers | Centrifugo, Socket.IO |
| | Droplets + Cloud Firewall (UDP) | media servers and TURN | LiveKit, coturn |
| | (no managed realtime, mail or push) | email via an external delivery service (Resend, Postmark, Postbox) | — |
| Railway | Public Networking | HTTP, WebSocket, SSE | realtime servers, SSE from the backend |
| | TCP Proxy | TCP ports outward | MQTT, own protocols |
| | Centrifugo / Novu / ntfy templates | realtime and notifications in the project | prototypes, small loads |
| | (**inbound UDP is a problem** — full LiveKit or coturn is hard; check current network capabilities first) | — | — |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | API Gateway WebSocket / AppSync Events (serverless WebSocket and pub/sub); IoT Core (MQTT — toys, drones, sensors); SES; SNS / End User Messaging (SMS, mobile push); Chime SDK / Kinesis Video Streams (voice, video, camera streams) |
| Google Cloud | Firestore / Realtime Database (client subscriptions to data); FCM; Gemini Live API / Speech-to-Text / Text-to-Speech |
| Azure | Web PubSub / SignalR (managed WebSocket); Communication Services (email, SMS, calls, video); Notification Hubs (mass push) |
| Cloudflare | Durable Objects WebSockets with hibernation (rooms, chat, collaboration at the edge without idle cost); Realtime (global SFU and TURN); Email Routing and sending from Workers |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| Streaming LLM answers and statuses to the UI | SSE from your own backend | — |
| Chat and live notifications, many connections | Centrifugo | Node app → Socket.IO; Elixir → Phoenix |
| Code already on Pusher (Laravel) | Laravel Reverb | SaaS wanted → Pusher or Ably |
| Live Postgres data in the UI | ElectricSQL | Linear-like instant UX → Zero |
| Mobile app without a connection | PowerSync | — |
| Collaborative editing | Yjs + Hocuspocus | history and P2P → Automerge |
| Voice AI agent | LiveKit + LiveKit Agents | own pipeline over WebSocket → Pipecat; call centre in a week → Vapi or Retell |
| Talking devices and toys | LiveKit (ESP32 SDK) + own STT/TTS | no WebRTC on the device → Pipecat over WebSocket |
| Drone and camera video in the browser | MediaMTX (RTSP/SRT → WebRTC) | in AWS → Kinesis Video Streams |
| Own video conferencing | Jitsi | embedding video in a product → LiveKit |
| Own WebRTC behind NAT | coturn with temporary credentials | on Cloudflare → Realtime TURN |
| Transactional email | Resend / Postmark | in Yandex → Postbox; volume and self-hosted → Postal |
| Self-hosted corporate mail | Stalwart | — |
| Notifications on many channels | Novu | — |
| Service alerts to a phone | ntfy | Telegram and a hundred other channels → Apprise |
