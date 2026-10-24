# Order file format

The Apex Orders panel reads every `*.json` file in the orders folder
(default `Documents\Apex Orders`, changeable in the panel's Settings). The form writes
these files. A future Shopify agent only has to write the same files. The panel needs no changes.

Rules for anything that writes orders:
- One file per item to print, named `<anything-unique>.json`. The file name is the order id.
- Write to a temp name, then rename, so the panel never reads half a file.
- Set `"status": "pending"`. The panel does everything after that (building → review → approved).
- Don't fix customer typos. Copy what the customer typed. The panel validates at build time, and a
  bad order shows up as **Failed** with the reason, for you to edit.

## Oscar Award (plaque, award-text skill)

```json
{
  "type": "award",
  "status": "pending",
  "source": "shopify",
  "ref": { "shopify_order": "#1042", "line_item": "1234567890", "customer": "Sara M." },
  "notes": "Gift wrap",
  "fields": {
    "lines": ["Sep 26 Winners", "Team", "Farah Helmy"],
    "job_name": ""
  }
}
```
1-3 lines, top to bottom. The **last line is the winner's name** and prints biggest. Lines fit 46 mm:
about 14 characters for the small lines, about 11 for the name. Longer lines shrink, and a build that needs
letters under 4 mm is refused. Arabic or other right-to-left text is refused (it needs the manual Inkscape route).
Optional fields: `small_h_mm` (4-6.5, default 5.1), `name_h_mm` (4-8, default 6.45).
Older files with `"type": "arch"` are read as `award`.

## Baby Birth Letter

```json
{
  "type": "birth",
  "status": "pending",
  "source": "shopify",
  "ref": { "shopify_order": "#1043", "customer": "Lina K." },
  "fields": {
    "baby_name": "Antoine",
    "time": "11:10",
    "date": "01.12.2021",
    "weight": "2860",
    "height": "49",
    "animal": "elephant",
    "colour": "blue"
  },
  "overrides": {}
}
```

Accepted input, which is normalised before building:

| Field | Accepts | Refuses |
|---|---|---|
| time | `11:10`, `9.05`, `3:15 pm` (converted to 15:15) | anything else |
| date | `01.12.2021`, `2021-12-01` (ISO, what Shopify date pickers send) | `01/12/2021`, refused on purpose because it could mean 1 Dec or 12 Jan |
| weight | `3415`, `3415 g`, `3.415 kg` (300–7000 g) | lb/oz |
| height | `51`, `51 cm`, `510 mm` (25–70 cm) | inches |
| animal | elephant, lion, unicorn, bunny (or rabbit), rocking_horse (or "rocking horse") | others |
| colour | pink, blue (`color` also accepted) | others |

Optional fields: `letter`, `letter_height_mm` (100–245), `letter_thickness_mm` (10–40), `min_overlap` (0.3–1).

`overrides` is `{"LAYOUT": {"clock": [0.30, 0.85]}, "SIZE": {"clock_r": 0.12}}`, using the keys from
`birth_letter.py`. Leave it empty: if a layout was approved before for the same letter,
the panel uses that automatically.

## What the panel adds

When it builds an order, the panel adds `clean` (the normalised values it built from), `result`
(`output`, `warnings`, `stl_folder`, `screenshots`, or `error`), and `updated`. Screenshots go in a
folder next to the JSON with the same name.
