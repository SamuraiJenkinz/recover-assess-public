# API Coverage — Microsoft Graph v1.0 (read-only subset)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
>
> Phase 1 integrates only the read-only, allow-listed subset of Microsoft Graph that the Step 1 collectors need (13 templates, pinned by `tests/graph/test_allowlist_pinned.py`, packaged in `src/recover_assess/core/graph_allowlist.yaml`, D-08). Everything that writes, downloads content or leaves Graph v1.0 is opted out by design: the read-only promise (GRPH-01) is the product. Adding any row below as INTEGRATE is a reviewed code change to the pinned allow-list, never a configuration change.

| capability | decision | reason |
|---|---|---|
| GET /sites/{site-id} (site_by_id) | INTEGRATE | |
| GET /sites/{hostname}:/{+path} (site_by_path) | INTEGRATE | |
| GET /sites/{site-id}/sites (subsites) | INTEGRATE | |
| GET /sites/{site-id}/lists (lists) | INTEGRATE | |
| GET /sites/{site-id}/lists/{list-id}/drive (list_drive) | INTEGRATE | |
| GET /sites/{site-id}/lists/{list-id}/columns (columns) | INTEGRATE | |
| GET /sites/{site-id}/lists/{list-id}/contentTypes (content_types) | INTEGRATE | |
| GET /sites/{site-id}/lists/{list-id}/items (list_items) | INTEGRATE | |
| GET /drives/{drive-id}/root/delta (drive_delta) | INTEGRATE | |
| GET /drives/{drive-id}/items/{item-id}/permissions (item_permissions) | INTEGRATE | |
| GET /sites/{site-id}/drive (site_drive) | INTEGRATE | |
| GET /groups/{group-id}/owners (group_owners) | INTEGRATE | |
| POST /$batch whose sub-requests are allow-listed GETs (batch) | INTEGRATE | |
| @odata.nextLink paging (validated follow) | INTEGRATE | |
| Throttling signals: Retry-After on 429/503, per-sub-response Retry-After | INTEGRATE | |
| Any write verb (POST outside $batch, PUT, PATCH, DELETE, MERGE) on any resource | OPT-OUT | read-only trust promise — GRPH-01 |
| $batch sub-requests other than GET, with body or dependsOn | OPT-OUT | read-only trust promise — GRPH-01 |
| Site permission grants (POST /sites/{id}/permissions) | OPT-OUT | read-only trust promise — GRPH-01; grants plan (INP-06, Phase 3) only prints bodies for an admin and never calls the endpoint |
| Sharing link creation, invites, checkout, preview (createLink, invite, checkout, preview) | OPT-OUT | read-only trust promise — GRPH-01 |
| File content download (/content, $value, @microsoft.graph.downloadUrl) | OPT-OUT | not in v1 — GRPH-02; sample tier is v2 (SMP-01) |
| Graph beta endpoints (/beta/...) | OPT-OUT | explicitly out of scope — v1.0 only (REQUIREMENTS Out of Scope, D-09) |
| Tenant-wide site enumeration and search (/sites?search=, getAllSites) | OPT-OUT | explicitly out of scope — sites are named explicitly; display-name resolution is v2 (V2-03) |
| Delta resync via @odata.deltaLink / $deltatoken | OPT-OUT | not needed yet — deltaLink is surfaced but not followed in Phase 1; Phase 4 delta spike decides |
| Delta function-call nextLink form delta(token='...') | OPT-OUT | not needed yet — rejected fail-closed until the Phase 4 live delta spike confirms the shape (assumption A15) |
| Graph SDK (msgraph-sdk / Kiota) | OPT-OUT | explicitly out of scope — cannot enforce read-only by construction (CLAUDE.md "What NOT to Use") |
| Change notifications / webhooks / subscriptions | OPT-OUT | explicitly out of scope — point-in-time assessment, no continuous monitoring |
| Authentication endpoints (login.microsoftonline.com via MSAL, IMDS) | OPT-OUT | not needed yet — Phase 2 (AUTH-01, AUTH-05, AUTH-06) and Phase 11 (AUTH-02, AUTH-03); Phase 1 injects a token callable |
| LLM provider APIs (Azure OpenAI via the corporate gateway, Bedrock) | OPT-OUT | not needed yet — Phase 9 (LLM-01..08) |
