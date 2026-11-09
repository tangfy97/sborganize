# Explicit domain policy and emoji redesign

The user requested a complete second review after inspecting the real phone.
Every folder needs intuitive emoji, fuller internal pages and better primary-purpose
grouping. Banks/payments and bills span service regions; local mainland-China/Hong
Kong shopping, government and transport retain their regional groups. Banking and
bills should be adjacent. Ground transport and flight/travel, entertainment and AI
are separate. Reading, learning, translation and cloud storage share one group.

## Implementation

`plan --policy PATH` is a separate offline mode. A local schema-1 policy binds to
the exact source fingerprint, enumerates every recognized app including the dock,
and supplies a destination and factual purpose for each. No fallback assignment,
name-language inference or model call is used. Bundle IDs must be unique. Folder
names must contain only emoji; explicit ordering reuses all existing root folder
slots once. Optional adjacent-group pairs are validated. Each folder is packed
from its first page to the configured capacity, nine on the current phone.

This extends conservative behavior only when explicitly selected. Default plans
still cannot rename or move existing folders. `Plan.folder_edits` declares each
source path, target path and new name. Every validation layer checks that only
displayName changed in the original folder metadata. The declaration survives
serialization, XML preparation and the apply safety gate. App payload inventory,
dock, pins and opaque nodes retain their previous strict protections. Folders
with pins, nested folders or unknown children are refused in this mode.

`--source-snapshot` previews a saved layout document with its original source type;
without it the command reads USB. Freshness, backup, confirmation, unchanged
round-trip and readback remain mandatory for live writes. Reports and policies
remain local and private. A new unknown app or changed snapshot needs a new review.

## Output

The separate plan is `plans/domain-policy.json`; its per-app reasons, target groups,
counts, page packing and home positions are saved in `reviews/domain-policy-audit.json`.
Source plans, cloud reviews and backups are not overwritten. Every renamed/moved
folder and changed app position is visible in preview.

On the development phone, 248 apps were individually reviewed into 18 groups,
including the unchanged dock. The private policy records all choices; no personal
dump or complete inventory is committed. Niche identities were checked using
primary product pages and public App Store lookup. Important examples include
Werkspot home services, MyPup parcel collection, Muse AI and SynFit/训记 fitness.

## Verification

Synthetic fixtures cover full first pages, region overrides, banking/bills
adjacency, all-emoji names, complete coverage, protected content, metadata whitelists,
default-mode rejection, saved-plan validation, XML preparation and fixture apply.
Real USB preflight validates the current snapshot and backup. Writing still needs
confirmation of the concrete new preview.
