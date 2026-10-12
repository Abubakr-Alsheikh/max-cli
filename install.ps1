# Install Max (max-cli) on Windows in one step.
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/Abubakr-Alsheikh/max-cli/main/install.ps1 | iex"
#
# It installs uv (a small installer for Python programs that brings its own
# Python) when it's missing, then Max with uv, puts both on your PATH, and
# checks that `max` answers. Run it again any time to update Max.

# A script block keeps these settings out of the window that ran irm | iex.
& {
    $ErrorActionPreference = 'Stop'

    function Say($text, $colour = 'Cyan') { Write-Host $text -ForegroundColor $colour }

    Say 'Installing Max...'

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Say 'Getting uv first (it installs Python for Max, too)...'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        # uv puts itself in ~\.local\bin; this window learns about it now, new
        # windows from the PATH change uv made.
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
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
