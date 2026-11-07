$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    python -m venv .venv
}

& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install application requirements." }

& $VenvPython -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Tests failed; the executable was not built." }

& $VenvPython -m PyInstaller --noconfirm --clean --distpath (Join-Path $ProjectRoot "dist") --workpath (Join-Path $ProjectRoot "build") MediaDownloader.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$DistributionDirectory = Join-Path $ProjectRoot "dist\MediaDownloader"
$Executable = Join-Path $DistributionDirectory "MediaDownloader.exe"
if (-not (Test-Path $Executable)) { throw "Build finished without creating MediaDownloader.exe." }
$PackagedReadme = Join-Path $DistributionDirectory "README.md"
Copy-Item -LiteralPath (Join-Path $ProjectRoot "README.md") -Destination $PackagedReadme -Force
$LegacyExecutable = Join-Path $ProjectRoot "dist\MediaDownloader.exe"
if (Test-Path $LegacyExecutable) { Remove-Item -LiteralPath $LegacyExecutable -Force }
Write-Host "Build succeeded: $Executable"

$DistributionArchive = Join-Path $ProjectRoot "MediaDownloader-Windows.zip"
if (Test-Path $DistributionArchive) { Remove-Item -LiteralPath $DistributionArchive -Force }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::Open(
    $DistributionArchive,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $Archive,
        $Executable,
        "MediaDownloader.exe",
        [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null

    $InternalDirectory = Join-Path $DistributionDirectory "_internal"
    Get-ChildItem -LiteralPath $InternalDirectory -File -Recurse |
        Sort-Object FullName |
        ForEach-Object {
            $RelativePath = $_.FullName.Substring($InternalDirectory.Length + 1).Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $Archive,
                $_.FullName,
                "_internal/$RelativePath",
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $Archive,
        $PackagedReadme,
        "README.md",
        [System.IO.Compression.CompressionLevel]::Optimal
    ) | Out-Null
}
finally {
    $Archive.Dispose()
}
if (-not (Test-Path $DistributionArchive)) { throw "Build finished without creating MediaDownloader-Windows.zip." }
Write-Host "Distribution archive created: $DistributionArchive"

# --- Windows installer (Inno Setup 6) ---
$IsccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
)
$Iscc = $IsccCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Iscc) {
    Write-Warning "Inno Setup 6 was not found, so Setup.exe was not created. Install it from https://jrsoftware.org/isdl.php (or: winget install JRSoftware.InnoSetup) and run .\build.ps1 again."
}
else {
    & $Iscc (Join-Path $ProjectRoot "installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
    $Setup = Join-Path $ProjectRoot "installer_output\MediaDownloader-Setup.exe"
    if (-not (Test-Path $Setup)) { throw "Installer build finished without creating MediaDownloader-Setup.exe." }
    Write-Host "Installer created: $Setup"
}
