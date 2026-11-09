# Layer: access and secrets

Source: Alexey's «Доступ и секреты» (checked 30 October 2026). Who you are (identity), what you may do (authorization), where keys and passwords live (secrets, PKI), how to reach the internal network (ZTNA), who watches for attacks (perimeter and runtime defence). Security tools are supply-chain targets themselves: pin versions and verify signatures.

How we build our own auth service is in the `auth-service` skill; secrets in git are in the `sops` skill; review-time checks are in `security-review`. This file is about **choosing** components.

Marks: licence **open / src / prop**; status **base / pop / grow** (grow = young, carries risk).

## Concepts

- **AuthN vs AuthZ.** Authentication = who you are (login, password, passkey, SSO, token issue). Authorization = what you may do with this object. An IdP solves the first; the second almost always stays in the app or a separate policy engine.
- **RBAC · ABAC · ReBAC.** Roles; attributes ("department = finance and working hours"); relationships ("editor of the folder that contains the document", Google Zanzibar). Multi-tenant SaaS usually needs ReBAC.
- **Secrets and workload identity.** The best secret is one that does not exist: a service gets a short-lived token from its identity (CI OIDC, SPIFFE, IAM role). Where a key is unavoidable — dynamic secrets with TTL and rotation.

## Rule 0

**Do not write your own authentication or cryptography** — take a ready IdP or a proven library. Secrets never sit in git, in env files on the server, or in CI variables in plain text: only encrypted (SOPS) in the repo, from a secret manager at runtime. **CI actions are pinned by commit SHA, not by tag.**

## Classes and technologies

### IDP — identity and SSO
Login, sign-up, MFA, passkeys, recovery, SSO for staff and customers; OIDC, OAuth 2.1, SAML. Workforce (staff, internal services) vs CIAM (your product's users).

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Keycloak** | open (Apache 2.0, CNCF) · base | Java (Quarkus) + Postgres; OIDC, OAuth 2.0, SAML 2.0, LDAP/AD federation; realms, MFA, passkeys, social brokering, fine-grained rights; themes via FreeMarker or Keycloakify (React); heavy, complex, major upgrades need care | corporate SSO with AD/LDAP; many apps on different protocols; banks and government requiring self-hosted | a startup needing a login page tonight; low-memory servers |
| **Authentik** | open (MIT + Enterprise) · pop | Python + Go + Postgres; OIDC, OAuth, SAML, LDAP provider, RADIUS, SCIM; flows and stages built in the UI; **outpost forward-auth proxy puts SSO in front of apps without OIDC**; serves LDAP for old systems | SSO for office internal services; putting a login in front of old admin panels | CIAM for millions of users |
| **Zitadel** | open (AGPLv3 since v3, March 2025; SDKs/APIs Apache 2.0) · pop | Go + Postgres; OIDC, OAuth, SAML, SCIM; **each SaaS customer is an organisation with its own users and SSO**; event-sourced, full audit; passkeys, actions | B2B SaaS where each customer has its own SSO; full change audit | modifying the core and offering it as a service without publishing |
| **Ory (Kratos, Hydra, Keto)** | open (Apache 2.0 core) · pop | Go, headless — you draw the pages; Kratos users and login, Hydra OpenID-certified OAuth server, Keto permissions; some enterprise features commercial | your own login UX on a safe backend; an OAuth server for your API | a ready solution with an admin UI |
| **Authelia** | open (Apache 2.0) · pop | Go, YAML config; forward-auth next to Traefik, Caddy, Nginx + OIDC provider; 2FA, passkeys, per-domain rules; users from a file or LDAP; tiny footprint | login + 2FA in front of internal services | product user sign-up |
| **Kanidm** | open (MPL 2.0) · grow | Rust IdM; OIDC, LDAPS, RADIUS, SSH keys, POSIX accounts; passkeys first; replaces FreeIPA and OpenLDAP with secure defaults | one account for Linux servers, Wi-Fi and services | SAML-dependent enterprise apps |
| **Better Auth** | open (MIT) · grow | a TypeScript **library**, users in your DB; sessions, OAuth login, can act as an OIDC provider; plugins: 2FA, passkeys, organisations, SSO, API keys; the new default in Next.js/Node instead of hand-rolled auth | MVP and SaaS in TS without a separate IdP | one login across many different apps (→ an IdP) |
| **Auth0 / Clerk / WorkOS** | prop (SaaS; Auth0 is Okta) · pop | OIDC, SAML, social; ready UIs, MFA, bot defence; WorkOS = enterprise SSO for B2B; price grows with users, data at the vendor | "launch yesterday"; B2B SaaS whose customers demand SAML | personal data that must stay in-country; millions of users on a small budget |

### AUTHZ — authorization and policy engines
A separate engine answers "allowed or not": rights in one place, testable and auditable, same in all services. Models: Zanzibar (ReBAC) and policy-as-code.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **OpenFGA** | open (Apache 2.0, CNCF) · pop | Zanzibar-like from Auth0/Okta; types, relations, tuples in a DSL; Postgres, MySQL, SQLite; ListObjects to filter lists | multi-tenant SaaS with document/folder sharing; complex permission hierarchies | simple admin/user roles |
| **SpiceDB** | open (Apache 2.0, AuthZed) · pop | the most mature open Zanzibar; schema language + caveats; Postgres, CockroachDB, Spanner, MySQL; ZedTokens solve the new-enemy problem (checks consistent with data changes); fast | large systems with millions of objects and strict consistency | small projects |
| **OPA (Rego)** | open (Apache 2.0, CNCF graduated) · base | policy-as-code over JSON; standard for k8s admission (Gatekeeper), Terraform checks (Conftest), Envoy authz; Styra founders moved to Apple in 2025, project stays in CNCF | Kubernetes and IaC policies; one rule set for infrastructure | per-user rights over millions of objects (Zanzibar engines fit better); teams struggling with Rego |
| **Cerbos** | open (Apache 2.0) · pop | stateless PDP: pass principal + resource attributes, get a decision; YAML + CEL; policies in git, tested in CI; generates DB query filters | app rights readable by non-developers; policies in git with tests | complex object relationships (→ ReBAC) |
| **Cedar** | open (Apache 2.0) · grow | AWS language designed for formal analysis (prove no policy grants too much); RBAC + ABAC, partly ReBAC; Rust library with bindings; base of AWS Verified Permissions | provable policies; AWS Verified Permissions | a ready service with a relationship store |
| **Casbin** | open (Apache 2.0) · base | embedded library (Go, Node, Python, Java, Rust); ACL/RBAC/ABAC via a PERM model config; DB adapters | simple RBAC inside a monolith | distributed systems with shared rights |

### SECRETS — secrets and PKI
Storing and issuing passwords, keys, tokens, certificates: encryption at rest, audit of every read, **dynamic secrets with short TTL**, automatic rotation and certificate issuance.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **HashiCorp Vault** | src (BSL 1.1 since 2023, HashiCorp → IBM) · base | secret engines KV, databases (hour-long dynamic logins), PKI, SSH signing, Transit (encryption as a service); auth methods k8s, OIDC, AppRole, clouds; Raft storage; namespaces and cross-DC replication Enterprise-only | budget for Enterprise or a vendor requirement; complex dynamic-secret scenarios | an open licence (→ OpenBao); small projects (too heavy) |
| **OpenBao** | open (MPL 2.0, OpenSSF / Linux Foundation) · pop | Vault fork from before the licence change; API-compatible (clients and Terraform providers work); 2.x adds namespaces (Enterprise-only in Vault) | Vault features with an open licence; self-hosted and government | needing official support from a big vendor |
| **Infisical** | open (MIT + Enterprise) · pop | projects, environments, folders; CLI, SDKs, k8s operator, CI integrations (GitHub Actions, Vercel, k8s sync); Postgres + Redis; leak scanner, PKI, dynamic secrets; lower barrier than Vault | dev teams without a dedicated security engineer; replacing `.env` files | enterprise-level PKI and Transit |
| **SOPS** | open (MPL 2.0 / MIT; SOPS is CNCF) · pop | encrypts values in YAML/JSON/ENV (keys stay readable, diffs work) with age, PGP, cloud KMS, Vault; decrypt at deploy into tmpfs with the right permissions — GitOps for secrets without a server | GitOps infrastructure; small teams without Vault | dynamic secrets and rotation; audit of every read |
| **step-ca / cert-manager** | open (Apache 2.0; cert-manager CNCF graduated) · pop | step-ca = private CA with ACME, OIDC, short-lived certs for mTLS and SSH inside the network; cert-manager issues and renews certs in k8s from any source | mTLS between services without a mesh; SSH certificates instead of scattered keys | public sites (just Let's Encrypt) |
| **External Secrets Operator** | open (Apache 2.0, CNCF) · pop | `ExternalSecret` CRD → k8s Secret from Vault, OpenBao, AWS, GCP, Azure, Yandex Lockbox, Infisical…; releases paused in August 2025 when the sole maintainer burned out, new maintainers by June 2026 — a **single-maintainer risk** example | cloud secret managers into k8s | secrets that must never reach etcd (→ CSI driver) |

### TEAM-PW — team passwords
Password managers for people (shared service logins, per-department vaults, audit) — not machine secret managers. **End-to-end encryption**: the server must not see passwords.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **Vaultwarden** | open (AGPLv3) · pop | unofficial Bitwarden API in Rust + SQLite/Postgres; official Bitwarden clients, E2E on the client; tiny resources; no vendor behind the server | small company, homelab, family | needing vendor support and certifications |
| **Bitwarden** | open (GPLv3 / AGPLv3 + commercial parts) · base | C# + MSSQL/Postgres; organisations, SSO, policies, audit; separate Secrets Manager for machines; enterprise features paid | companies with audit and SSO requirements | — |
| **Passbolt** | open (AGPLv3 CE) · pop | PHP + MySQL; OpenPGP on the client; per-password sharing by groups, audit; browser, mobile, CLI; popular in Europe | IT departments sharing access | personal use |

### ZTNA — network access (VPN and Zero Trust)
Old: VPN "let into the network and trust". New: **Zero Trust** — access to a specific service by identity and device state, checked every time.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **WireGuard** | open (GPLv2, in the Linux kernel) · base | peers with public keys; fast, small code; base of most mesh VPNs; no users, SSO or key distribution (wrappers do that) | site-to-site between offices and cloud; few peers | dozens of users with SSO and ACLs (needs a wrapper) |
| **Headscale** | open (BSD-3) · pop | self-hosted coordinator for official Tailscale clients; ACLs, OIDC login, MagicDNS, subnet routers, exit nodes | a team and server mesh VPN under your control | vendor support and enterprise features |
| **NetBird** | open (BSD-3 client / AGPLv3 management) · pop | WireGuard mesh + access policies; web panel, IdP integrations, SSO, **posture checks** (device state) — close to real ZTNA; fully self-hosted | replacing a corporate VPN with SSO; staff access to office services | modifying the panel and selling it as a service without publishing |
| **Tailscale** | prop (SaaS; clients partly open) · pop | coordinator in the cloud, traffic direct between nodes; ACLs in HuJSON, SSO, SSH, Funnel, Serve, App Connectors; working network in five minutes | a quick team network without admin work | must not depend on an external service |
| **Teleport** | prop (Community Edition own licence, limited for large companies) · pop | access proxy with short-lived certs after SSO for SSH, k8s, databases, apps; access requests, roles, session recording, just-in-time access, audit | audited admin access to servers and databases | an open licence |
| **Pomerium / oauth2-proxy** | open (Apache 2.0 / MIT) · pop | identity-aware proxy checks identity on every request; OIDC, policies by user/group/device; oauth2-proxy simpler, Pomerium full Zero Trust policies | internal admin panels without a VPN | non-HTTP access (→ VPN or Teleport) |

### DEFENSE — perimeter and runtime defence
WAF filters web attacks, IDS sees network attacks, SIEM collects and correlates events, scanners find vulnerabilities in images and dependencies, runtime protection catches suspicious process behaviour.

| Tech | Licence · status | Inside | Good for | Bad for |
|---|---|---|---|---|
| **CrowdSec** | open (MIT) · pop | modern fail2ban: agent parses logs (Nginx, SSH, Traefik…) → decisions → bouncers in proxy, firewall, Cloudflare; community blocklist (attacker IPs blocked before they reach you); AppSec WAF | protecting servers and proxies from brute force and scanners | a full SIEM |
| **Coraza / ModSecurity** | open (Apache 2.0, OWASP) · base | WAF engine + OWASP Core Rule Set (SQLi, XSS, RCE); Coraza in Go embeds in Caddy, Envoy, Traefik, HAProxy; ModSecurity in C. **Start in detection mode** or false positives break the product | your own WAF without a cloud vendor | switching straight to blocking without tuning |
| **Wazuh** | open (GPLv2) · base | host agents + server + OpenSearch indexer; logs, file integrity, vulnerabilities, configuration; detection rules, compliance (PCI and similar checks), active response; needs resources and rule tuning | a SOC for a company without a commercial SIEM budget | a couple of servers (CrowdSec and logs are simpler) |
| **Suricata** | open (GPLv2) · base | C/Rust IDS/IPS on a port mirror or inline; ET Open rules, file extraction, protocol logs as EVE JSON (→ Wazuh, ClickHouse) | office networks, segments with important systems | encrypted traffic without decryption (sees little) |
| **Trivy** | open (Apache 2.0, Aqua) · base | scans images, filesystems, repos, k8s, SBOM for CVEs, secrets, licences, misconfig. **March 2026 compromise**: malicious release 0.69.4 and images 0.69.5–0.69.6; 75 of 76 `trivy-action` tags rewritten to steal CI secrets. Lesson for all tools: pin Actions by SHA, verify signatures, give scanners no extra secrets | CI scanning with pinned versions | running `latest` or an Action by tag; runners with broad cloud rights |
| **Falco / Tetragon** | open (Apache 2.0; Falco CNCF graduated, Tetragon part of Cilium) · pop | eBPF syscall observation + k8s audit; rules like "shell in a container", "read /etc/shadow"; Tetragon can block | k8s and servers with important data | no people to triage alerts |

## Clouds

Cloud IAM controls access to **cloud resources**, not your app's users. App users need your own IdP or a cloud CIAM (Cognito, Identity Platform, Entra External ID). **With frequent migrations keep the IdP and the secret manager cloud-independent.**

**Migration targets:**

| Cloud | Service | What | When |
|---|---|---|---|
| Yandex Cloud | IAM + Cloud Organization | cloud access, SAML/OIDC SSO federations, SAML/OIDC apps | staff login |
| | Lockbox | secret manager with versions and audit; ESO integration | app secrets |
| | KMS | encryption keys, envelope encryption | data encryption and SOPS |
| | Certificate Manager | Let's Encrypt and own certs | TLS |
| | Smart Web Security | WAF, anti-DDoS, anti-bot, limits | public services |
| | Audit Trails | audit of cloud actions | investigations, compliance |
| DigitalOcean | Teams + 2FA/SSO | access to the DO panel | cloud login |
| | App Platform encrypted env | encrypted environment variables | simple PaaS secrets |
| | Cloud Firewalls + VPC | network perimeter | close everything else |
| | (no app IdP or secret manager) | bring your own: Infisical, OpenBao, Keycloak | — |
| Railway | Variables / Sealed variables | env vars, sealed = unreadable after saving; shared project variables | service secrets |
| | Private Networking | services without public exposure | databases and internal APIs |
| | Infisical / Keycloak / Authentik templates | own secret manager and IdP | when audit and SSO are needed |

**Industry standard:**

| Cloud | Services |
|---|---|
| AWS | IAM / Identity Center (workforce SSO); Cognito (CIAM); Verified Permissions (Cedar as a service); Secrets Manager / Parameter Store (rotation); KMS / CloudHSM / Private CA; WAF / Shield / GuardDuty |
| Google Cloud | Cloud IAM / Workforce Identity; Identity Platform (CIAM on Firebase Auth); IAP (Zero Trust app access without VPN); Secret Manager / Cloud KMS / CAS; Cloud Armor / Security Command Center |
| Azure | Entra ID (corporate SSO, conditional access); Entra External ID (CIAM); Key Vault / Managed HSM; WAF / DDoS Protection / Defender for Cloud |
| Cloudflare | Cloudflare One: Access (SSO in front of any app), Gateway + WARP (staff traffic filtering); WAF / Bot Management / Turnstile; Secrets Store for Workers |

## Task → default → when to switch

| Task | Default | Switch when |
|---|---|---|
| SSO for staff and internal services | Authentik | large company with AD and a SAML zoo → Keycloak |
| Login in our own TypeScript product | Better Auth | many apps needing a shared IdP → Zitadel or Keycloak |
| B2B SaaS with SSO per customer | Zitadel | needed yesterday with budget → WorkOS |
| Login + 2FA in front of admin panels | Authelia or Pomerium | already on Cloudflare → Access |
| Rights in a multi-tenant SaaS | OpenFGA | huge scale and strict consistency → SpiceDB |
| Attribute rights readable by the business | Cerbos | — |
| Kubernetes and Terraform policies | OPA (Gatekeeper, Conftest) | prefer YAML over Rego → Kyverno |
| Secrets in GitOps | SOPS | audit of reads and rotation → OpenBao |
| Team secret manager | Infisical | dynamic secrets and PKI → OpenBao |
| Vault with an open licence | OpenBao | — |
| Internal CA and mTLS | step-ca; in k8s cert-manager | — |
| Team passwords | Vaultwarden (small) / Bitwarden (company) | per-department sharing and audit → Passbolt |
| Office and server network | WireGuard site-to-site | people with laptops and SSO → NetBird or Headscale |
| Audited admin access to servers and databases | Teleport | open licence → step-ca SSH certs + Headscale |
| Protecting servers from brute force and scanners | CrowdSec | — |
| SIEM for a company | Wazuh | — |
| Image scanning in CI | Trivy or Grype, **pinned by SHA** | — |
