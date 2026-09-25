#Requires -Version 5.1
<#
.SYNOPSIS
Installs photographs by Yuval Kolodkin-Gal into your Pictures folder.
.EXAMPLE
.\install.ps1 -Theme canopy -Resolution master -DryRun
.EXAMPLE
.\install.ps1 -Destination 'D:\Wallpapers'
#>
[CmdletBinding()]
param(
    [string]$Destination,
    [ValidateSet('all', 'canopy', 'lagoon', 'ember', 'dusk')]
    [string]$Theme = 'all',
    [ValidateSet('1920x1080', 'master')]
    [string]$Resolution = '1920x1080',
    [switch]$DryRun,
    [switch]$Help
)

if ($Help) {
    Write-Output @'
Yuval Wallpapers - photography by Yuval Kolodkin-Gal

Usage: .\install.ps1 [-Theme all|canopy|lagoon|ember|dusk]
                     [-Resolution 1920x1080|master]
                     [-Destination PATH] [-DryRun] [-Help]

Installs to Pictures\Yuval Wallpapers by default. The selected photographs go
in a 1920x1080 or master subfolder. Master images retain their exported size,
up to 3840x2160. Downloads a pinned repository snapshot into a temporary folder.
DryRun downloads and checks files without writing to the destination.
Identical existing files are kept; differing files are never overwritten.
No administrator rights, Git, or Python are needed. Desktop settings are unchanged.
Choose an installed image in Windows Settings > Personalization > Background.
Hyprland themes are available through install.sh on Linux.
'@
    return
}

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Theme = $Theme.ToLowerInvariant()
$Resolution = $Resolution.ToLowerInvariant()

# Pin payload changes separately from the installer commit.
$SourceRef = '97a73e0e951978f637b627f6ff086b29d1946d30'
$ArchiveUrl = "https://codeload.github.com/yuvalkolodkingal/Wallpapers/zip/$SourceRef"
$ArchiveRoot = "Wallpapers-$SourceRef/"
$TemporaryRoot = $null
$Archive = $null
$PreviousSecurityProtocol = [Net.ServicePointManager]::SecurityProtocol

function Assert-RelativePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Contains('\') -or
        $Path.Contains(':') -or $Path.StartsWith('/') -or
        $Path -match '[\x00-\x1f]' -or $Path -match '(^|/)\.\.?(/|$)') {
        throw "Unsafe archive path: $Path"
    }
}

function Get-ContainedPath {
    param([string]$Root, [string]$RelativePath)
    Assert-RelativePath $RelativePath
    $RootFull = [IO.Path]::GetFullPath($Root).TrimEnd(
        [IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    $Full = [IO.Path]::GetFullPath([IO.Path]::Combine($RootFull, $RelativePath))
    if (-not $Full.StartsWith($RootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path leaves its installation folder: $RelativePath"
    }
    return $Full
}

function Expand-SelectedFile {
    param([string]$RelativePath)
    $EntryName = $ArchiveRoot + $RelativePath
    if (-not $Entries.ContainsKey($EntryName)) {
        throw "Snapshot is missing $RelativePath"
    }
    $Entry = $Entries[$EntryName]
    # Only regular files may become wallpapers or metadata. Repository theme
    # symlinks are deliberately not extracted by this Windows installer.
    $UnixKind = ($Entry.ExternalAttributes -shr 16) -band 61440
    if ($Entry.FullName.EndsWith('/') -or $UnixKind -eq 40960 -or
        ($UnixKind -ne 0 -and $UnixKind -ne 32768)) {
        throw "Expected a regular file in the snapshot: $RelativePath"
    }
    $OutputPath = Get-ContainedPath $ExtractRoot $RelativePath
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($OutputPath))
    $InputStream = $Entry.Open()
    try {
        $OutputStream = [IO.File]::Open($OutputPath, [IO.FileMode]::CreateNew)
        try { $InputStream.CopyTo($OutputStream) }
        finally { $OutputStream.Dispose() }
    }
    finally { $InputStream.Dispose() }
    return $OutputPath
}

function Assert-DestinationParents {
    param([string]$Path)
    $Current = [IO.Path]::GetDirectoryName($Path)
    while (-not [string]::IsNullOrEmpty($Current)) {
        if ([IO.File]::Exists($Current)) {
            throw "A file blocks an installation folder: $Current"
        }
        # Refuse links beneath the chosen destination; a redirected Pictures
        # folder itself is supported because Windows commonly redirects it.
        if ([IO.Directory]::Exists($Current) -and
            $Current.Length -gt $Destination.Length -and
            (([IO.File]::GetAttributes($Current) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "A linked folder blocks installation: $Current"
        }
        $Current = [IO.Path]::GetDirectoryName($Current)
    }
}

try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Use install.sh on Linux, macOS, or other Unix systems.'
    }
    if ([string]::IsNullOrWhiteSpace($Destination)) {
        $Pictures = [Environment]::GetFolderPath([Environment+SpecialFolder]::MyPictures)
        if ([string]::IsNullOrWhiteSpace($Pictures)) {
            $UserProfile = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
            if ([string]::IsNullOrWhiteSpace($UserProfile)) {
                throw 'Cannot locate your Pictures folder; supply -Destination PATH.'
            }
            $Pictures = Join-Path $UserProfile 'Pictures'
        }
        $Destination = Join-Path $Pictures 'Yuval Wallpapers'
    }
    $Destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
    $Destination = [IO.Path]::GetFullPath($Destination)
    if ([IO.File]::Exists($Destination)) {
        throw "Destination is an existing file: $Destination"
    }

    $TemporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ('yuval-wallpapers-' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($TemporaryRoot)
    $ArchivePath = Join-Path $TemporaryRoot 'wallpapers.zip'
    $ExtractRoot = Join-Path $TemporaryRoot 'extracted'

    # Windows PowerShell 5.1 can otherwise default to obsolete TLS versions.
    [Net.ServicePointManager]::SecurityProtocol = $PreviousSecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-Host "Downloading Yuval Wallpapers ($($SourceRef.Substring(0, 12)))..."
    Invoke-WebRequest -UseBasicParsing -Uri $ArchiveUrl -OutFile $ArchivePath -TimeoutSec 300
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Archive = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
    $Entries = @{}
    foreach ($Entry in $Archive.Entries) {
        Assert-RelativePath $Entry.FullName
        if (-not $Entry.FullName.StartsWith($ArchiveRoot, [StringComparison]::Ordinal)) {
            throw 'The downloaded ZIP does not match the pinned repository snapshot.'
        }
        if ($Entries.ContainsKey($Entry.FullName)) {
            throw "Duplicate archive entry: $($Entry.FullName)"
        }
        $Entries.Add($Entry.FullName, $Entry)
    }

    $MetadataPath = Expand-SelectedFile 'metadata/collection.json'
    $Collection = Get-Content -LiteralPath $MetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Collection.author -ne 'Yuval Kolodkin-Gal') {
        throw 'The collection has unexpected photographer metadata.'
    }
    $Selected = @($Collection.wallpapers | Where-Object { $Theme -eq 'all' -or $_.theme -eq $Theme })
    if ($Selected.Count -eq 0) { throw "No wallpapers found for theme: $Theme" }

    $Files = @()
    $Targets = @{}
    foreach ($Wallpaper in $Selected) {
        if ($Wallpaper.slug -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$' -or
            $Wallpaper.photographer -ne 'Yuval Kolodkin-Gal') {
            throw 'Invalid wallpaper metadata in the snapshot.'
        }
        $RelativeSource = [string]$Wallpaper.fullhd
        if ($Resolution -eq 'master') { $RelativeSource = [string]$Wallpaper.master }
        $ExpectedSource = "wallpapers/$Resolution/$($Wallpaper.slug).jpg"
        if ($RelativeSource -cne $ExpectedSource) {
            throw "Unexpected wallpaper path: $RelativeSource"
        }
        $RelativeTarget = "$Resolution/$($Wallpaper.slug).jpg"
        if ($Targets.ContainsKey($RelativeTarget)) { throw "Duplicate wallpaper: $RelativeTarget" }
        $Targets.Add($RelativeTarget, $true)
        $Source = Expand-SelectedFile $RelativeSource
        if ($Resolution -eq 'master' -and
            (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne $Wallpaper.sha256) {
            throw "Wallpaper checksum mismatch: $($Wallpaper.slug)"
        }
        $Files += [PSCustomObject]@{ Source = $Source; Target = (Get-ContainedPath $Destination $RelativeTarget) }
    }
    $CopyrightSource = Expand-SelectedFile 'COPYRIGHT'
    $Files += [PSCustomObject]@{ Source = $CopyrightSource; Target = (Get-ContainedPath $Destination 'COPYRIGHT') }
    $Instructions = @'
Yuval Wallpapers
Photography by Yuval Kolodkin-Gal (@yuvalkolodkingal).
https://github.com/yuvalkolodkingal/Wallpapers

Choose a photograph in Settings > Personalization > Background > Browse photos.
For a slideshow, choose Slideshow and select the 1920x1080 or master subfolder.
The installer does not change your desktop settings.

Run install.ps1 -Help to see theme, resolution, and destination options.
Hyprland themes are available through install.sh on Linux.
See COPYRIGHT for the photography credit and reuse terms.
'@
    $InstructionsPath = Join-Path $TemporaryRoot 'INSTALLATION.txt'
    [IO.File]::WriteAllText($InstructionsPath, ($Instructions -replace '\r?\n', "`r`n") + "`r`n", [Text.UTF8Encoding]::new($false))
    $Files += [PSCustomObject]@{ Source = $InstructionsPath; Target = (Get-ContainedPath $Destination 'INSTALLATION.txt') }

    # Check every destination before creating folders or copying any files.
    $Pending = @()
    foreach ($File in $Files) {
        Assert-DestinationParents $File.Target
        if (Test-Path -LiteralPath $File.Target) {
            $Item = Get-Item -LiteralPath $File.Target -Force
            if ($Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Existing path is not a regular file: $($File.Target)"
            }
            if ((Get-FileHash -LiteralPath $File.Source -Algorithm SHA256).Hash -ne
                (Get-FileHash -LiteralPath $File.Target -Algorithm SHA256).Hash) {
                throw "Existing file differs; move it aside before retrying: $($File.Target)"
            }
        }
        else { $Pending += $File }
    }
    Write-Host "Selected $($Selected.Count) $Resolution wallpapers ($Theme)."
    Write-Host "Destination: $Destination"
    if ($DryRun) {
        Write-Host "Dry run: $($Pending.Count) files would be added. No destination files were written."
    }
    else {
        foreach ($File in $Pending) {
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($File.Target))
            [IO.File]::Copy($File.Source, $File.Target, $false)
        }
        Write-Host "Installed; $($Pending.Count) files added. Photography by Yuval Kolodkin-Gal."
        Write-Host 'Choose an image in Settings > Personalization > Background.'
    }
}
finally {
    if ($null -ne $Archive) { $Archive.Dispose() }
    [Net.ServicePointManager]::SecurityProtocol = $PreviousSecurityProtocol
    if ($null -ne $TemporaryRoot -and [IO.Directory]::Exists($TemporaryRoot)) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}
