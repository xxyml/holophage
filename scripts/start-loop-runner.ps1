[CmdletBinding()]
param(
    [string]$RunnerId = "",
    [int]$MaxRounds = 0
)

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $args = @("integrations/codex_loop/cli.py", "run-autopilot")
    if ($RunnerId) {
        $args += @("--runner-id", $RunnerId)
    }
    if ($MaxRounds -gt 0) {
        $args += @("--max-rounds", $MaxRounds)
    }
    python @args
}
finally {
    Pop-Location
}
