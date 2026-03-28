$ErrorActionPreference = "Stop"

$target = "D:\data\ai4s\holophage\models\prot_t5_xl_uniref50_git"

if (Test-Path $target) {
    Remove-Item -Recurse -Force $target
}

$env:GIT_LFS_SKIP_SMUDGE = "1"
git clone https://hf-mirror.com/Rostlab/prot_t5_xl_uniref50 $target

Set-Location $target
git lfs pull --include "pytorch_model.bin"

Write-Output "DOWNLOADED_TO $target"
