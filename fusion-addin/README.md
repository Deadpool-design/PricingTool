# Apex Orders: Fusion 360 add-in

An **Apex Orders** button on Fusion's Design > **Solid** tab opens a panel docked on the right side of Fusion.

**New order**: choose **Oscar Award** or **Baby Birth Letter** and fill in the form.
- Oscar Award shows a live preview of the gold band with your text and the estimated letter height
  (amber when it's borderline, red when the build would refuse it). It also counts characters per line.
- Baby Birth Letter takes the name, time, date, weight, height, colour and animal. It spells the date out
  ("1 December 2021") so day and month can't get swapped. Use **Layout overrides** to move or resize inserts. The
  spots and sizes are read from your own `birth_letter.py`, so the form always matches the script.
- **Add to queue** saves the order. **Build now** saves it and builds it straight away.

**Queue**: lists every order: *To build*, *To review*, *Approved*.
- **Build** / **Build all**. Each build runs in a new document (your open designs are never changed), exports the STLs
  and takes review screenshots (top and iso for the arch; three-quarter, front and back for the letter).
  "Close each document after building" keeps a big batch from leaving 20 tabs open.
- **Review** shows the screenshots, every WARNING line and the order details, plus a checklist (name letter by
  letter, logo reads left-to-right, and so on). **Approve** stays disabled until every box is ticked.
- When you approve a birth letter with layout overrides, the overrides are **saved for that letter**. The next letter-I order
  uses them automatically.

## Install (one time)
1. Copy the `ApexJobs` folder somewhere permanent, e.g. `C:\Users\Mina\Desktop\Apex Prints\Add-ins\ApexJobs`.
2. In Fusion: **Utilities > Add-Ins > Scripts and Add-Ins** (Shift+S), open the **Add-Ins** tab, click the green **+** and choose the `ApexJobs` folder.
3. Select **ApexJobs**, click **Run**, and tick **Run on Startup**.
4. Click **Apex Orders** in the **Apex Prints** panel on the Solid tab.

## Shopify later
Every order is a JSON file in the orders folder (default `Documents\Apex Orders`). The form is just one way of
writing them. A Shopify agent only has to write the same files with `"source": "shopify"`. See
[ApexJobs/ORDER_FORMAT.md](ApexJobs/ORDER_FORMAT.md).

## Files
- `ApexJobs.py`: the Fusion side: toolbar button, panel, build queue, screenshots.
- `orders.py`: order validation and storage (no Fusion code, so a Shopify agent can reuse it).
- `arch_award.py`: the arch script from the arch-award-text skill.
- `palette/`: the panel UI (HTML/CSS/JS).
- The birth letter runs your existing `birth_letter.py` (+ `svgpoly.py`, `pylib\`). Its path is in Settings.
