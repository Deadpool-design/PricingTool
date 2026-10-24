# Apex Orders - what the desktop shortcut runs.
# Starts Fusion if it is not running, brings it to the front if it is, and asks the
# Apex Jobs add-in to open its panel (the add-in watches for open-panel.flag).

$ErrorActionPreference = 'Stop'
$root  = Split-Path $PSScriptRoot -Parent
$addin = Join-Path $root 'ApexJobs'
New-Item -ItemType File -Force -Path (Join-Path $addin 'open-panel.flag') | Out-Null

$fusion = Get-Process -Name 'Fusion360' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($fusion) {
    (New-Object -ComObject WScript.Shell).AppActivate($fusion.Id) | Out-Null
    exit 0
}

# Fusion installs per user under webdeploy\production\<build id>\ - take the newest launcher.
$exe = Get-ChildItem "$env:LOCALAPPDATA\Autodesk\webdeploy\production\*\FusionLauncher.exe", `
                     "$env:LOCALAPPDATA\Autodesk\webdeploy\production\*\Fusion360.exe" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $exe) {
    # Fall back to the Start menu shortcut
    $exe = Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs", `
                         "$env:ProgramData\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter '*Fusion*.lnk' -ErrorAction SilentlyContinue |
           Select-Object -First 1
}
if ($exe) {
    Start-Process -FilePath $exe.FullName
} else {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('Could not find Autodesk Fusion on this PC. Open Fusion yourself, then click Apex Orders on the Solid tab.', 'Apex Orders') | Out-Null
}
