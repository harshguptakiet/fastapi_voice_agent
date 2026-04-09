param(
  [Parameter(Mandatory=$true)] [string]$AccountId,
  [Parameter(Mandatory=$true)] [string]$Region,
  [Parameter(Mandatory=$true)] [string]$Tag
)

$ErrorActionPreference = 'Stop'

$AwsPython = 'c:/New folder (6)/MAIN/.venv/Scripts/python.exe'
$UseAwsExe = [bool](Get-Command aws -ErrorAction SilentlyContinue)

if (-not $UseAwsExe -and -not (Test-Path $AwsPython)) {
  throw "AWS CLI not found. Install aws.exe or ensure $AwsPython exists."
}

function Invoke-Aws {
  param(
    [Parameter(Mandatory=$true)] [string[]]$Args,
    [switch]$AllowFailure
  )

  if ($UseAwsExe) {
    & aws @Args
  } else {
    & $AwsPython -m awscli @Args
  }

  $exitCode = $LASTEXITCODE
  if (-not $AllowFailure -and $exitCode -ne 0) {
    throw "aws $($Args -join ' ') failed with exit code $exitCode"
  }

  return $exitCode
}

function Invoke-External {
  param(
    [Parameter(Mandatory=$true)] [scriptblock]$Command,
    [Parameter(Mandatory=$true)] [string]$Description
  )

  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Description failed with exit code $LASTEXITCODE"
  }
}

function Ensure-EcrRepository {
  param(
    [Parameter(Mandatory=$true)] [string]$RepositoryName,
    [Parameter(Mandatory=$true)] [string]$Region
  )

  $describeExitCode = Invoke-Aws -AllowFailure -Args @('ecr', 'describe-repositories', '--region', $Region, '--repository-names', $RepositoryName)
  if ($describeExitCode -ne 0) {
    Write-Host "Creating ECR repository $RepositoryName..."
    Invoke-Aws -Args @('ecr', 'create-repository', '--region', $Region, '--repository-name', $RepositoryName) *> $null
  }
}

$RepoRoot = "c:/New folder (6)/MAIN"

$EcrBase = "$AccountId.dkr.ecr.$Region.amazonaws.com"

Write-Host "Logging into ECR..."
Invoke-External -Description 'ECR login' -Command {
  if ($UseAwsExe) {
    $password = aws ecr get-login-password --region $Region
  } else {
    $password = & $AwsPython -m awscli ecr get-login-password --region $Region
    if ($LASTEXITCODE -ne 0) {
      throw "aws ecr get-login-password failed with exit code $LASTEXITCODE"
    }
  }

  $password | docker login --username AWS --password-stdin $EcrBase
}

$images = @(
  @{ Name='chatbot-frontend'; Path="$RepoRoot/tekurious-chatbot-main/tekurious-chatbot-ui" },
  @{ Name='fastapi-server'; Path="$RepoRoot/fastapi_server" },
  @{ Name='religious-bot'; Path="$RepoRoot/tekurious-chatbot-main/bots/religious-ai/src" },
  @{ Name='education-bot'; Path="$RepoRoot/tekurious-chatbot-main/bots/education-ai/src" }
)

foreach ($img in $images) {
  Ensure-EcrRepository -RepositoryName $img.Name -Region $Region

  $localTag = "$($img.Name):$Tag"
  $remoteTag = "$EcrBase/$($img.Name):$Tag"

  Write-Host "Building $localTag from $($img.Path)..."
  Invoke-External -Description "docker build $localTag" -Command {
    docker build -t $localTag $img.Path
  }

  Write-Host "Tagging $remoteTag..."
  Invoke-External -Description "docker tag $localTag" -Command {
    docker tag $localTag $remoteTag
  }

  Write-Host "Pushing $remoteTag..."
  Invoke-External -Description "docker push $remoteTag" -Command {
    docker push $remoteTag
  }
}

Write-Host "All images pushed successfully."
