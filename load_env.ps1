    param (
        [string]$EnvFilePath = "./.env"
    )

    if (Test-Path $EnvFilePath) {
        Get-Content $EnvFilePath | ForEach-Object {
            if ($_ -match "^([^#=]+)=(.*)$") {
                $key = $Matches[1].Trim()
                $value = $Matches[2].Trim()
                # Remove quotes if present
                $value = $value -replace "^['""]|['""]$",""
                Set-Item -Path Env:$key -Value $value
                Write-Host "Set environment variable: $key=$value"
            }
        }
    } else {
        Write-Error "Error: .env file not found at $EnvFilePath"
    }