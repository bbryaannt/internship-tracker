# Verified Notion mapping

Inspected through authorized Notion API reads on 2026-10-20. Machine-readable IDs and types are centralized in `notion_mapping.json`.

- Tracker: 2026–2027 Intern Madness (`3ee90d2e-cd48-83ff-9bf8-018a18a29562`). This is the parent page, not the write destination.
- Bryant's database: Job & Internship Tracker (`b4990d2e-cd48-83e3-beba-8174946cd0d9`). It appears under the Bryant Barrio section, separately from other people's databases.
- Opportunity data source: `dc590d2e-cd48-828f-8221-8743b81a2279`.
- Assignment: `Person` is a **relation**, pointing to the `Bryant` count row (`b34b89c1-d1b5-4174-941f-6c7d8fd0ac39`) in Internship Count (`9ce0f9b2-380b-4e15-a7d0-c0725663d065`). Existing Bryant entries populate this relation. Its reverse is `Bryant positions`, used by the `Bryant total` rollup. Both correct database placement and this relation are required.
- Exact status: `Not applied`, option ID `59579075-87a7-4947-a98b-f5a5e7c68d72`. Preserve this capitalization. Do not use `Not applied / Past` or create a new option.

| Existing property | Type | Mapping |
| --- | --- | --- |
| Position | title | Verified job title |
| Company | rich_text | Verified company name |
| Application Link | url | Original supplied posting URL |
| Application Status | status | Existing Not applied option by ID |
| Person | relation | Existing Bryant count row |
| Application ID | rich_text | Public posting/requisition ID when verified; existing entries use IDs or N/A |
| Notes | rich_text | Verified location, department, compensation, duration and other metadata |

The source has no dedicated season, salary, location or qualification properties. Supplementary information belongs in Notes and the page body. Full verified posting text is retained in paragraph blocks, consistent with existing entries having paragraph bodies. Unknown dates, season and pay period are omitted rather than inferred. Existing records, count rows, schema and status options are never directly updated. Assigning the relation lets Notion maintain its existing reverse relation and rollup automatically.

All 84 current Bryant entries were retrieved using paginated queries. Live duplicate detection recognized the existing Vast Mechanical/Aerospace Engineering Internship without changes. A separate Vast Electrical Engineering Internship produced a new-entry dry run.

## Approved live test completed

The user explicitly approved the Vast Electrical Engineering Internship preview. Page `3ff90d2e-cd48-81ae-8bd9-c81a6828d424` was created once on 2026-10-20. Read-back verified the destination, every mapped property, original URL, Person relation, exact Not applied option and paragraph body. A separate paginated property read verified the page appears in Bryant's `Bryant positions` reverse relation; the linked count increased from 84 to 85.

`first_live_verified` is now true, with evidence recorded in the mapping. Normal skill invocations may add new internships with `--create` without repeated confirmation under the user's standing authorization. Existing records/statuses and the database schema must never be modified. If the destination changes, inspect and validate the new mapping before writing.

Notion views are not exposed by this API; database placement and relation are verified, but visual appearance in the user's UI remains a manual check. Cross-device execution/discovery and simultaneous writers across separate cloud machines are not verified. Notion has no atomic uniqueness constraint; serialize intake tasks to avoid concurrent race conditions.
