# Install Max (max-cli) on Windows in one step.
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/Abubakr-Alsheikh/max-cli/main/install.ps1 | iex"
#
# Same script, for networks that block raw.githubusercontent.com:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://abubakr-alsheikh.github.io/max-cli/install.ps1 | iex"
#
# It installs uv (a small installer for Python programs that brings its own
# Python) when it's missing: with winget, Windows' package manager, when you
# have it, else with uv's own installer. Then Max with uv, both on your PATH,
# and a check that `max` answers. Run it again any time to update Max. It
# needs no administrator rights: everything goes into your user folder.

# A script block keeps these settings out of the window that ran irm | iex.
& {
    $ErrorActionPreference = 'Stop'

    function Say($text, $colour = 'Cyan') { Write-Host $text -ForegroundColor $colour }

    # Windows PowerShell 5.1 on older Windows offers TLS 1.0 first, which
    # download sites refuse.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    Say 'Installing Max...'

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Say 'Getting uv first (it installs Python for Max, too)...'
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id astral-sh.uv --exact --accept-source-agreements --accept-package-agreements --disable-interactivity
        }
        # A new install isn't on this window's PATH yet: winget's link
        # folder, and ~\.local\bin, where uv's own installer puts it.
        $env:Path = "$env:LOCALAPPDATA\Microsoft\WinGet\Links;$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        }
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
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

    # Make `max` work in new windows (it changes PATH only when it must), and in
    # this script for the check below.
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
