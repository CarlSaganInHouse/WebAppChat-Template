# World Model (Hybrid)

- Exported: 2026-01-13 05:16 UTC
- Canonical source of truth: the JSON block below.
- Human notes: Keep edits primarily in the JSON block; regenerate derived sections as needed.

---

## Operating Principles (Human-facing)
- Tasks/reminders: Microsoft To Do is source of truth.
- Obsidian: context, logs, reference, decisions, asset history.
- If uncertain: ask 1 clarifying question OR save to Inbox without filing.
- Prefer append-first edits; avoid large rewrites without explicit request.
- When importing facts, store sources + capture dates.

---

## ENTITY_REGISTRY_JSON (Canonical — do not hand-edit unless you know what you’re doing)
```json
{
  "version": 1,
  "exported": "2026-01-13 05:16 UTC",
  "systems": {
    "tasks_source_of_truth": "microsoft_todo",
    "notes": "Obsidian holds context/logs/reference/decisions; tasks live in Microsoft To Do."
  },
  "user": {
    "canonical": "Aaron Abel",
    "aliases": [
      "Aaron"
    ],
    "preferences": {
      "tone": "concise",
      "avoid_early_meetings": true,
      "nudges_help": true
    }
  },
  "vocabulary": [
    {
      "id": "term:commune",
      "term": "The Commune",
      "aliases": [
        "the commune",
        "commune"
      ],
      "meaning": "Shared-property coordination with neighbors (semi-joking term)."
    },
    {
      "id": "term:main_house",
      "term": "Main House",
      "aliases": [
        "main house",
        "the main house"
      ],
      "meaning": "Kathleen's house; pool/pool house/sauna/hot tub nearby."
    },
    {
      "id": "term:shop",
      "term": "The Shop",
      "aliases": [
        "the shop",
        "shop"
      ],
      "meaning": "40x40 metal pole barn; tractor/mowers/woodworking tools; near garden."
    },
    {
      "id": "term:buddys_barn",
      "term": "Buddy's Barn",
      "aliases": [
        "buddy's barn",
        "buddys barn"
      ],
      "meaning": "Barn location associated with Buddy (pig), near Main House area."
    },
    {
      "id": "term:honks",
      "term": "The Honks",
      "aliases": [
        "the honks",
        "honks"
      ],
      "refers_to": [
        "animal:doug",
        "animal:patches"
      ]
    }
  ],
  "entities": [
    {
      "id": "person:aaron",
      "type": "person",
      "canonical": "Aaron Abel",
      "aliases": [
        "Aaron"
      ],
      "relationship": "self"
    },
    {
      "id": "person:taylor",
      "type": "person",
      "canonical": "Taylor Kearschner",
      "aliases": [
        "Taylor"
      ],
      "relationship": "wife"
    },
    {
      "id": "person:kathleen",
      "type": "person",
      "canonical": "Kathleen Ross",
      "aliases": [
        "Kathleen"
      ],
      "relationship": "aunt"
    },
    {
      "id": "person:logan",
      "type": "person",
      "canonical": "Logan Cunningham",
      "aliases": [
        "Logan"
      ],
      "relationship": "neighbor/friend"
    },
    {
      "id": "person:lindsey",
      "type": "person",
      "canonical": "Lindsey Cunningham",
      "aliases": [
        "Lindsey"
      ],
      "relationship": "neighbor/friend"
    },
    {
      "id": "person:david",
      "type": "person",
      "canonical": "David Abel",
      "aliases": [
        "David"
      ],
      "relationship": "father"
    },
    {
      "id": "person:elliot",
      "type": "person",
      "canonical": "Elliot Abel",
      "aliases": [
        "Elliot"
      ],
      "relationship": "brother"
    },
    {
      "id": "person:brandon",
      "type": "person",
      "canonical": "Brandon Abel",
      "aliases": [
        "Brandon"
      ],
      "relationship": "brother"
    },
    {
      "id": "animal:dezzie",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Desdemona",
      "aliases": [
        "Dezzie"
      ],
      "species": "dog",
      "breed": "Rat Terrier"
    },
    {
      "id": "animal:diva",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Goddiva",
      "aliases": [
        "Diva"
      ],
      "species": "dog",
      "breed": "Pomeranian"
    },
    {
      "id": "animal:button",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Button",
      "aliases": [],
      "species": "cat",
      "notes": "Outdoor cat"
    },
    {
      "id": "animal:simba",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Simba",
      "aliases": [],
      "species": "cat",
      "notes": "Outdoor cat"
    },
    {
      "id": "animal:tiger",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Tiger",
      "aliases": [],
      "species": "cat",
      "notes": "Outdoor cat"
    },
    {
      "id": "animal:zazu",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Zazu",
      "aliases": [],
      "species": "cat",
      "notes": "Outdoor cat"
    },
    {
      "id": "animal:kiara",
      "type": "asset",
      "subtype": "pet",
      "canonical": "Kiara",
      "aliases": [],
      "species": "cat",
      "notes": "Outdoor cat"
    },
    {
      "id": "animal:doug",
      "type": "asset",
      "subtype": "livestock",
      "canonical": "Doug",
      "aliases": [],
      "species": "horse"
    },
    {
      "id": "animal:patches",
      "type": "asset",
      "subtype": "livestock",
      "canonical": "Patches",
      "aliases": [],
      "species": "mini donkey"
    },
    {
      "id": "animal:buddy",
      "type": "asset",
      "subtype": "livestock",
      "canonical": "Buddy",
      "aliases": [],
      "species": "pig"
    },
    {
      "id": "asset:pilot",
      "type": "asset",
      "subtype": "vehicle",
      "canonical": "Honda Pilot",
      "aliases": [
        "Pilot"
      ],
      "year": 2019
    },
    {
      "id": "asset:f150",
      "type": "asset",
      "subtype": "vehicle",
      "canonical": "Ford F-150",
      "aliases": [
        "F150",
        "truck"
      ],
      "year": 2001
    },
    {
      "id": "asset:mahindra_tractor",
      "type": "asset",
      "subtype": "machine",
      "canonical": "Mahindra Tractor",
      "aliases": [
        "Mahindra",
        "tractor"
      ],
      "notes": "~50 hp"
    },
    {
      "id": "asset:mower_gravely",
      "type": "asset",
      "subtype": "machine",
      "canonical": "Gravely lawnmower",
      "aliases": [
        "Gravely"
      ]
    },
    {
      "id": "asset:mower_ferris",
      "type": "asset",
      "subtype": "machine",
      "canonical": "Ferris lawnmower",
      "aliases": [
        "Ferris"
      ]
    },
    {
      "id": "asset:atv_grizzly",
      "type": "asset",
      "subtype": "vehicle",
      "canonical": "Yamaha Grizzly",
      "aliases": [
        "Grizzly"
      ],
      "notes": "3x ATVs"
    },
    {
      "id": "asset:utv_viking",
      "type": "asset",
      "subtype": "vehicle",
      "canonical": "Yamaha Viking",
      "aliases": [
        "Viking"
      ]
    },
    {
      "id": "asset:rv_class_c",
      "type": "asset",
      "subtype": "vehicle",
      "canonical": "Class C RV",
      "aliases": [
        "RV"
      ]
    },
    {
      "id": "asset:splitter",
      "type": "asset",
      "subtype": "machine",
      "canonical": "Hydraulic wood splitter",
      "aliases": [
        "splitter"
      ]
    },
    {
      "id": "asset:trailer_flatbed",
      "type": "asset",
      "subtype": "trailer",
      "canonical": "17ft flatbed trailer",
      "aliases": [
        "trailer"
      ]
    },
    {
      "id": "asset:brushhog",
      "type": "asset",
      "subtype": "implement",
      "canonical": "Brush hog",
      "aliases": [
        "brushhog",
        "brush hog"
      ]
    },
    {
      "id": "location:home",
      "type": "location",
      "canonical": "Home",
      "aliases": [
        "home"
      ],
      "notes": "Aaron & Taylor's house"
    },
    {
      "id": "location:main_house",
      "type": "location",
      "canonical": "Main House",
      "aliases": [
        "main house",
        "the main house"
      ],
      "notes": "Kathleen's house; pool/pool house/sauna/hot tub nearby"
    },
    {
      "id": "location:shop",
      "type": "location",
      "canonical": "The Shop",
      "aliases": [
        "shop",
        "the shop"
      ],
      "notes": "40x40 pole barn; tools + tractor + mowers; near garden"
    },
    {
      "id": "location:garden",
      "type": "location",
      "canonical": "Garden",
      "aliases": [
        "garden"
      ],
      "notes": "Large raised-bed garden near The Shop"
    },
    {
      "id": "location:orchard",
      "type": "location",
      "canonical": "Orchard",
      "aliases": [
        "orchard"
      ],
      "notes": "Fruit trees established ~2 years ago"
    },
    {
      "id": "location:buddys_barn",
      "type": "location",
      "canonical": "Buddy's Barn",
      "aliases": [
        "buddy's barn",
        "buddys barn"
      ],
      "notes": "Near Main House area"
    }
  ],
  "routing": {
    "folders": {
      "inbox_new": "00_INBOX/new",
      "daily": "01_DAILY",
      "projects": "10_PROJECTS",
      "areas": "20_AREAS",
      "reference": "30_REFERENCE",
      "people": "40_PEOPLE",
      "assets": "50_ASSETS",
      "meta": "90_META",
      "archive": "99_ARCHIVE"
    },
    "capture_types": [
      "task",
      "log",
      "reference",
      "inventory",
      "decision",
      "question"
    ],
    "default_time_for_tomorrow_morning": "09:00"
  }
}
```

---

## Generated Index (Convenience)
# World Model (Generated View)

- Generated: 2026-01-13 05:16 UTC
- Source: `WorldModel.json`
- Notes: Edit the JSON as the canonical source; this file can be regenerated.

---

## Systems
- Tasks source of truth: **microsoft_todo**
- Obsidian usage: Obsidian holds context/logs/reference/decisions; tasks live in Microsoft To Do.

## Vocabulary & Aliases
- **The Commune** — aliases: the commune, commune — Shared-property coordination with neighbors (semi-joking term).
- **Main House** — aliases: main house, the main house — Kathleen's house; pool/pool house/sauna/hot tub nearby.
- **The Shop** — aliases: the shop, shop — 40x40 metal pole barn; tractor/mowers/woodworking tools; near garden.
- **Buddy's Barn** — aliases: buddy's barn, buddys barn — Barn location associated with Buddy (pig), near Main House area.
- **The Honks** — aliases: the honks, honks — refers_to: animal:doug, animal:patches

## People
- **Aaron Abel** (`person:aaron`) — aliases: Aaron — self
- **Taylor Kearschner** (`person:taylor`) — aliases: Taylor — wife
- **Kathleen Ross** (`person:kathleen`) — aliases: Kathleen — aunt
- **Logan Cunningham** (`person:logan`) — aliases: Logan — neighbor/friend
- **Lindsey Cunningham** (`person:lindsey`) — aliases: Lindsey — neighbor/friend
- **David Abel** (`person:david`) — aliases: David — father
- **Elliot Abel** (`person:elliot`) — aliases: Elliot — brother
- **Brandon Abel** (`person:brandon`) — aliases: Brandon — brother

## Animals
- **Desdemona** (`animal:dezzie`) — aliases: Dezzie — dog; Rat Terrier
- **Goddiva** (`animal:diva`) — aliases: Diva — dog; Pomeranian
- **Button** (`animal:button`) — aliases: — — cat; Outdoor cat
- **Simba** (`animal:simba`) — aliases: — — cat; Outdoor cat
- **Tiger** (`animal:tiger`) — aliases: — — cat; Outdoor cat
- **Zazu** (`animal:zazu`) — aliases: — — cat; Outdoor cat
- **Kiara** (`animal:kiara`) — aliases: — — cat; Outdoor cat
- **Doug** (`animal:doug`) — aliases: — — horse
- **Patches** (`animal:patches`) — aliases: — — mini donkey
- **Buddy** (`animal:buddy`) — aliases: — — pig

## Key Assets
- **Honda Pilot** (`asset:pilot`) — subtype: vehicle — aliases: Pilot — year 2019
- **Ford F-150** (`asset:f150`) — subtype: vehicle — aliases: F150, truck — year 2001
- **Mahindra Tractor** (`asset:mahindra_tractor`) — subtype: machine — aliases: Mahindra, tractor — ~50 hp
- **Gravely lawnmower** (`asset:mower_gravely`) — subtype: machine — aliases: Gravely
- **Ferris lawnmower** (`asset:mower_ferris`) — subtype: machine — aliases: Ferris
- **Yamaha Grizzly** (`asset:atv_grizzly`) — subtype: vehicle — aliases: Grizzly — 3x ATVs
- **Yamaha Viking** (`asset:utv_viking`) — subtype: vehicle — aliases: Viking
- **Class C RV** (`asset:rv_class_c`) — subtype: vehicle — aliases: RV
- **Hydraulic wood splitter** (`asset:splitter`) — subtype: machine — aliases: splitter
- **17ft flatbed trailer** (`asset:trailer_flatbed`) — subtype: trailer — aliases: trailer
- **Brush hog** (`asset:brushhog`) — subtype: implement — aliases: brushhog, brush hog

## Locations
- **Home** (`location:home`) — aliases: home — Aaron & Taylor's house
- **Main House** (`location:main_house`) — aliases: main house, the main house — Kathleen's house; pool/pool house/sauna/hot tub nearby
- **The Shop** (`location:shop`) — aliases: shop, the shop — 40x40 pole barn; tools + tractor + mowers; near garden
- **Garden** (`location:garden`) — aliases: garden — Large raised-bed garden near The Shop
- **Orchard** (`location:orchard`) — aliases: orchard — Fruit trees established ~2 years ago
- **Buddy's Barn** (`location:buddys_barn`) — aliases: buddy's barn, buddys barn — Near Main House area

## Routing (folders)
- `inbox_new` → `00_INBOX/new`
- `daily` → `01_DAILY`
- `projects` → `10_PROJECTS`
- `areas` → `20_AREAS`
- `reference` → `30_REFERENCE`
- `people` → `40_PEOPLE`
- `assets` → `50_ASSETS`
- `meta` → `90_META`
- `archive` → `99_ARCHIVE`

- Default time for “tomorrow morning”: `09:00`

