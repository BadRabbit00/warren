# Agent layer: knowledge base (retrieval, RAG)

Source: Alexey's «База знаний» (map 2 of 8, checked 12 November 2026). How to give the agent the company's knowledge: embedding models, hybrid search and rerankers, vector stores, graph approaches, document parsing, ready platforms, agentic search. Why the layer exists is in `../base.md` (layer 02, mechanism M12); how the databases themselves work is in `architecture-guide` → `layers/databases.md`; memory about the user is in `memory.md`. Benchmark scores are a guide only: sources disagree, and on your documents the order can differ.

Marks: licence **open / src / prop**; status **base / pop / grow**.

## Concepts

- **Retrieval is a pipeline.** Parse → chunk → embed → search → rerank → answer. It breaks most often **at the start**: if a PDF table turned into mush, no model downstream can fix it. Fix in order, left to right.
- **Hybrid by default.** Vectors find meaning; full-text search (BM25) finds exact words: SKU, surname, contract number. Per Anthropic's measurements, contextual embeddings + BM25 cut retrieval misses by 49%, and with a reranker by 67%.
- **A vector is data too.** Source text can be reconstructed from an embedding (one paper recovered 92% of short fragments exactly). Access rights are usually lost at indexing because one service account reads everything. **Protect the vector store like the documents themselves.**

## Rule 0

First collect 30–50 real questions with correct answers and measure every change against them. Start in Postgres: pgvector + full-text search + a reranker. Add a graph, a separate vector database or heavy parsing only when a measurement showed what exactly is missing. **Check access rights at search time, not by a request in the prompt.**

## Classes and technologies

### EMBED — embedding models
Turn text into a vector to find similar text. **The choice is long-lived: changing the model means re-embedding the whole index.** Key questions: your languages, whether text may leave, how much memory a vector takes. Many models support MRL (a vector can be shortened with little quality loss).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **BGE-M3** | open (MIT) · base | BAAI, open weights 568M, 100+ languages, 8k-token context, vector 1024; one model gives a dense vector, a sparse one (BM25-like) and per-token ColBERT-style vectors — **hybrid search without a second model**; runs on a modest GPU and even CPU | a multilingual knowledge base in-house; hybrid search with one model; weak hardware | chasing the top of the benchmark; very long documents as one chunk |
| **Qwen3-Embedding** | open (Apache 2.0) · pop | Alibaba, 0.6B / 4B / 8B, 100+ languages plus code, 32k context, flexible size (MRL); 8B holds first place in multilingual MTEB (~70.6) and leads code search; follows a query instruction; 8B needs a serious GPU, 0.6B is light and still beats many APIs | maximum quality without sending data out; search over code and docs; long documents | a server without a GPU; when BGE-M3 is enough (needless complexity) |
| **GigaEmbeddings** | open (MIT) · grow | Sber, opened August 2026: 480M, 3B, 10B-A1.8B; Russian first, English; context up to a few thousand tokens; the 480M scores 70.98 on Russian MTEB and beats the larger FRIDA, the largest is first on ruMTEB per Sber; within a couple of points of Qwen3 | Russian documents: contracts, regulations; a light model with strong Russian | a multilingual corpus with Kazakh (measure first); English as the main language |
| **Voyage 4** | prop (API, Voyage AI owned by MongoDB) · pop | January 2026; multilingual, 32k context, vector ≤ 2048 with MRL; **all four sizes share one vector space** — index with the large one, embed queries with the small one; voyage-context-4 (June) accounts for the chunk's neighbouring text | long documents where chunks lose context; quality over independence | text that cannot leave the country; a tight budget on a large corpus |
| **Gemini Embedding** | prop (Google API) · pop | 001 leads English MTEB, 2k-token context in 001, vector 3072 (flexible); Gemini Embedding 2 is multimodal, named the best all-rounder and first in cross-lingual search in an independent 2026 test | a Google Cloud stack; query in one language, documents in another | data in your own jurisdiction; long chunks in 001 |
| **OpenAI text-embedding-3** | prop (OpenAI API) · base | small and large, 8k context, 3072 (large) truncatable to 1024; where most prototypes start; by 2026 beaten in multilingual rankings by open models and other APIs; reasonable price when truncated | a quick prototype; everything already on OpenAI | a new project with Russian and Kazakh (better and free exist); data in your own jurisdiction |
| **Cohere Embed v4** | prop (Cohere API) · pop | multilingual, long context, fixed size set; text and page images in one space; usually paired with Cohere Rerank | scans and pages with charts without separate parsing; pairing with Cohere Rerank | data in your own jurisdiction |
| **Jina Embeddings v4** | src (CC BY-NC 4.0 weights) · pop | open weights 3.8B and API, multilingual, long context, 2048 with MRL, task adapters; strong at dimension reduction and visual documents. **Weights are non-commercial — business needs their API or a contract** | research and trials in-house; visually complex documents | a commercial project on your own servers without a contract |

### SEARCH — hybrid search and rerankers
Stage one quickly finds ~100 candidates; stage two (the reranker) reads the query together with each chunk and reorders. **A reranker is the cheapest improvement to search that already works:** the model does not change, the index is not rebuilt.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Hybrid: BM25 + vectors** | open (technique) · base | two searches in parallel, results merged by RRF (sum of reciprocal ranks, no weight tuning); Postgres (`tsvector` or `pg_search`) + pgvector, Qdrant, Weaviate, OpenSearch; BGE-M3 sparse mode can replace BM25; full text catches exact matches vectors blur (error code, SKU, surname), vectors catch paraphrases | any knowledge base over company documents; queries with numbers, codes, names | almost nothing — this is the starting point |
| **Contextual Retrieval** | open (technique, Anthropic) · pop | before embedding and BM25 indexing, a cheap model writes one or two sentences of context per chunk from the whole document ("revenue grew 3%" is useless without whose and which quarter); one model call per chunk at indexing, the prefix cache saves cost; gave the −49% misses; voyage-context-4 does similar inside the model | long documents: reports, contracts, regulations; chunks that lose meaning out of the document | a corpus that is often fully refreshed (costly reindexing); short self-contained records like an FAQ |
| **BGE-reranker-v2-m3** | open (MIT) · base | open weights 568M, multilingual cross-encoder (reads query + chunk together, gives a score); CPU for small volumes, GPU for speed; v2-gemma and v2-minicpm are more accurate but heavier; on own tests usually within 1–2 points of paid APIs | data that must not leave the network; Russian and other non-English languages | hundreds of candidates per query without a GPU (slow) |
| **Cohere Rerank 4** | prop (API) · pop | rerank-v4.0-pro and fast, multilingual, long context (large documents billed per chunk), on cloud marketplaces; one API call over any search — many teams add it first | raising quality quickly without own infrastructure | text that cannot leave |
| **Voyage rerank-2.5** | prop (API) · pop | rerank-2.5 and 2.5-lite, multilingual, AWS Marketplace; makes sense if embeddings are already Voyage (one vendor, one bill) | a Voyage stack | text that cannot leave |
| **ColBERT / late interaction** | open (MIT) · pop | a vector per token instead of per chunk (ColBERTv2, jina-colbert-v2, BGE-M3 mode); stored in Qdrant, Vespa, Weaviate multivectors; query and document encoded separately, compared per token — more accurate than plain vectors on long technical texts and faster than a cross-encoder; **index several times larger** | legal, scientific, technical texts; accuracy above plain vectors without heavy reranking | a small project (complexity does not pay off); expensive storage |

### STORE — where to keep vectors
Briefly, from the knowledge-base point of view (internals and clouds are in `layers/databases.md`). **The 2026 conclusion: many projects do not need a separate vector database at all.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **pgvector** | open (PostgreSQL License) · base | Postgres extension; hybrid with `tsvector` / `pg_search`; filters are plain SQL and row-level rights; pgvectorscale for large volumes; chunks, metadata, rights and vectors in one database and **one transaction — delete a document and its vectors go in the same query** | the start of any knowledge base; row-level access rights; one database instead of two | tens of millions of vectors under heavy load |
| **Qdrant** | open (Apache 2.0) · pop | Rust server; dense, sparse and multivectors; fast metadata filtering; tenant isolation by a field filter or separate collections; Qdrant Cloud or self-hosted; taken when pgvector stops coping or ColBERT multivectors are needed | a large corpus with filters; late interaction | a small project (an extra service) |
| **Weaviate** | open (BSD-3) · pop | Go server; BM25 + vectors in one query, built-in embedding and reranker modules; some enterprise modules under a separate licence | hybrid without hand assembly | needing the fewest moving parts |
| **Milvus** | open (Apache 2.0) · base | distributed cluster, scales to billions of vectors; Zilliz Cloud or self-hosted; noticeably heavier to operate | hundreds of millions to billions of vectors | one company's knowledge base (overkill) |
| **LanceDB** | open (Apache 2.0) · grow | embedded library, data as files on disk or S3, full text + vectors, in-process without a server; LanceDB Cloud | local and embedded scenarios, a small store next to the agent's code; data in object storage | many concurrent writers |
| **turbopuffer** | prop (SaaS / BYOC) · grow | keeps the index in S3-like storage and loads only what is needed; full text + vectors; no free plan; cheapest when the corpus is huge and queries are rare | a very large corpus with rare queries; many isolated tenants | data in your own jurisdiction without BYOC; a small project |

### GRAPH — graph approaches
A model extracts entities and relations from documents, search walks the graph. Helps with "how are A and B related" and "what is said about X overall". **Loses on ordinary "find the contract clause":** one comparison gave 54% for vector search vs 35% for the graph. Plus cost: the graph is built with model calls and needs upkeep.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Microsoft GraphRAG** | open (MIT) · pop | Python; builds a graph, groups entities into communities and pre-writes summaries; local mode around an entity, global over summaries; **expensive indexing** (tens of thousands of dollars for a large corpus in 2024), LazyGraphRAG cuts it sharply; updates rebuild the graph | overview questions across a large corpus; analytics, investigations | a frequently changing corpus; finding a specific fact or clause; a modest indexing budget |
| **LightRAG** | open (MIT) · grow | Python library and server; graph + vector search on two key levels, skips the community step; cheap queries; new documents appended without rebuilding; indexing still through a model; may miss long relation chains | graph search on a limited budget; a growing corpus | needing community summaries; complex multi-hop relations |
| **Neo4j + neo4j-graphrag** | open (GPLv3 Community) · base | mature graph DB and library, Cypher, vector index inside; **you define the entity/relation schema yourself** instead of trusting what the model extracts — more work up front, a predictable, checkable graph | a domain with clear entities (clients, contracts, supplies); a graph as a long-lived data product | "pour in documents, get answers" in a day |
| **Graphiti** | open (Apache 2.0) · pop | Python; each fact carries its validity time, contradictions produce an explicit replacement; Neo4j, FalkorDB and others. **A memory tool, not document search** (see `memory.md`) | the agent's memory about a client over time | Q&A over a document base |

### PARSE — document parsing
Turns PDFs, scans and office files into clean text with structure: headings, tables, reading order. Extracting text is solved; **structure is the problem**. Test on your documents: almost all are good on clean digital PDFs, they diverge on tables, formulas and scans.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Docling** | open (MIT) · base | IBM Research, LF AI & Data; Python, fully local, runs on CPU; PDF, Office, HTML, images; outputs a document object model with hierarchy, Markdown, ready chunks; a table split across pages comes out as two objects; paid managed version in watsonx since 2026 | a closed perimeter (nothing leaves); tables in digital PDFs and office files; LlamaIndex / LangChain pipelines | scientific texts with dense formulas; maximum throughput on a stream |
| **MinerU** | src (own licence based on Apache 2.0) · pop | Python, local CPU/GPU, VLM mode; PDF and scans → Markdown, JSON; joins tables across page breaks, best on formulas; a commercial contract only for very large services, an online product built on it must say so | scientific and technical literature; multi-page tables | high speed (normal mode is slow); a strict "standard licences only" policy |
| **Marker** | src (OpenRAIL-M weights) · pop | Python, GPU, three speed modes, 90+ OCR languages, paid Datalab API; v2 several times faster than MinerU at comparable quality per the authors; **weights free for research and small companies — above a revenue threshold (sources say $2–5M) a paid licence is required** | a large PDF stream where speed matters; scans in various languages | complex financial tables; a company above the licence threshold |
| **Unstructured** | open (Apache 2.0) · base | library + paid platform, local or cloud; 25+ formats (PDF, Office, email, HTML…) as typed elements; one interface for every file type plus source connectors; less accurate on complex PDFs than specialists | a zoo of formats: emails, slides, wikis; needing source connectors | when the main pain is complex PDF tables |
| **LlamaParse** | prop (SaaS) · pop | LlamaIndex cloud only; PDF, Office, images → Markdown and structured output; tiers by page complexity; first in an independent document-parsing ranking in summer 2026; **documents are processed by the vendor** | hard tables and layouts when documents may leave; no wish to run GPUs | documents that cannot leave the network |

### PLATFORM — ready platforms and retrieval libraries
Three levels: a platform with UI (upload documents, get a chat), a server with an API (a ready pipeline without UI), a library (bricks to build your own). Dify (`frameworks.md`) has a knowledge base inside too.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **RAGFlow** | open (Apache 2.0) · pop | Docker platform; own deep parsing, chunking templates, hybrid search, rerank, agents, GraphRAG and RAPTOR; answers link to the place in the document; **you see how a document was chunked and can fix it by hand**; heavy to deploy (many containers); managed version exists | a knowledge base on complex documents with chunking review; source links in answers | a weak server; syncing rights from corporate systems |
| **Onyx** | open (MIT + Enterprise) · pop | ex-Danswer; Docker / Kubernetes; ~50 connectors (Slack, Confluence, Google Drive, Jira…), hybrid search, agents, deep research; runs in closed perimeters on local models; SSO, roles and audit in the paid version | search across all company systems at once; a closed perimeter | free roles and SSO; a narrow single-task agent |
| **R2R** | open (MIT) · grow | SciPhi; Docker server with REST API: ingestion, hybrid search, knowledge graph, agentic search; no end-user chat; small community | a ready pipeline behind an API with your own UI | a ready chat for staff; when community size matters |
| **Kotaemon** | open (Apache 2.0) · grow | web app; hybrid search, citations, multi-user login; light alternative to big platforms | a small team, fast result | corporate sources and rights |
| **Haystack** | open (Apache 2.0) · base | deepset; Python library with explicit pipelines, each component tested separately, less magic; deepset Cloud | production where tests and predictability matter | needing the most ready connectors |
| **LlamaIndex** | open (MIT) · base | Python and TS; connectors, indexes, query engines, Workflows; LlamaCloud, LlamaParse; here: quickly assembling a pipeline from ready parts for dirty PDFs and many sources (as an agent framework see `frameworks.md`) | many different sources and formats; quick assembly of your own pipeline | wanting minimal abstractions |

### AGENTIC — agentic search
The agent builds queries itself, looks at results and searches again. **Not a replacement for search, a way to use it.** The "RAG is dead" debate is about code — in a repository grep really wins. For a company document base the conclusion differs.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **File search: grep and glob** | open (technique) · pop | no index (nothing goes stale), file-reading tools, ripgrep; pays in tokens on every query; how coding agents work. A 2026 study: on small corpora on par with BM25, at full scale **39× more tokens per answer and almost 20 points behind** | code and configs; a small file set (up to hundreds); constantly changing documents | a large knowledge base; questions without exact words to search for |
| **Agent with a search tool** | open (technique) · pop | hybrid search from this file wrapped as a tool or MCP server; the agent decides when to search, reformulates, checks and searches again; several search calls per question; same study: agent + BM25 **69.4** vs bare BM25 54.8 vs agent on raw files 36.9 | a production knowledge base for an agent; complex questions needing several searches | a hard latency limit (every round costs time) |
| **Query data instead of searching** | open (technique) · base | if knowledge lives in tables, it is not searched by meaning: deal status, stock, a master's schedule come from CRM and DBs through **narrow tools with parameters; text-to-SQL read-only**; rights checked in the tool by the user's identity. Vector search over a CRM export gives stale, inaccurate answers | a CRM companion; bookings, orders, stock, schedules | knowledge in free text: regulations, correspondence |

## Clouds

Managed search is convenient, but documents and vectors end up with the provider. For Kazakhstan personal data: **embedding through a foreign API is also sending the text abroad.** Open models (BGE-M3, Qwen3-Embedding, GigaEmbeddings) can be kept in-house.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | AI Studio: AI Search | search over uploaded files and the web, plugs into an agent as a tool | a quick knowledge base without own pipeline |
| | Embeddings and Vector Store | models and vector storage | own search on Yandex services |
| | Managed PostgreSQL | Postgres with pgvector | hybrid in one database |
| | Managed OpenSearch | full text + vectors | a large corpus, complex search |
| DigitalOcean | Gradient AI Knowledge Bases | managed knowledge base for platform agents and own code via ADK | an agent on Gradient |
| | Managed PostgreSQL / OpenSearch | pgvector; full text + vectors | own hybrid search; a large corpus |
| Railway | Postgres with pgvector (template) | no managed search; Qdrant and the reranker as plain containers; **GPU not confirmed** — light models on CPU or via API | starting a knowledge base; outgrown pgvector → Qdrant container |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | Bedrock Managed Knowledge Base (June 2026: ingestion, parsing, chunking, embeddings, storage, rerank behind one API; connectors to S3, SharePoint, Confluence, Salesforce, Jira; agentic search); S3 Vectors (cheap vector storage, rare queries); Aurora pgvector / OpenSearch (own pipeline); Textract (OCR and tables) |
| Google Cloud | Agent Search (ex-Vertex AI Search, turnkey; data in BigQuery and Cloud Storage); RAG Engine (assembled pipeline on Gemini with swappable vector DBs; names keep changing); AlloyDB / Cloud SQL pgvector; Document AI |
| Azure | Azure AI Search (strong hybrid with semantic ranking; agentic mode GA in 2026 splits a question into parallel subqueries; it is an engine — you build the app); Document Intelligence (containers for your own network); PostgreSQL Flexible Server with pgvector |
| Cloudflare | AI Search (GA 1 October 2026, pay-per-use from November; sources: upload, R2 or your site); Vectorize for own pipeline; Workers AI open embeddings and rerankers |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| First knowledge base on company documents | Postgres: pgvector + full text, BGE-M3, bge-reranker-v2-m3 | tens of millions of chunks or heavy filters → Qdrant |
| Ready with UI in a week | RAGFlow or Onyx self-hosted | Dify already runs → its built-in knowledge base |
| Russian documents | BGE-M3 or GigaEmbeddings | maximum quality and a GPU → Qwen3-Embedding-8B |
| Kazakh documents | BGE-M3 and a mandatory measurement on own questions | bad measurement → strengthen BM25 and translate the query |
| Text cannot leave | open embeddings and reranker in-house | — |
| Queries with SKUs, surnames, numbers | hybrid BM25 + vectors | — |
| PDFs with tables | Docling | formulas and science → MinerU; may go to the cloud → LlamaParse |
| Scans | Docling with OCR | large stream → Marker if the licence fits |
| "How are A and B related", corpus overview | LightRAG | community summaries needed → GraphRAG |
| Data in CRM and tables | a tool with a DB query, not semantic search | — |
| A small set of files | agent with file search | corpus grew → give the agent a hybrid search tool |
| Chunks lose meaning without the document | Contextual Retrieval | via API → voyage-context-4 |
| Search works, want better | add a reranker | then contextual retrieval, then a new embedding model |
| Memory about a client over time | not here: Graphiti in `memory.md` | — |
