[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^[a-z][a-z0-9_]+$')]
    [string]$Module,

    [string]$SshTarget = 'root@217.216.32.33',
    [string]$Database = 'MOG_DEV'
)

$ErrorActionPreference = 'Stop'
$modulePath = Join-Path -Path $PSScriptRoot -ChildPath $Module
$remoteRoot = '/srv/docker/odoo/custom-addons'
$remoteModule = "$remoteRoot/$Module"
$sshOptions = @(
    '-o', 'BatchMode=yes',
    '-o', 'ConnectTimeout=15',
    '-o', 'StrictHostKeyChecking=accept-new'
)

if (-not (Test-Path -LiteralPath (Join-Path $modulePath '__manifest__.py')) -or
    -not (Test-Path -LiteralPath $modulePath -PathType Container)) {
    throw "Odoo module '$Module' not found or __manifest__.py is missing: $modulePath"
}

Write-Host "Deploying $Module to $SshTarget ($Database)..."

# Remove the previous copy so deleted local files do not remain on DEV.
& ssh @sshOptions $SshTarget "rm -rf '$remoteModule' && mkdir -p '$remoteModule'"
if ($LASTEXITCODE -ne 0) { throw "DEV connection failed or the SSH key is unavailable" }

& scp @sshOptions -r $modulePath "$SshTarget`:$remoteRoot/"
if ($LASTEXITCODE -ne 0) { throw "Module upload to DEV failed" }

& ssh @sshOptions $SshTarget "docker exec odoo odoo -d '$Database' -u '$Module' --stop-after-init --no-http"
if ($LASTEXITCODE -ne 0) { throw "Odoo upgrade failed for $Module" }

Write-Host "Deploy succeeded: $Module -> $SshTarget / $Database" -ForegroundColor Green
