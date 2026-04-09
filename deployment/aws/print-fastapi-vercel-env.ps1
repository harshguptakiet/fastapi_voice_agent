param(
  [Parameter(Mandatory = $false)] [string]$Region = "us-east-1",
  [Parameter(Mandatory = $false)] [string]$Cluster = "tekurious-prod",
  [Parameter(Mandatory = $false)] [string]$Service = "fastapi-server",
  [Parameter(Mandatory = $false)] [string]$TenantId = "tenant-demo"
)

$ErrorActionPreference = "Stop"

$RepoRoot = "c:/New folder (6)/MAIN"
$AwsPython = "$RepoRoot/.venv/Scripts/python.exe"
$UseAwsExe = [bool](Get-Command aws -ErrorAction SilentlyContinue)

if (-not $UseAwsExe -and -not (Test-Path $AwsPython)) {
  throw "AWS CLI not found. Install aws.exe or ensure $AwsPython exists."
}

function Invoke-AwsText {
  param([Parameter(Mandatory = $true)] [string[]]$Args)

  $output = ""
  if ($UseAwsExe) {
    $output = (& aws @Args 2>&1 | Out-String)
  } else {
    $output = (& $AwsPython -m awscli @Args 2>&1 | Out-String)
  }

  if ($LASTEXITCODE -ne 0) {
    $details = if ([string]::IsNullOrWhiteSpace($output)) { "<no output>" } else { $output.Trim() }
    throw "aws $($Args -join ' ') failed with exit code $LASTEXITCODE`n$details"
  }

  return $output.Trim()
}

$taskArn = Invoke-AwsText -Args @(
  "ecs", "list-tasks",
  "--region", $Region,
  "--cluster", $Cluster,
  "--service-name", $Service,
  "--desired-status", "RUNNING",
  "--query", "taskArns[0]",
  "--output", "text"
)

if ([string]::IsNullOrWhiteSpace($taskArn) -or $taskArn -eq "None") {
  throw "No running task found for service '$Service' in cluster '$Cluster'."
}

$eniId = Invoke-AwsText -Args @(
  "ecs", "describe-tasks",
  "--region", $Region,
  "--cluster", $Cluster,
  "--tasks", $taskArn,
  "--query", "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]",
  "--output", "text"
)

$publicIp = Invoke-AwsText -Args @(
  "ec2", "describe-network-interfaces",
  "--region", $Region,
  "--network-interface-ids", $eniId,
  "--query", "NetworkInterfaces[0].Association.PublicIp",
  "--output", "text"
)

if ([string]::IsNullOrWhiteSpace($publicIp) -or $publicIp -eq "None") {
  throw "Public IP not found for running task network interface '$eniId'."
}

$baseUrl = "http://${publicIp}:8001"

Write-Host "Current FastAPI URL:"
Write-Host "$baseUrl/health"
Write-Host ""
Write-Host "Vercel Production env values (set at least TEKURIOUS_FASTAPI_URL):"
Write-Host "TEKURIOUS_FASTAPI_URL=$baseUrl"
Write-Host "FASTAPI_TENANT_ID=$TenantId"
Write-Host "# Optional fallbacks (same URL is fine):"
Write-Host "TEKURIOUS_AI_BASE_URL=$baseUrl"
Write-Host "EDUTHUM_BASE_URL=$baseUrl"
Write-Host "FASTAPI_BASE_URL=$baseUrl"
Write-Host "FASTAPI_VOICE_BASE_URL=$baseUrl"

Write-Host ""
Write-Host "Apply in Vercel Dashboard -> Project -> Settings -> Environment Variables (Production),"
Write-Host "or: vercel env add TEKURIOUS_FASTAPI_URL production"
Write-Host "    vercel env add FASTAPI_TENANT_ID production"
