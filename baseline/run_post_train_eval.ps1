[CmdletBinding()]
param(
    [string]$EnvName = "ai4s",
    [string]$ConfigPath = "baseline/train_config.embed_restart.yaml",
    [string]$RunDir = "baseline/runs/baseline_l1_l2_l3core_embed"
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return (Resolve-Path $PathValue).Path
    }
    return (Resolve-Path (Join-Path $RepoRoot $PathValue)).Path
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedConfigPath = Resolve-RepoPath -PathValue $ConfigPath -RepoRoot $repoRoot
$resolvedRunDir = if ([System.IO.Path]::IsPathRooted($RunDir)) {
    [System.IO.Path]::GetFullPath($RunDir)
}
else {
    [System.IO.Path]::GetFullPath((Join-Path $repoRoot $RunDir))
}

$checkpointPath = Join-Path $resolvedRunDir "checkpoints\\best.pt"
$valLogPath = Join-Path $resolvedRunDir "evaluation_val.log"
$testLogPath = Join-Path $resolvedRunDir "evaluation_test.log"
$evaluationDir = Join-Path $resolvedRunDir "evaluation"

if (-not (Test-Path $checkpointPath)) {
    Write-Error "best checkpoint not found: $checkpointPath`nPlease run training until best.pt is created."
    exit 1
}

Push-Location $repoRoot
try {
    $startAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Set-Content -Path $valLogPath -Value "[$startAt] start val evaluation`n"
    Set-Content -Path $testLogPath -Value "[$startAt] start test evaluation`n"

    & conda run -n $EnvName python -u -m baseline.evaluate --config $resolvedConfigPath --checkpoint $checkpointPath --split val 1>> $valLogPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "val evaluation failed. See log: $valLogPath"
        exit $LASTEXITCODE
    }

    & conda run -n $EnvName python -u -m baseline.evaluate --config $resolvedConfigPath --checkpoint $checkpointPath --split test 1>> $testLogPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "test evaluation failed. See log: $testLogPath"
        exit $LASTEXITCODE
    }

    $endAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $valLogPath -Value "`n[$endAt] val evaluation done"
    Add-Content -Path $testLogPath -Value "`n[$endAt] test evaluation done"

    Write-Host "Post-train evaluation finished. Output summary:"
    Write-Host "  Config        : $resolvedConfigPath"
    Write-Host "  RunDir        : $resolvedRunDir"
    Write-Host "  Checkpoint    : $checkpointPath"
    Write-Host "  Val Log       : $valLogPath"
    Write-Host "  Test Log      : $testLogPath"
    Write-Host "  Eval Dir      : $evaluationDir"
    Write-Host "  Val Metrics   : $(Join-Path $evaluationDir 'metrics_val.json')"
    Write-Host "  Test Metrics  : $(Join-Path $evaluationDir 'metrics_test.json')"
    Write-Host "  Val Pred      : $(Join-Path $evaluationDir 'predictions_val.csv')"
    Write-Host "  Test Pred     : $(Join-Path $evaluationDir 'predictions_test.csv')"
}
finally {
    Pop-Location
}
