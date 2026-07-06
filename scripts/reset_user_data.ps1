$ErrorActionPreference = "Stop"

$allowedNames = @(
    "CompanyDecisionMonitor",
    "Company Decision Monitor"
)

$roots = @()
if ($env:APPDATA) {
    $roots += $env:APPDATA
}
if ($env:LOCALAPPDATA) {
    $roots += $env:LOCALAPPDATA
}

$targets = New-Object System.Collections.Generic.List[string]
foreach ($root in $roots) {
    foreach ($name in $allowedNames) {
        $targets.Add((Join-Path -Path $root -ChildPath $name))
    }
}

$uniqueTargets = $targets | Sort-Object -Unique
foreach ($target in $uniqueTargets) {
    $leaf = Split-Path -Path $target -Leaf
    $parent = Split-Path -Path $target -Parent
    if (-not ($allowedNames -contains $leaf)) {
        throw "Refusing unsafe reset target: $target"
    }
    if (-not ($roots -contains $parent)) {
        throw "Refusing target outside AppData/LocalAppData: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Write-Host "Deleting $target"
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Write-Host "Company Decision Monitor local user data has been cleared."
