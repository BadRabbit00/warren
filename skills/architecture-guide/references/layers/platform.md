# Layer: platform and delivery

Source: Alexey's «Платформа и доставка» (checked 30 October 2026). Where and how everything else runs: container orchestration, self-hosted PaaS, image registries, CI/CD and GitOps, infrastructure as code, backups. Many tools here rest on a few people — before betting on one, check who maintains it and with what money. How we build the deploy variants themselves is in the `deploy-variants` skill; this file is about **choosing** components.

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **Push vs pull deploy.** Push: CI logs into the server or cluster and rolls out — simple, but CI holds production keys. Pull (GitOps): an agent in the cluster watches git and converges — CI has no production access, drift is visible at once.
- **Declarative and reproducible.** Describe what the system should be, not the steps. Best when the same description gives the same result on any machine any day: images pinned by digest, IaC lock files.
- **3-2-1 rule.** Three copies, on two media types, one off-site; plus one immutable copy (object lock) against ransomware. **A backup never restored from is not a backup.**

## Rule 0

Kubernetes is needed when there are many services, several teams, and **someone who will maintain it**. For one to three servers, Docker Compose + Kamal or Coolify is enough. Infrastructure in code from day one. Backups automatic, off the main site, with regular restore tests.

## Classes and technologies

### ORCH — container orchestration
Place containers on machines, restart failed ones, balance, update without downtime. Kubernetes is the standard but has a large **cost of ownership**: network, storage, upgrades, security, monitoring of the cluster itself.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Kubernetes** | open (Apache 2.0) · base | declarative resources, controllers, reconcile loop; thousands of nodes; three releases a year, ~1 year support per version; 1.35: DRA improvements (dynamic GPU/device allocation), in-place pod resource changes; managed in every cloud; self-installed needs constant upgrade attention | many services and teams; one platform for everything | a couple of services and one developer; no one responsible for the cluster |
| **k3s** | open (Apache 2.0, CNCF, SUSE/Rancher) · pop | certified k8s in one binary; embedded etcd, SQLite or external Postgres; Traefik and local-path by default; Raspberry Pi to hundreds of nodes; tracks upstream (1.35.x) | own small cluster, edge, labs, office servers | needing managed-level support |
| **Talos Linux** | open (MPL 2.0) · pop | immutable OS only for k8s: no SSH, no shell, no package manager, managed via API with one YAML; Omni for fleets; 1.12 branch | own production cluster on hardware with a security focus | needing anything else on the nodes |
| **HashiCorp Nomad** | src (BSL 1.1, HashiCorp → IBM) · base | one binary; HCL jobs; drivers Docker, exec, Java, QEMU; Consul, Vault; community shrank after the licence change | mixed loads: containers + binaries + VMs | the k8s ecosystem; an open licence |
| **Docker Swarm** | open (Apache 2.0, Mirantis) · base | `docker stack deploy` with the same Compose file across machines; tens of nodes; base of Dokploy; alive but almost no new features | 2–5 servers, a team that knows Compose | a long-term growing platform |

### PAAS — self-hosted PaaS and deploy tools
"Heroku on your server": push to git → build → deploy with HTTPS, databases and logs. Covers 80% of small-project needs without k8s. Key question: **how the panel itself is updated and who owns its security.**

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Coolify** | open (Apache 2.0) · pop | panel managing many independent servers; deploy from git, Docker, Compose; 280+ one-click services; databases, S3 backups, preview deploys; panel uses 0.5–1.2 GB RAM. **11 CVEs in 2025–2026 (all fixed)** — a panel with access to every server must be updated at once and not exposed without protection | client projects and MVPs on own VPSes; teams without DevOps | clustering and balancing across servers; a panel on the open internet without SSO and updates |
| **Dokploy** | src (Apache 2.0 + proprietary directories; moving to a clearer source-available model) · grow | apps, Compose, databases, templates; real multi-server cluster via Swarm with balancing; Traefik; ~350 MB RAM | several servers with balancing without k8s | needing an unambiguously open licence |
| **Kamal** | open (MIT, 37signals) · pop | config in the repo, `kamal deploy` over SSH to any Docker machine; zero-downtime, automatic TLS via kamal-proxy; accessories (databases, Valkey); nothing else on the server; 37signals left the cloud with it | deploying from CI without panels or agents; moving between clouds (only IPs change) | a web UI for non-developers |
| **Dokku** | open (MIT) · base | `git push dokku main`; buildpacks or Dockerfile; Postgres, Valkey, Let's Encrypt plugins; one server (k3s mode exists); 10+ years | one server, several apps, zero complexity | several servers |

### REGISTRY — image and artifact registries
Store OCI images, Helm charts, other artifacts. A good registry scans for vulnerabilities, stores signatures (**cosign**) and SBOMs, and caches Docker Hub (which has pull limits).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Harbor** | open (Apache 2.0, CNCF graduated) · base | OCI, Helm, any OCI artifact; Trivy scanning, signatures, RBAC, OIDC; proxy cache for Docker Hub, GHCR…; projects with quotas, "don't run images with critical CVEs" policies, replication; several services + Postgres + Redis | a company registry; a Docker Hub mirror in a closed network | one developer (heavy) |
| **Zot** | open (Apache 2.0, CNCF) · pop | one Go binary, OCI only, any artifacts; scanning, signatures, OIDC; sync and mirrors | a light own registry, edge, small teams | Harbor's rich admin |
| **Forgejo / Gitea / GitLab registry** | open (GPLv3 Forgejo / MIT Gitea) · pop | packages next to code: Docker, npm, PyPI, Maven, Cargo…; repo permissions; no cache; Forgejo is the non-profit Gitea fork under Codeberg | a small team with its own git | Harbor-level image security policies |

### CI/CD — CI/CD and GitOps
CI builds and tests, CD rolls out. Pipeline security: **actions pinned by commit SHA**, runners hold no extra secrets, cloud access via **OIDC, not static keys** (see `access.md`, the Trivy incident).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **GitHub Actions** | prop (SaaS, runner open) · base | YAML workflows, marketplace (a strength and the main supply-chain risk); hosted or self-hosted runners; OIDC to clouds, environments with review; hosted runners up to 39% cheaper since 1 January 2026; a $0.002/min self-hosted fee was announced for March 2026 then postponed | code already on GitHub; quick CI start | actions by tag without SHA pinning; everything-in-own-perimeter requirements |
| **GitLab CI** | open (MIT CE) + EE · base | `.gitlab-ci.yml`, stages, DAG; GitLab Runner anywhere; protected variables, OIDC, scanners in EE; full DevOps platform; popular in CIS companies with their own perimeter; CE self-hosted free | own git + CI in one with enterprise features | small servers (GitLab is heavy) |
| **Forgejo Actions / Woodpecker** | open (GPLv3 / Apache 2.0) · pop | Forgejo Actions uses GitHub Actions syntax (many actions reusable); Woodpecker = minimal container pipelines (Drone fork); own runners | own git and CI on one small server | the whole GitHub ecosystem |
| **Dagger** | open (Apache 2.0) · grow | pipelines in Go, Python, TS run in containers, identical on a laptop and any CI with a shared cache; ends "works in CI, not locally" | complex builds portable between CIs | simple pipelines (YAML is enough) |
| **Argo CD** | open (Apache 2.0, CNCF graduated) · base | Application → git repo → cluster, pull-based; RBAC, SSO, CI has no cluster access; v3 (2025); resource tree and drift UI; ApplicationSet for many clusters/environments | GitOps for teams that value a UI | no Kubernetes |
| **Flux** | open (Apache 2.0, CNCF graduated) · base | source, kustomize, helm, image-automation controllers; multi-tenancy, OCI signature verification; community + ControlPlane after Weaveworks closed; no heavy UI, all CRDs | strict GitOps without a UI; multi-tenant clusters | needing a visual interface (→ Argo CD) |

### IAC — infrastructure as code
Clouds, DNS, networks, databases and permissions in code, reviewed and applied automatically. Central entity: **state** — stored remotely, locked and encrypted.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenTofu** | open (MPL 2.0, Linux Foundation / CNCF sandbox) · pop | HCL, Terraform-provider compatible; 1.12 branch; **client-side state and plan encryption** (incl. OpenBao keys), provider `for_each` for multi-region, early variable evaluation, `enabled`, dynamic `prevent_destroy` | new IaC projects with an open licence; multi-cloud and frequent migrations | HCP Terraform features |
| **Terraform** | src (BSL 1.1, IBM since February 2025) · base | HCL, the largest registry; ephemeral resources, Stacks, HCP integration; BSL barely matters internally (restricts products competing with HashiCorp); **the HashiCorp registry is restricted in some countries — Yandex Cloud runs its own provider mirror** | existing projects and HCP Terraform | your own product competing with HashiCorp |
| **Pulumi** | open (Apache 2.0 engine; Pulumi Cloud paid) · pop | TS, Python, Go, C#, Java, YAML; own providers + Terraform bridge; loops, functions, tests like normal code; risk of over-clever infra code that is hard to review | complex infrastructure logic; TS or Python teams | simple static infrastructure (HCL reads easier) |
| **Crossplane** | open (Apache 2.0, CNCF graduated, v2) · pop | cloud resources as k8s CRDs + Compositions (Go, Python, KCL functions); continuous reconcile fixes drift; created via `kubectl apply` and GitOps; base of internal platforms | a self-service internal platform on k8s | no k8s or a small team |
| **Ansible** | open (GPLv3, Red Hat) · base | agentless YAML playbooks over SSH, thousands of modules; configures existing servers and network gear; result depends on prior machine state | Debian/RHEL server fleets, network equipment | creating cloud resources (→ OpenTofu) |

### BACKUP — backups
Deduplication, client-side encryption, S3 storage, retention (7 daily, 4 weekly, 12 monthly). For databases: physical backups + **WAL archive for PITR**.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **restic** | open (BSD-2) · base | deduplicated snapshots to S3, SFTP, local, rclone backends; always encrypted client-side; one binary. **Enable bucket object lock or rest-server append-only so a hacked server cannot delete its backups** | server and volume backups to S3 | consistent backups of a running database (needs a dump or the DB's tool) |
| **BorgBackup / Borgmatic** | open (BSD-3) · base | dedup + compression repositories over SSH (BorgBase, Hetzner Storage Box); client-side encryption; Borgmatic adds config and DB hooks; **2.x repo format incompatible with 1.x** — check status first | backups to SSH storage | straight to S3 (→ restic or Kopia) |
| **Kopia** | open (Apache 2.0) · pop | snapshots, dedup, compression to S3, B2, GCS, Azure, SFTP, WebDAV; client-side encryption; desktop and web UI | laptops and workstations | — |
| **pgBackRest** | open (MIT) · base | full, differential, incremental + WAL archive; S3, Azure, GCS, POSIX; encryption, parallelism, PITR, backup verification. Sole long-time maintainer stepped back in June 2025; in May 2026 AWS, Percona, Supabase, pgEdge and Tiger Data pledged ≥$2M over two years, Percona funds a full-time maintainer | large production Postgres | small databases (scheduled pg_dump is simpler) |
| **Barman / WAL-G** | open (GPLv3 / Apache 2.0) · pop | physical backups + WAL; Barman (EDB) with a dedicated backup server; WAL-G cloud-oriented (S3), used by many managed services, also MySQL, MongoDB, Redis | Postgres PITR stored in S3 (WAL-G) | — |
| **Velero** | open (Apache 2.0) · base | k8s manifests + PV snapshots to S3; restore into another cluster; databases inside k8s still need their native tools | cluster backup and migration | consistent DB backups (→ pgBackRest, WAL-G) |

## Clouds

Moving is easiest when the app is an **OCI image**, infrastructure is in **OpenTofu**, and deploy goes through **GitOps or Kamal** — then only the provider in code changes, not the whole process.

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | Managed Service for Kubernetes | managed k8s with node autoscaling | service platform |
| | Container Registry / Cloud Registry | images and artifacts with scanning | images |
| | Serverless Containers | container on request, pay per run time | APIs and jobs without servers |
| | Compute Instance Groups | VM groups with autoscaling | classic deploy |
| | Cloud Backup | VM and server backup | backups |
| | Terraform provider + registry mirror | IaC for Yandex Cloud | OpenTofu and Terraform |
| | (some prices changed on 1 May 2026 — check the calculator) | — | — |
| DigitalOcean | DOKS | managed k8s, free control plane | service platform |
| | App Platform | PaaS from git or image | apps without k8s |
| | Container Registry | images | images |
| | Backups / Snapshots | Droplet and volume backups | backups |
| | Terraform provider | IaC | — |
| Railway | Deploy from GitHub / image | build and deploy on push | main path |
| | Railpack (replaces Nixpacks) | stack detection and image build | builds without a Dockerfile |
| | Environments / PR environments | environments and temporary ones | staging and previews |
| | Volume backups | volume backups | template database data |
| | Config as code (`railway.toml` / `.json`) | reproducible service config | — |
| | (no k8s and no low-level control — both a plus and a limit) | — | — |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | EKS / EKS Auto Mode; ECS + Fargate (containers without k8s or servers); ECR; CodeBuild / CodePipeline; AWS Backup; CloudFormation / CDK (AWS only) |
| Google Cloud | GKE / Autopilot; Cloud Run (serverless containers, GPU); Artifact Registry; Cloud Build / Cloud Deploy; Backup and DR |
| Azure | AKS; Container Apps (serverless containers on k8s with KEDA and Dapr); ACR; Azure DevOps / GitHub; Azure Backup / Bicep |
| Cloudflare | Workers; Containers (GA 13 April 2026: ephemeral containers called from a Worker, pay for active CPU — not for databases or long-lived stateful services); Sandboxes (persistent isolated environments for agent code); Workers Builds |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| 1–3 servers, several apps | Docker Compose + Kamal | a panel for the team → Coolify; several servers with balancing → Dokploy |
| Many services and teams | the cloud's managed Kubernetes | own hardware → Talos or k3s |
| Edge, office servers, labs | k3s | — |
| Own image registry | Zot | a company with security policies → Harbor |
| CI for code on GitHub | GitHub Actions pinned by SHA with OIDC | everything in own perimeter → Forgejo Actions or GitLab CI |
| Portable complex pipelines | Dagger | — |
| Deploying to Kubernetes | Argo CD | strict GitOps without a UI → Flux |
| Cloud resources in code | OpenTofu | complex logic → Pulumi; platform on k8s → Crossplane |
| Configuring ordinary servers | Ansible | — |
| Server backups | restic to S3 with object lock | SSH storage → Borg; workstations → Kopia |
| Postgres backups | pgBackRest or WAL-G with PITR | small database → scheduled pg_dump |
| Kubernetes backups | Velero + native DB tools | — |
| Frequent migrations between clouds | OCI images + OpenTofu + Kamal or GitOps | — |
