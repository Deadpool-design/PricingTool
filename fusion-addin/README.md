# Apex Jobs: Fusion 360 add-in

Adds an **Apex Prints** panel to Fusion's Design > **Solid** tab with two buttons:

| Button | Asks for | Builds |
|---|---|---|
| **Oscar Award** | 1-3 text lines, optional job name (Advanced: font, thickness, text raise) | Curved arch in a new document. Exports ARCH + TEXT STLs to `Downloads\Apex Arch Jobs\<job>\` |
| **Baby Birth Letter** | Name, time, date, weight, height, animal, colour (Advanced: letter, letter height, min overlap, script path) | Birth-stats letter in a new document. Runs `birth_letter.py` from your Scripts folder and exports its STLs to `Downloads\Apex Birth Letters\...` |

Each build opens a **new** document, so your open designs are never changed. When a build finishes, a box shows every WARNING line, the sizes and grams, and what to check before printing. It can also open the STL folder for you.

## Install (one time)
1. Copy the `ApexJobs` folder somewhere permanent, e.g. `C:\Users\Mina\Desktop\Apex Prints\Add-ins\ApexJobs`.
2. In Fusion: **Utilities > Add-Ins > Scripts and Add-Ins** (Shift+S), open the **Add-Ins** tab, click the green **+**, and choose the `ApexJobs` folder.
3. Select **ApexJobs**, click **Run**, and tick **Run on Startup**.
4. The **Apex Prints** panel appears at the right end of the Solid tab.

## Notes
- **Oscar Award** has the script built in (`arch_award.py`, copied from the arch-award-text skill).
- **Baby Birth Letter** runs your existing `birth_letter.py` (plus `svgpoly.py` and `pylib\`) from
  `C:\Users\Mina\Desktop\Apex Prints\Products\Letters\Scripts`. If you move it, change the path under Advanced. The add-in remembers the new path in `settings.json`.
- The date is spelled out in the dialog ("1 December 2021") so you can catch day/month mix-ups before building.
- If a build fails it leaves an Untitled document open. Close it without saving.
- Nobody checks the screenshots any more. Read the name letter by letter and check the logo on the back yourself.
