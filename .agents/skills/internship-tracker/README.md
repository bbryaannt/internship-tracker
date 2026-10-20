# Internship tracker

Repository-scoped cloud skill using Python 3.12+ standard library only. No installation, Mac process, or long-running server is required.

## Current validation

- Authorized Notion inspection succeeded; Bryant's data source, Person relation, existing Not applied option, and property mapping are verified in `references/notion_schema.md` and `notion_mapping.json`.
- Live reads retrieved all 84 Bryant opportunities. A real Vast Mechanical/Aerospace posting returned the existing record without changes.
- Official Greenhouse extraction succeeded for a real Vast Electrical Engineering Internship. Dry run produced its typed properties and page body.
- 23 automated tests pass, covering extraction, URL identity, pagination, duplicate ambiguity, dry-run and approval gates, schema-related types, read-back validation and uncertain-write retry prevention.
- The user-approved first live Vast Electrical Engineering Internship was created and read back successfully. Destination, all mapped properties, page body and Bryant’s reverse relation passed verification. `first_live_verified` is true; normal invocations may now create new records without repeated confirmation.

## Commands

From the checkout root:

```sh
python3 -m unittest discover -s tests -v
python3 .agents/skills/internship-tracker/scripts/extract_job.py '<official-job-url>'
python3 .agents/skills/internship-tracker/scripts/add_internship.py '<official-job-url>'
```

The last command is a **dry run**. It inspects the live schema and all existing destination records, then returns either an existing entry, ambiguity, failure, or a proposed entry. URL batches are accepted as additional positional arguments. Partial failure returns exit 1 while processing other URLs.

The approved first live test has passed. Normal skill invocations use `--create` under the user’s standing authorization to add new records; direct CLI calls remain dry-run by default. Example: `python3 .agents/skills/internship-tracker/scripts/add_internship.py --create "<official-job-url>"`. No existing pages or statuses are updated. The original first-entry approval gate remains implemented for unverified mappings.

## Extraction coverage

Public single-job JSON-LD and the official Greenhouse board API are implemented. The API fallback handles JavaScript-only Greenhouse pages; verified board metadata supplies the company name rather than guessing it from a URL slug. Original posting URLs are preserved. Full description text and verified supplementary metadata go to the existing Notes property and page body; missing information remains absent. Pay period is never assumed from a bare amount.

Workday, Lever-specific APIs, LinkedIn, Handshake and arbitrary JavaScript rendering are not validated. These sites work only when an accessible page provides supported metadata. Unsupported or login-protected pages fail clearly, rather than generating misleading entries. The extractor restricts public HTTPS destinations, checks DNS addresses where available, and allows proxy-only DNS for exact known recruitment hosts; other proxy-only company domains need a supported route before extraction.

## Secure configuration

`NOTION_TOKEN` is supplied through cloud secret settings, targeted to api.notion.com. Never put credentials in Git, chat, logs or posting URLs. The connection needs read and insert-content access to the existing tracker. Reports and write journals in `.local/` are ignored and must stay private.

Saved network settings include api.notion.com, app.notion.com, boards-api.greenhouse.io, boards.greenhouse.io, job-boards.greenhouse.io, api.lever.co, and jobs.lever.co, preserving the package-manager preset. Individual company/redirect hosts may require additional domain permissions. Do not replace the allowlist with unrestricted access as a workaround.

Read-only reinspection:

```sh
mkdir -p .local
python3 .agents/skills/internship-tracker/scripts/inspect_notion.py --output .local/notion-inspection-new.json
```

The inspector refuses to overwrite reports, retrieves schemas and sample pages, and flags linked-view limitations. Schema drift or a changed Bryant relation blocks writes.

## Duplicate and failure limits

All current destination pages are queried, not just a sample. Normalized URLs and company-scoped job IDs establish matches. Same company/title with missing identifiers is ambiguous; different verified IDs remain separate. Matches are returned without modification, and ambiguous duplicates block creation.

Read requests retry bounded rate limits and transient errors. A creation request is never blindly retried. A private journal records pending/created/verified states. Investigate uncertain attempts and read-back failures before another create; never remove a journal to force one.

Run one intake task at a time. A local file lock and a second query protect one machine; Notion lacks an atomic unique key, so simultaneous independent cloud machines can still race. Strict cross-machine uniqueness requires a shared coordinator and is not claimed here.

## Cross-device use and persistence

Keep `.agents/skills/internship-tracker/` in this repository on the selected cloud branch, then publish the prepared cloud environment after configuration review. Processes and temporary authentication should never be assumed to survive publication; startup instructions are saved separately. Local commits/snapshots do not by themselves prove repository restoration.

Pending manual checks:

1. Open a fresh cloud task for this repository/environment. Confirm `internship-tracker` appears in the available skill list and invoke `$internship-tracker <job-url>`. Current-session file creation does not prove fresh-task discovery.
2. Initiate that cloud workflow from the Mac's available Codex interface; no Mac service is involved.
3. On iPhone, use an available Codex cloud interface with the same account, repository and environment. Try the same invocation with the Mac switched off. Account availability, mobile UI and native skill invocation cannot be verified from this machine.
4. If the interface starts cloud tasks but lacks native `$skill` support, ask: “Read and follow .agents/skills/internship-tracker/SKILL.md for this URL: …”. If no mobile cloud-task interface is available, select a supported authenticated automation/hosting entry point before deploying infrastructure. None has been deployed.
5. Submit the same job from both devices. The second request should link the existing entry without changing its status. Also confirm its visual placement under Bryant Barrio; the Notion API cannot inspect view filters.

Do not claim these checks passed until they have actually been run.
