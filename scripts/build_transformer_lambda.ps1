$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SourcePackage = Join-Path $ProjectRoot "src\mevo_transformer"
$CodeBuildDirectory = Join-Path $ProjectRoot "build\transformer-code"
$LayerBuildDirectory = Join-Path $ProjectRoot "build\transformer-layer"
$LayerPythonDirectory = Join-Path $LayerBuildDirectory "python"
$DistDirectory = Join-Path $ProjectRoot "dist"
$CodeZipPath = Join-Path $DistDirectory "mevo-cleaned-transformer-code.zip"
$LayerZipPath = Join-Path $DistDirectory "mevo-cleaned-transformer-dependencies-layer.zip"
$Python = if ($env:MEVO_PYTHON) { $env:MEVO_PYTHON } else { "python" }

function Remove-DirectoryIfPresent {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Remove-PythonArtifacts {
    param([Parameter(Mandatory = $true)][string]$Root)

    $PythonCacheDirectories = @(
        Get-ChildItem -LiteralPath $Root -Directory -Recurse -Force |
            Where-Object { $_.Name -eq "__pycache__" } |
            Sort-Object FullName -Descending
    )
    foreach ($Directory in $PythonCacheDirectories) {
        Remove-Item -LiteralPath $Directory.FullName -Recurse -Force
    }

    $CompiledPythonFiles = @(
        Get-ChildItem -LiteralPath $Root -File -Recurse -Force |
            Where-Object { $_.Extension -in @(".pyc", ".pyo") }
    )
    foreach ($File in $CompiledPythonFiles) {
        Remove-Item -LiteralPath $File.FullName -Force
    }
}

function Get-DirectorySizeBytes {
    param([Parameter(Mandatory = $true)][string]$Path)

    [Int64]$Size = 0
    $Files = @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
    foreach ($File in $Files) {
        $Size += $File.Length
    }
    return $Size
}

function Get-RelativeArchivePath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Path
    )

    return $Path.Substring($Root.Length).TrimStart([char[]]"\/").Replace("\", "/")
}

function New-DeterministicZip {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDirectory,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Force
    }

    $DestinationParent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $DestinationParent -Force | Out-Null

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $Root = (Resolve-Path -LiteralPath $SourceDirectory).Path.TrimEnd([char[]]"\/")
    $ArchiveTimestamp = [DateTimeOffset]::Parse("1980-01-01T00:00:00+00:00")
    $Archive = [System.IO.Compression.ZipFile]::Open(
        $Destination,
        [System.IO.Compression.ZipArchiveMode]::Create
    )

    try {
        $Directories = @(
            Get-ChildItem -LiteralPath $SourceDirectory -Directory -Recurse -Force |
                Sort-Object FullName
        )
        foreach ($Directory in $Directories) {
            $RelativePath = Get-RelativeArchivePath -Root $Root -Path $Directory.FullName
            $Entry = $Archive.CreateEntry(
                "$RelativePath/",
                [System.IO.Compression.CompressionLevel]::Optimal
            )
            $Entry.LastWriteTime = $ArchiveTimestamp
        }

        $Files = @(
            Get-ChildItem -LiteralPath $SourceDirectory -File -Recurse -Force |
                Sort-Object FullName
        )
        foreach ($File in $Files) {
            $RelativePath = Get-RelativeArchivePath -Root $Root -Path $File.FullName
            $Entry = $Archive.CreateEntry(
                $RelativePath,
                [System.IO.Compression.CompressionLevel]::Optimal
            )
            $Entry.LastWriteTime = $ArchiveTimestamp

            $InputStream = [System.IO.File]::OpenRead($File.FullName)
            try {
                $OutputStream = $Entry.Open()
                try {
                    $InputStream.CopyTo($OutputStream)
                }
                finally {
                    $OutputStream.Dispose()
                }
            }
            finally {
                $InputStream.Dispose()
            }
        }
    }
    finally {
        $Archive.Dispose()
    }
}

if (-not (Test-Path -LiteralPath $SourcePackage -PathType Container)) {
    throw "Transformer source package not found: $SourcePackage"
}

Remove-DirectoryIfPresent -Path $CodeBuildDirectory
Remove-DirectoryIfPresent -Path $LayerBuildDirectory
New-Item -ItemType Directory -Path $CodeBuildDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $LayerPythonDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $DistDirectory -Force | Out-Null

if (Test-Path -LiteralPath $CodeZipPath) {
    Remove-Item -LiteralPath $CodeZipPath -Force
}
if (Test-Path -LiteralPath $LayerZipPath) {
    Remove-Item -LiteralPath $LayerZipPath -Force
}

Copy-Item -LiteralPath $SourcePackage -Destination $CodeBuildDirectory -Recurse
Remove-PythonArtifacts -Root $CodeBuildDirectory

$PipArguments = @(
    "-m",
    "pip",
    "install",
    "--isolated",
    "--disable-pip-version-check",
    "--no-cache-dir",
    "--no-compile",
    "--index-url",
    "https://pypi.org/simple",
    "--target",
    $LayerPythonDirectory,
    "--platform",
    # PyArrow 25.0.1 publishes the CPython 3.14 x86_64 wheel as
    # manylinux_2_28_x86_64. AWS Lambda Python 3.14 runs on AL2023 (glibc 2.34),
    # so this Linux wheel is compatible with the target runtime.
    "manylinux_2_28_x86_64",
    "--implementation",
    "cp",
    "--python-version",
    "3.14",
    "--only-binary=:all:",
    "pyarrow==25.0.1",
    "tzdata==2026.3"
)

Write-Output "Installing Linux x86_64 CPython 3.14 layer dependencies..."
& $Python @PipArguments
if ($LASTEXITCODE -ne 0) {
    throw "pip could not install Linux-compatible CPython 3.14 binary wheels. No source-build or local-Windows-wheel fallback was used."
}

Remove-PythonArtifacts -Root $LayerBuildDirectory

if (-not (Test-Path -LiteralPath (Join-Path $LayerPythonDirectory "pyarrow") -PathType Container)) {
    throw "The dependency layer does not contain python/pyarrow after pip installation."
}
if (-not (Test-Path -LiteralPath (Join-Path $LayerPythonDirectory "tzdata") -PathType Container)) {
    throw "The dependency layer does not contain python/tzdata after pip installation."
}

$PyArrowMetadata = Get-ChildItem -LiteralPath $LayerPythonDirectory -Directory -Filter "pyarrow-*.dist-info" |
    Select-Object -First 1
if ($null -eq $PyArrowMetadata) {
    throw "Could not find PyArrow package metadata in the dependency layer."
}
$PyArrowVersion = (
    Select-String -LiteralPath (Join-Path $PyArrowMetadata.FullName "METADATA") -Pattern "^Version:\s*(.+)$" |
        Select-Object -First 1
).Matches.Groups[1].Value.Trim()
$TzdataMetadata = Get-ChildItem -LiteralPath $LayerPythonDirectory -Directory -Filter "tzdata-*.dist-info" |
    Select-Object -First 1
if ($null -eq $TzdataMetadata) {
    throw "Could not find tzdata package metadata in the dependency layer."
}
$TzdataVersion = (
    Select-String -LiteralPath (Join-Path $TzdataMetadata.FullName "METADATA") -Pattern "^Version:\s*(.+)$" |
        Select-Object -First 1
).Matches.Groups[1].Value.Trim()

if ($PyArrowVersion -ne "25.0.1" -or $TzdataVersion -ne "2026.3") {
    throw "Dependency metadata does not match the pinned versions: pyarrow=$PyArrowVersion, tzdata=$TzdataVersion"
}

New-DeterministicZip -SourceDirectory $CodeBuildDirectory -Destination $CodeZipPath
New-DeterministicZip -SourceDirectory $LayerBuildDirectory -Destination $LayerZipPath

$CodeZipBytes = (Get-Item -LiteralPath $CodeZipPath).Length
$LayerZipBytes = (Get-Item -LiteralPath $LayerZipPath).Length
$CodeUnpackedBytes = Get-DirectorySizeBytes -Path $CodeBuildDirectory
$LayerUnpackedBytes = Get-DirectorySizeBytes -Path $LayerBuildDirectory
$CombinedUnpackedBytes = $CodeUnpackedBytes + $LayerUnpackedBytes

Write-Output ("code ZIP size MB: {0:N2}" -f ($CodeZipBytes / 1MB))
Write-Output ("layer ZIP size MB: {0:N2}" -f ($LayerZipBytes / 1MB))
Write-Output ("code unpacked size MB: {0:N2}" -f ($CodeUnpackedBytes / 1MB))
Write-Output ("layer unpacked size MB: {0:N2}" -f ($LayerUnpackedBytes / 1MB))
Write-Output ("combined unpacked size MB: {0:N2}" -f ($CombinedUnpackedBytes / 1MB))
Write-Output "PyArrow version: $PyArrowVersion"
Write-Output "tzdata version: $TzdataVersion"

if ($CombinedUnpackedBytes -ge (250MB)) {
    throw ("Combined unpacked size is {0:N2} MB, which meets or exceeds the 250 MB Lambda ZIP + layers limit." -f ($CombinedUnpackedBytes / 1MB))
}

Write-Output "Created $CodeZipPath"
Write-Output "Created $LayerZipPath"
