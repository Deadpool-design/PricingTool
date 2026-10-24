# Apex Orders: Fusion 360 add-in

Double-click **Apex Orders** in `C:\Users\Mina\Desktop\Apex Prints`. Fusion starts (or comes to the front if it is
already open) and the Apex Orders panel opens on the right. The same panel is also on the Design > **Solid** tab:
**Apex Prints > Apex Orders**.

**New order**: choose **Oscar Award** or **Baby Birth Letter** and fill in the form.
- **Oscar Award** runs **Script A only** from the **award-text** skill: the 50 x 34 mm plaque, no base (the base is
  printed to stock; Script B is not in the app). Tick **Show on the base** to mount the plaque on a preview copy of
  the base for the customer screenshot; that copy is never exported. It saves two separate
  STLs, **PLAQUE** and **TEXT**, so Bambu Studio can give them different colours; the review screen has an
  **Open both in Bambu Studio** button. Type 1-3 lines;
  the **last line is the winner's name** and prints biggest. A live preview shows the plaque with the estimated name
  size (amber when the name switches to the lighter font, red when the build would refuse letters under 4 mm).
  Arabic and other right-to-left text is blocked, because Fusion reverses it; use the skill's manual Inkscape route.
- **Baby Birth Letter** (birth-letter skill) takes the name, time, date, weight, height, colour and animal. It spells
  the date out ("1 December 2021") so day and month can't get swapped. Use **Layout overrides** to move or resize
  inserts. The spots and sizes are read from your own `birth_letter.py`, so the form always matches the script.
- **Add to queue** saves the order. **Build now** saves it and builds it straight away.

**Queue**: lists every order: *To build*, *To review*, *Approved*.
- **Build** / **Build all**. Each build runs in a new document (your open designs are never changed), exports the STLs
  and takes review screenshots (top + iso of the plaque for the award; three-quarter, front and back for the letter).
  "Close each document after building" keeps a big batch from leaving 20 tabs open.
- **Review** shows the screenshots, every WARNING line and the order details, plus a checklist. **Approve** stays
  disabled until every box is ticked.
- **Approving an Oscar order** creates `C:\Users\Mina\Desktop\Apex Prints\Products\Sutherland\Oscar\<job name>\`
  with the PLAQUE and TEXT STLs (same wording again gets `<job name> (2)`), then deletes Script A's working copy in
  `Downloads\Apex Prints - Oscar\Plaque Jobs` (only that folder is ever touched; a file open in another program is
  left and you get a note). Rebuilding an approved order and approving again overwrites the same folder. After that, **Open STL folder** and
  **Open both in Bambu Studio** use that folder. The folder can be changed in Settings.
- When you approve a birth letter with layout overrides, the overrides are **saved for that letter**. The next
  letter-I order uses them automatically.

## Install (one time)
1. Copy this whole **Apex Orders** folder to `C:\Users\Mina\Desktop\Apex Prints\Apex Orders`.
2. Double-click **Install Apex Orders.cmd** inside it. It does two things:
   - links the add-in into Fusion's add-ins folder, so Fusion loads it on every start;
   - puts the **Apex Orders** shortcut, with the Apex icon, in `C:\Users\Mina\Desktop\Apex Prints`.
3. If Fusion was open, restart it once.
4. If you added ApexJobs earlier with Shift+S and the green **+**, remove that old entry so it doesn't load twice.

To update later: replace the files in the Apex Orders folder and run the installer again.

## Shopify later
Every order is a JSON file in the orders folder (default `Documents\Apex Orders`). The form is just one way of
writing them. A Shopify agent only has to write the same files with `"source": "shopify"`. See
[ApexJobs/ORDER_FORMAT.md](ApexJobs/ORDER_FORMAT.md).

## Files
- `Install Apex Orders.cmd` + `tools/install.ps1`: one-time setup (add-in link + desktop shortcut).
- `tools/open-apex-orders.ps1`: what the shortcut runs: start or focus Fusion, then open the panel.
- `ApexJobs/ApexJobs.py`: the Fusion side: toolbar button, panel, build queue, screenshots.
- `ApexJobs/orders.py`: order validation and storage (no Fusion code, so a Shopify agent can reuse it).
- `ApexJobs/award_text.py`: Script A from the **award-text** skill. When the skill's Script A changes, copy it in
  again (keep the `build(overrides)` line at the top of the function).
- `ApexJobs/palette/`: the panel UI (HTML/CSS/JS).
- The birth letter runs your existing `birth_letter.py` (+ `svgpoly.py`, `pylib\`). Its path is in Settings.
