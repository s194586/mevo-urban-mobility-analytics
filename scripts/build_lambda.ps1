$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDirectory = Join-Path $ProjectRoot "build\lambda"
$ZipPath = Join-Path $ProjectRoot "dist\mevo-data-collector-lambda.zip"
$Python = if ($env:MEVO_PYTHON) { $env:MEVO_PYTHON } else { "python" }

if (Test-Path -LiteralPath $BuildDirectory) {
    Remove-Item -LiteralPath $BuildDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $ZipPath) -Force | Out-Null

& $Python -m pip install --target $BuildDirectory "boto3>=1.35"
Copy-Item -LiteralPath (Join-Path $ProjectRoot "src\mevo_collector") -Destination $BuildDirectory -Recurse
Get-ChildItem -Path $BuildDirectory -Directory -Filter "__pycache__" -Recurse | Remove-Item -Recurse -Force
Get-ChildItem -Path $BuildDirectory -File -Include "*.pyc", "*.pyo" -Recurse | Remove-Item -Force

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
[System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem") | Out-Null
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $BuildDirectory,
    $ZipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)
Write-Output "Created $ZipPath"
