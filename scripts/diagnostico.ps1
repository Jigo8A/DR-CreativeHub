[CmdletBinding()]
param(
    [switch]$Quiet
)

function Get-CreativeHubPrerequisites {
    $requirements = @(
        @{ Name = "Python"; Command = "python"; Hint = "Instale o Python 3.12 ou mais recente e marque Add Python to PATH." },
        @{ Name = "Node.js"; Command = "node"; Hint = "Instale a versao LTS do Node.js." },
        @{ Name = "npm"; Command = "npm"; Hint = "Reinstale a versao LTS do Node.js, que inclui o npm." },
        @{ Name = "FFmpeg"; Command = "ffmpeg"; Hint = "Instale o FFmpeg e adicione a pasta bin ao PATH." }
    )

    foreach ($requirement in $requirements) {
        $command = Get-Command $requirement.Command -ErrorAction SilentlyContinue
        [PSCustomObject]@{
            Name = $requirement.Name
            Ready = $null -ne $command
            Message = if ($command) { $command.Source } else { $requirement.Hint }
        }
    }
}

function Test-CreativeHubPrerequisites {
    param([switch]$Quiet)

    $checks = @(Get-CreativeHubPrerequisites)
    if (-not $Quiet) {
        $checks | Format-Table Name, Ready, Message -AutoSize | Out-Host
    }
    return (@($checks | Where-Object { -not $_.Ready }).Count -eq 0)
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not (Test-CreativeHubPrerequisites -Quiet:$Quiet)) {
        exit 1
    }
}
