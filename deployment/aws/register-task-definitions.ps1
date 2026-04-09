param(
  [Parameter(Mandatory=$true)] [string]$Region
)

$ErrorActionPreference = 'Stop'

$AwsPython = 'c:/New folder (6)/MAIN/.venv/Scripts/python.exe'
$UseAwsExe = [bool](Get-Command aws -ErrorAction SilentlyContinue)

if (-not $UseAwsExe -and -not (Test-Path $AwsPython)) {
  throw "AWS CLI not found. Install aws.exe or ensure $AwsPython exists."
}

function Invoke-Aws {
  param(
    [Parameter(Mandatory=$true)] [string[]]$Args
  )

  if ($UseAwsExe) {
    & aws @Args
  } else {
    & $AwsPython -m awscli @Args
  }

  if ($LASTEXITCODE -ne 0) {
    throw "aws $($Args -join ' ') failed with exit code $LASTEXITCODE"
  }
}

$TaskFiles = @(
  'c:/New folder (6)/MAIN/deployment/aws/task-definitions/frontend.task.json',
  'c:/New folder (6)/MAIN/deployment/aws/task-definitions/fastapi-server.task.json',
  'c:/New folder (6)/MAIN/deployment/aws/task-definitions/religious-bot.task.json',
  'c:/New folder (6)/MAIN/deployment/aws/task-definitions/education-bot.task.json'
)

foreach ($taskFile in $TaskFiles) {
  Write-Host "Registering task definition from $taskFile"
  Invoke-Aws -Args @('ecs', 'register-task-definition', '--region', $Region, '--cli-input-json', "file://$taskFile")
}

Write-Host "Task definitions registered."
