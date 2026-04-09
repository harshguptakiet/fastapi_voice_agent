param(
  [Parameter(Mandatory = $true)] [string]$AccountId,
  [Parameter(Mandatory = $false)] [string]$Region = "us-east-1",
  [Parameter(Mandatory = $false)] [string]$Cluster = "tekurious-prod",
  [Parameter(Mandatory = $false)] [string]$Service = "fastapi-server",
  [Parameter(Mandatory = $false)] [string]$Tag = (Get-Date -Format "yyyyMMdd-HHmmss"),
  [Parameter(Mandatory = $false)] [string[]]$ScaleDownServices = @("religious-bot", "education-bot")
)

$ErrorActionPreference = "Stop"

$RepoRoot = "c:/New folder (6)/MAIN"
$TaskDefPath = "$RepoRoot/deployment/aws/task-definitions/fastapi-server.task.json"
$BuildContext = "$RepoRoot/fastapi_server"
$RepositoryName = "fastapi-server"
$EcrBase = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$ImageUri = "$EcrBase/${RepositoryName}:$Tag"
$AwsPython = "$RepoRoot/.venv/Scripts/python.exe"
$UseAwsExe = [bool](Get-Command aws -ErrorAction SilentlyContinue)

if (-not $UseAwsExe -and -not (Test-Path $AwsPython)) {
  throw "AWS CLI not found. Install aws.exe or ensure $AwsPython exists."
}

function Invoke-AwsText {
  param(
    [Parameter(Mandatory = $true)] [string[]]$Args,
    [switch]$AllowFailure
  )

  $output = ""
  $previousEap = $ErrorActionPreference
  try {
    # Native tools can write warnings to stderr; capture both streams without terminating the script.
    $ErrorActionPreference = "Continue"
    if ($UseAwsExe) {
      $output = (& aws @Args 2>&1 | Out-String)
    } else {
      $output = (& $AwsPython -m awscli @Args 2>&1 | Out-String)
    }
  } finally {
    $ErrorActionPreference = $previousEap
  }

  $exitCode = $LASTEXITCODE
  if (-not $AllowFailure -and $exitCode -ne 0) {
    $details = if ([string]::IsNullOrWhiteSpace($output)) { "<no output>" } else { $output.Trim() }
    throw "aws $($Args -join ' ') failed with exit code $exitCode`n$details"
  }

  return ($output.Trim())
}

function Invoke-AwsJson {
  param([Parameter(Mandatory = $true)] [string[]]$Args)
  $txt = Invoke-AwsText -Args $Args
  if ([string]::IsNullOrWhiteSpace($txt)) {
    return $null
  }
  return ($txt | ConvertFrom-Json)
}

function Invoke-External {
  param(
    [Parameter(Mandatory = $true)] [scriptblock]$Command,
    [Parameter(Mandatory = $true)] [string]$Description
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

function Assert-DockerReady {
  $dockerExists = [bool](Get-Command docker -ErrorAction SilentlyContinue)
  if (-not $dockerExists) {
    throw "Docker CLI not found. Install Docker Desktop and ensure docker is on PATH."
  }

  cmd /c "docker info >NUL 2>NUL" | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not running. Start Docker Desktop and retry."
  }
}

if (-not (Test-Path $TaskDefPath)) {
  throw "Task definition file not found: $TaskDefPath"
}

Assert-DockerReady

Write-Host "Logging into ECR $EcrBase..."
if ($UseAwsExe) {
  $password = aws ecr get-login-password --region $Region
} else {
  $password = & $AwsPython -m awscli ecr get-login-password --region $Region
  if ($LASTEXITCODE -ne 0) {
    throw "aws ecr get-login-password failed with exit code $LASTEXITCODE"
  }
}
$password | docker login --username AWS --password-stdin $EcrBase | Out-Null

$describeExit = 0
Invoke-AwsText -AllowFailure -Args @("ecr", "describe-repositories", "--region", $Region, "--repository-names", $RepositoryName) | Out-Null
$describeExit = $LASTEXITCODE
if ($describeExit -ne 0) {
  Write-Host "Creating ECR repository $RepositoryName..."
  Invoke-AwsText -Args @("ecr", "create-repository", "--region", $Region, "--repository-name", $RepositoryName) | Out-Null
}

$localTag = "${RepositoryName}:$Tag"
Write-Host "Building image $localTag..."
Invoke-External -Description "docker build" -Command { docker build -t $localTag $BuildContext }

Write-Host "Tagging image as $ImageUri..."
Invoke-External -Description "docker tag" -Command { docker tag $localTag $ImageUri }

Write-Host "Pushing image $ImageUri..."
Invoke-External -Description "docker push" -Command { docker push $ImageUri }

$taskDefObj = Get-Content -Raw $TaskDefPath | ConvertFrom-Json
$taskDefObj.containerDefinitions[0].image = $ImageUri
$containerName = [string]$taskDefObj.containerDefinitions[0].name
$containerPort = [int]$taskDefObj.containerDefinitions[0].portMappings[0].containerPort

$tmpTaskDefPath = [System.IO.Path]::GetTempFileName()
$taskDefJson = $taskDefObj | ConvertTo-Json -Depth 30
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($tmpTaskDefPath, $taskDefJson, $utf8NoBom)

Write-Host "Registering task definition..."
$taskDefArn = Invoke-AwsText -Args @("ecs", "register-task-definition", "--region", $Region, "--cli-input-json", "file://$tmpTaskDefPath", "--query", "taskDefinition.taskDefinitionArn", "--output", "text")
if ([string]::IsNullOrWhiteSpace($taskDefArn) -or $taskDefArn -eq "None") {
  throw "Failed to register task definition."
}

Write-Host "Scaling down optional services..."
foreach ($svc in $ScaleDownServices) {
  Invoke-AwsText -AllowFailure -Args @("ecs", "update-service", "--region", $Region, "--cluster", $Cluster, "--service", $svc, "--desired-count", "0") | Out-Null
}

$allServices = @($Service) + $ScaleDownServices
$emptyLbFile = "$env:TEMP/empty-lb.json"
"[]" | Set-Content -Path $emptyLbFile -Encoding ASCII

Write-Host "Detaching load balancers from services..."
foreach ($svc in $allServices) {
  Invoke-AwsText -AllowFailure -Args @("ecs", "update-service", "--region", $Region, "--cluster", $Cluster, "--service", $svc, "--load-balancers", "file://$emptyLbFile", "--force-new-deployment") | Out-Null
}

$svcJson = Invoke-AwsJson -Args @("ecs", "describe-services", "--region", $Region, "--cluster", $Cluster, "--services", $Service)
if (-not $svcJson -or -not $svcJson.services -or $svcJson.services.Count -eq 0) {
  throw "Service $Service not found in cluster $Cluster"
}

$awsvpc = $svcJson.services[0].networkConfiguration.awsvpcConfiguration
$subnets = @($awsvpc.subnets)
$securityGroups = @($awsvpc.securityGroups)

if ($subnets.Count -eq 0 -or $securityGroups.Count -eq 0) {
  throw "Service network configuration missing subnets/security groups."
}

foreach ($sg in $securityGroups) {
  Invoke-AwsText -AllowFailure -Args @("ec2", "authorize-security-group-ingress", "--region", $Region, "--group-id", [string]$sg, "--protocol", "tcp", "--port", [string]$containerPort, "--cidr", "0.0.0.0/0") | Out-Null
}

$subnetsJson = ($subnets | ForEach-Object { '"' + $_ + '"' }) -join ","
$sgJson = ($securityGroups | ForEach-Object { '"' + $_ + '"' }) -join ","
$netCfgFile = "$env:TEMP/netcfg-fastapi.json"
@"
{
  "awsvpcConfiguration": {
    "subnets": [$subnetsJson],
    "securityGroups": [$sgJson],
    "assignPublicIp": "ENABLED"
  }
}
"@ | Set-Content -Path $netCfgFile -Encoding ASCII

Write-Host "Updating $Service in cheap mode..."
Invoke-AwsText -Args @(
  "ecs", "update-service",
  "--region", $Region,
  "--cluster", $Cluster,
  "--service", $Service,
  "--task-definition", $taskDefArn,
  "--network-configuration", "file://$netCfgFile",
  "--desired-count", "1",
  "--force-new-deployment"
) | Out-Null

Write-Host "Waiting for service to stabilize..."
Invoke-AwsText -Args @("ecs", "wait", "services-stable", "--region", $Region, "--cluster", $Cluster, "--services", $Service) | Out-Null

$runningArn = Invoke-AwsText -Args @("ecs", "list-tasks", "--region", $Region, "--cluster", $Cluster, "--service-name", $Service, "--desired-status", "RUNNING", "--query", "taskArns[0]", "--output", "text")
if ([string]::IsNullOrWhiteSpace($runningArn) -or $runningArn -eq "None") {
  $latestEvent = Invoke-AwsText -Args @("ecs", "describe-services", "--region", $Region, "--cluster", $Cluster, "--services", $Service, "--query", "services[0].events[0].message", "--output", "text")
  throw "Service is stable but no running task ARN found. Latest event: $latestEvent"
}

$eniId = Invoke-AwsText -Args @("ecs", "describe-tasks", "--region", $Region, "--cluster", $Cluster, "--tasks", $runningArn, "--query", "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]", "--output", "text")
$publicIp = Invoke-AwsText -Args @("ec2", "describe-network-interfaces", "--region", $Region, "--network-interface-ids", $eniId, "--query", "NetworkInterfaces[0].Association.PublicIp", "--output", "text")

Write-Host ""
Write-Host "Cheap-mode redeploy complete."
Write-Host "Image URI: $ImageUri"
Write-Host "FastAPI URL: http://${publicIp}:$containerPort/health"
Write-Host "Note: Public IP may change after task replacement/redeploy."

Remove-Item $tmpTaskDefPath -Force -ErrorAction SilentlyContinue
Remove-Item $emptyLbFile -Force -ErrorAction SilentlyContinue
Remove-Item $netCfgFile -Force -ErrorAction SilentlyContinue
