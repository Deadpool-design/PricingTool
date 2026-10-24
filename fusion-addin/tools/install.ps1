# Apex Orders - one-time setup. Run it through "Install Apex Orders.cmd".
#  1. Registers the ApexJobs add-in with Fusion (a folder link, so this folder stays the only copy).
#  2. Puts an "Apex Orders" shortcut with the Apex icon in Desktop\Apex Prints.
# Safe to run again after updating the files.

$ErrorActionPreference = 'Stop'
$root  = Split-Path $PSScriptRoot -Parent
$addin = Join-Path $root 'ApexJobs'
if (-not (Test-Path (Join-Path $addin 'ApexJobs.py'))) { throw "ApexJobs folder not found next to this installer: $addin" }

# Files downloaded from GitHub are marked as "from the internet"; clear that so nothing gets blocked.
Get-ChildItem $root -Recurse -File | Unblock-File

# --- 1. add-in link in Fusion's add-ins folder (Fusion loads it on every start)
$addins = Join-Path $env:APPDATA 'Autodesk\Autodesk Fusion 360\API\AddIns'
New-Item -ItemType Directory -Force -Path $addins | Out-Null
$link = Join-Path $addins 'ApexJobs'
if (Test-Path $link) {
    $item = Get-Item $link -Force
    if ($item.LinkType) {
        cmd /c rmdir "$link" | Out-Null          # removes only the old link, never the files it points to
    } else {
        throw "A separate ApexJobs folder already exists in $addins. Move it somewhere else, then run this again."
    }
}
cmd /c mklink /J "$link" "$addin" | Out-Null
Write-Host "Add-in linked:  $link -> $addin"

# --- 2. shortcut in Desktop\Apex Prints
$dest = Join-Path $env:USERPROFILE 'Desktop\Apex Prints'
if (-not (Test-Path $dest)) { $dest = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Apex Prints' }   # OneDrive desktop
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$lnkPath = Join-Path $dest 'Apex Orders.lnk'
$sc = (New-Object -ComObject WScript.Shell).CreateShortcut($lnkPath)
$sc.TargetPath       = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$sc.Arguments        = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $PSScriptRoot 'open-apex-orders.ps1') + '"'
$sc.IconLocation     = (Join-Path $addin 'resources\apex.ico') + ',0'
$sc.WorkingDirectory = $root
$sc.Description      = 'Open Apex Orders (Oscar Award + Baby Birth Letter) in Fusion'
$sc.WindowStyle      = 7   # minimised
$sc.Save()
Write-Host "Shortcut made:  $lnkPath"
Write-Host ''
Write-Host 'Done. If Fusion is open, restart it once so it loads the add-in.'
Write-Host 'If you added ApexJobs before with Shift+S and the green +, remove that old entry so it does not load twice.'
