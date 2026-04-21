param(
    [ValidateSet("client", "server", "rsa", "all")]
    [string[]]$Targets = @("all")
)

$ErrorActionPreference = "Stop"

$python = if ($env:CONDA_PREFIX) {
    Join-Path $env:CONDA_PREFIX "python.exe"
}
else {
    "python"
}

Write-Host "Using Python: $python"

function Assert-PythonModules {
    param([string[]]$Modules)

    $moduleList = $Modules -join ", "
    $importList = ($Modules | ForEach-Object { "'$_'" }) -join ", "
    & $python -c "import importlib; [importlib.import_module(name) for name in [$importList]]; print('Environment OK')" | Out-Null
}

function Test-FileLocked {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return $false
    }

    try {
        $stream = [System.IO.File]::Open($Path, "Open", "ReadWrite", "None")
        $stream.Close()
        return $false
    }
    catch {
        return $true
    }
}

function Invoke-BuildTarget {
    param(
        [string]$Name,
        [string]$OutputPath,
        [scriptblock]$Command
    )

    if (Test-FileLocked $OutputPath) {
        Write-Warning "Skipping $Name because the output file is in use: $OutputPath"
        return $false
    }

    Write-Host "Building $Name ..."
    & $Command
    return $true
}

$selectedTargets = if ($Targets -contains "all") {
    @("client", "server", "rsa")
}
else {
    $Targets
}

$failedTargets = @()

if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

foreach ($target in $selectedTargets) {
    switch ($target) {
        "client" {
            Assert-PythonModules @("websockets", "PIL", "PyInstaller")
            $buildOk = Invoke-BuildTarget "SecureChat" "dist/SecureChat.exe" {
                & $python -m PyInstaller SecureChat.spec -y
            }
            if (-not $buildOk) {
                $failedTargets += "client"
            }
        }
        "server" {
            Assert-PythonModules @("websockets", "PyInstaller")
            $buildOk = Invoke-BuildTarget "SecureChatServer" "dist/SecureChatServer.exe" {
                & $python -m PyInstaller SecureChatServer.spec -y
            }
            if (-not $buildOk) {
                $failedTargets += "server"
            }
        }
        "rsa" {
            Assert-PythonModules @("PyInstaller")
            $buildOk = Invoke-BuildTarget "RSA_Encrypt_Decrypt_Tool" "dist/RSA_Encrypt_Decrypt_Tool.exe" {
                & $python -m PyInstaller --onefile --windowed --name RSA_Encrypt_Decrypt_Tool InfoSecurWork_GUI.py -y
            }
            if (-not $buildOk) {
                $failedTargets += "rsa"
            }
        }
    }
}

if ($failedTargets.Count -gt 0) {
    throw "Build skipped for target(s): $($failedTargets -join ', '). Close the corresponding exe and rerun if needed."
}

Write-Host "Build complete. Outputs are in dist/."