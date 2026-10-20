# Internship tracker skill — partial implementation

This is a repository-scoped Codex skill for cloud execution. It currently implements conservative public JSON-LD extraction, URL normalization, independent batch error handling, and read-only Notion discovery. It uses Python 3.12+ standard-library modules only. It does **not** yet add or deduplicate Notion entries. The user's required schema inspection must precede write implementation.

## Run now

From the checkout root:

```sh
python3 -m unittest discover -s tests -v
python3 .agents/skills/internship-tracker/scripts/extract_job.py 'https://company.example/careers/single-job'
mkdir -p .local
python3 .agents/skills/internship-tracker/scripts/inspect_notion.py --output .local/notion-inspection.json
```

Replace the example with a real posting. Only pages containing one complete JobPosting JSON-LD object are currently supported. Workday, Greenhouse, Lever, LinkedIn, Handshake, and company sites have **not** been validated. JavaScript-only or login-protected pages return failures; they are not silently treated as complete jobs. There is no running server or installation step.

## Secure initial Notion setup

Create a Notion internal connection with read and insert-content capabilities and share the existing tracker with that connection. Enter the credential securely as `NOTION_TOKEN` in cloud environment settings. A proxy binding must target `api.notion.com`; never place credentials in Git, job URLs, reports, or chat. No update/delete operations are implemented.

The saved network draft includes api.notion.com, app.notion.com, boards-api.greenhouse.io, boards.greenhouse.io, job-boards.greenhouse.io, api.lever.co, and jobs.lever.co, retaining the package-manager preset. Individual company career hosts and redirect destinations need explicit permission before use. Do not replace the allowlist with unrestricted access merely to make extraction work.

Review and save environment changes, then retry the inspector. If inaccessible linked databases are not exposed, share their underlying sources with the connection too. Do not guess the destination from the tracker page name. A first-live-test preview and explicit approval are still required.

## Persistence and device checks

The skill lives at `.agents/skills/internship-tracker/SKILL.md`. Keep it in this project repository so the same implementation can be used in future cloud tasks. The current files must be committed and made available to the cloud checkout before repository-based persistence is established. Publishing a cloud snapshot is a separate product operation; local files do not prove fresh-session restoration or skill discovery.

After publishing the prepared environment and preserving this project in the repository:

1. Start a new cloud task for the same repository. Confirm `internship-tracker` appears in its available skills and invoke `$internship-tracker <official-internship-url>`. If it is not discovered, ask Codex to read and follow the repository's SKILL.md explicitly, and report native discovery as unverified.
2. On Mac, initiate a cloud task through your available Codex interface. No local Mac service is required.
3. On iPhone, open your available Codex cloud interface with the same account, select this repository/environment, and attempt the same invocation. Confirm that it runs a cloud task with this skill and the same tracker mapping. Repeat while the Mac is off. Exact iPhone UI availability, account entitlements, and native `$skill` invocation cannot be tested from this machine.
4. Once schema mapping and the approved live test are implemented, submit the same posting from both devices and verify that the second invocation returns the existing entry without changing it.

These are **pending manual checks**, not supported claims of successful mobile operation. If your phone interface can start cloud tasks but cannot invoke `$skill`, use a plain-language request to follow the repository skill. If no phone cloud-task interface is available, choose a supported authenticated automation/hosting option before building an intake endpoint. No public service is deployed and no ongoing hosting cost is introduced.

## Validation limits

Fixture tests exercise actual parsing, missing/ambiguous metadata, URL identity, private-address rejection, batch continuation, and credential gating. They do not substitute for real-posting extraction, authorized Notion inspection, duplicate tests, dry-run mapping, an approved live write, or cloud/mobile testing. See `references/notion_schema.md` for the explicit integration gate.
