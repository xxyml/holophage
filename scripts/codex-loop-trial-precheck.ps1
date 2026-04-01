[CmdletBinding()]
param(
    [string]$TaskId = ""
)

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    python integrations/codex_loop/cli.py materialize-policy
    if ($TaskId) {
        python integrations/codex_loop/cli.py trial-precheck --task-id $TaskId
    }
    else {
        python integrations/codex_loop/cli.py trial-precheck
    }
}
finally {
    Pop-Location
}
