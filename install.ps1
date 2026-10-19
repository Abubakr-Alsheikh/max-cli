# Install Max (max-cli) on Windows in one step. The command that runs this
# file is in the README and on https://abubakr-alsheikh.github.io/max-cli/start-here/
# (this file also lives on that site, for networks that block GitHub's raw
# file host).
#
# It installs uv (a small installer for Python programs that brings its own
# Python) when it's missing: with winget, Windows' package manager, when you
# have it, else from uv's official zip on GitHub, checked against the SHA-256
# published beside it. Then Max with uv, both on your PATH, and a check that
# `max` answers. Run it again any time to update Max. It needs no
# administrator rights: everything goes into your user folder.
#
# It never downloads another script and runs it: Windows Defender blocks that
# pattern, which malware uses too. To install with no script at all, run the
# two commands it would:
#
#   winget install --id astral-sh.uv --exact
#   uv tool install max-cli

# A script block keeps these settings out of the window that ran this file.
& {
    $ErrorActionPreference = 'Stop'
    # Invoke-WebRequest's progress bar makes Windows PowerShell 5.1 slow.
    $ProgressPreference = 'SilentlyContinue'
    # Windows PowerShell 5.1 on older Windows offers TLS 1.0 first, which
    # download sites refuse.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    function Say($text, $colour = 'Cyan') { Write-Host $text -ForegroundColor $colour }

    function Find-Uv {
        # A new install isn't on this window's PATH yet: winget's link
        # folder, and ~\.local\bin, where uv's zip goes.
        foreach ($folder in "$env:LOCALAPPDATA\Microsoft\WinGet\Links", "$env:USERPROFILE\.local\bin") {
            if ((Test-Path "$folder\uv.exe") -and (($env:Path -split ';') -notcontains $folder)) {
                $env:Path = "$folder;$env:Path"
            }
        }
        return [bool](Get-Command uv -ErrorAction SilentlyContinue)
    }

    function Install-UvFromZip {
        $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'aarch64' } else { 'x86_64' }
        $name = "uv-$arch-pc-windows-msvc.zip"
        $url = "https://github.com/astral-sh/uv/releases/latest/download/$name"
        $work = Join-Path ([IO.Path]::GetTempPath()) ("max-uv-" + [Guid]::NewGuid())
        New-Item -ItemType Directory -Path $work | Out-Null
        try {
            $zip = Join-Path $work $name
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $zip
            $published = (Invoke-WebRequest -UseBasicParsing -Uri "$url.sha256").Content
            if ($published -is [byte[]]) { $published = [Text.Encoding]::ASCII.GetString($published) }
            $expected = ($published.Trim() -split '\s+')[0].ToLower()
            $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
            if ($actual -ne $expected) { throw "uv's download doesn't match its published checksum." }
            Expand-Archive -Path $zip -DestinationPath (Join-Path $work 'uv')
            $bin = "$env:USERPROFILE\.local\bin"
            New-Item -ItemType Directory -Force -Path $bin | Out-Null
            Get-ChildItem -Path (Join-Path $work 'uv') -Recurse -Include 'uv.exe', 'uvx.exe', 'uvw.exe' |
                Copy-Item -Destination $bin -Force
        }
        finally {
            Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue
        }
    }

    Say 'Installing Max...'

    if (-not (Find-Uv)) {
        Say 'Getting uv first (it installs Python for Max, too)...'
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id astral-sh.uv --exact --accept-source-agreements --accept-package-agreements --disable-interactivity
        }
        if (-not (Find-Uv)) {
            try {
                Install-UvFromZip
            }
            catch {
                Say "Couldn't get uv: $($_.Exception.Message)" 'Red'
                Say 'Check your internet connection, or install it yourself: winget install --id astral-sh.uv --exact' 'Yellow'
                return
            }
        }
        if (-not (Find-Uv)) {
            Say 'uv was installed, but this window cannot find it. Open a new terminal and run this line again.' 'Yellow'
            return
        }
    }

    # --upgrade installs Max, or updates the Max that's there.
    uv tool install --upgrade max-cli
    if ($LASTEXITCODE -ne 0) {
        Say 'uv could not install Max. Check your internet connection and run this line again.' 'Red'
        return
    }

    # Make `max` and uv work in new windows (it changes PATH only when it
    # must), and in this script for the check below.
    uv tool update-shell *> $null
    $bin = (uv tool dir --bin).Trim()
    if (($env:Path -split ';') -notcontains $bin) { $env:Path = "$bin;$env:Path" }

    max --version
    if ($LASTEXITCODE -ne 0) {
        Say 'Max is installed, but did not start. Open a new terminal and type: max doctor' 'Yellow'
        return
    }

    Say ''
    Say 'Max is ready. Open a new terminal window, then:' 'Green'
    Say '  max          opens the dashboard'
    Say '  max doctor   checks your setup (FFmpeg, AI, YouTube)'
}
