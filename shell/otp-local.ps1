# OTP-Local PowerShell Profile & Completion Module
# Enables native tab completions, pipeline processing, and clipboard integration for Windows PowerShell 7+.

<#
.SYNOPSIS
    Retrieves or copies a Time-based One-Time Password (TOTP) code using OTP-Local CLI.

.DESCRIPTION
    Integrates OTP-Local with the PowerShell pipeline, native Windows DPAPI, and clipboard.
    Exposes Get-OtpCode, Copy-OtpCode, and aliases 'otp', 'totp', and 'otpc'.
#>

function Get-OtpCode {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromPipeline = $true, HelpMessage = "Account identifier for the OTP token")]
        [string]$Account,

        [Parameter(HelpMessage = "Target storage backend")]
        [ValidateSet("dpapi", "onepassword", "pass-otp", "totpm", "yubikey", "tpm2-totp", "keychain")]
        [string]$Backend = "dpapi"
    )

    process {
        if ($Account) {
            $code = & otp-local show --backend $Backend --account $Account
            if ($LASTEXITCODE -eq 0 -and $code) {
                return $code.Trim()
            }
        } else {
            $code = & otp-local select --backend $Backend
            if ($LASTEXITCODE -eq 0 -and $code) {
                return $code.Trim()
            }
        }
    }
}

function Copy-OtpCode {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0, ValueFromPipeline = $true, HelpMessage = "Account identifier for the OTP token")]
        [string]$Account,

        [Parameter(HelpMessage = "Target storage backend")]
        [ValidateSet("dpapi", "onepassword", "pass-otp", "totpm", "yubikey", "tpm2-totp", "keychain")]
        [string]$Backend = "dpapi"
    )

    process {
        if ($Account) {
            & otp-local copy --backend $Backend --account $Account
        } else {
            & otp-local select --backend $Backend --copy
        }
    }
}

function Select-OtpCode {
    [CmdletBinding()]
    param(
        [Parameter(HelpMessage = "Target storage backend")]
        [ValidateSet("dpapi", "onepassword", "pass-otp", "totpm", "yubikey", "tpm2-totp", "keychain")]
        [string]$Backend = "dpapi",

        [switch]$Copy
    )

    if ($Copy) {
        & otp-local select --backend $Backend --copy
    } else {
        & otp-local select --backend $Backend
    }
}

# Export functions and aliases
Set-Alias -Name otp -Value Get-OtpCode -Scope Global -Option AllScope -ErrorAction SilentlyContinue
Set-Alias -Name totp -Value Get-OtpCode -Scope Global -Option AllScope -ErrorAction SilentlyContinue
Set-Alias -Name otpc -Value Copy-OtpCode -Scope Global -Option AllScope -ErrorAction SilentlyContinue

# Register Argument Completers for PowerShell
$OtpCompleter = {
    param($wordToComplete, $commandAst, $cursorPosition)

    $subcommands = @(
        [System.Management.Automation.CompletionResult]::new('doctor', 'doctor', 'Method', 'Inspect system tools and capabilities'),
        [System.Management.Automation.CompletionResult]::new('tui', 'tui', 'Method', 'Launch interactive Textual TUI dashboard'),
        [System.Management.Automation.CompletionResult]::new('guide', 'guide', 'Method', 'Display operator markdown guides'),
        [System.Management.Automation.CompletionResult]::new('show', 'show', 'Method', 'Output OTP decimal code to terminal'),
        [System.Management.Automation.CompletionResult]::new('copy', 'copy', 'Method', 'Copy OTP code to desktop clipboard'),
        [System.Management.Automation.CompletionResult]::new('select', 'select', 'Method', 'Interactively select and retrieve item'),
        [System.Management.Automation.CompletionResult]::new('enroll', 'enroll', 'Method', 'Enroll new OTP secret or QR code'),
        [System.Management.Automation.CompletionResult]::new('pick', 'pick', 'Method', 'Launch desktop quick-picker'),
        [System.Management.Automation.CompletionResult]::new('import', 'import', 'Method', 'Import OTP credentials from external backups'),
        [System.Management.Automation.CompletionResult]::new('export', 'export', 'Method', 'Export OTP credentials for offline backup'),
        [System.Management.Automation.CompletionResult]::new('audit', 'audit', 'Method', 'Audit stored tokens for duplicate seeds'),
        [System.Management.Automation.CompletionResult]::new('qr', 'qr', 'Method', 'Display terminal UTF-8 QR code for phone scanning'),
        [System.Management.Automation.CompletionResult]::new('agent', 'agent', 'Method', 'Manage background session agent daemon'),
        [System.Management.Automation.CompletionResult]::new('unlock', 'unlock', 'Method', 'Interactively authenticate or unlock CLI session')
    )

    $backends = @('dpapi', 'onepassword', 'pass-otp', 'totpm', 'yubikey', 'tpm2-totp', 'keychain')

    $elements = $commandAst.CommandElements
    if ($elements.Count -le 2) {
        return $subcommands | Where-Object { $_.CompletionText -like "$wordToComplete*" }
    }

    $prev = $elements[$elements.Count - 2].Extent.Text
    if ($prev -eq '--backend') {
        return $backends | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', "Backend: $_")
        }
    }

    $flags = @(
        '--backend', '--account', '--vault', '--store', '--key-home',
        '--entry', '--config', '--service', '--json', '--apply',
        '--format', '--stdout', '--allow-pipe', '--no-notify'
    )
    return $flags | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterName', "Option: $_")
    }
}

Register-ArgumentCompleter -Native -CommandName 'otp-local' -ScriptBlock $OtpCompleter
Register-ArgumentCompleter -CommandName 'Get-OtpCode' -ParameterName 'Backend' -ScriptBlock {
    param($commandName, $parameterName, $wordToComplete, $commandAst, $fakeBoundParameters)
    @('dpapi', 'onepassword', 'pass-otp', 'totpm', 'yubikey', 'tpm2-totp', 'keychain') | Where-Object { $_ -like "$wordToComplete*" }
}
Register-ArgumentCompleter -CommandName 'Copy-OtpCode' -ParameterName 'Backend' -ScriptBlock {
    param($commandName, $parameterName, $wordToComplete, $commandAst, $fakeBoundParameters)
    @('dpapi', 'onepassword', 'pass-otp', 'totpm', 'yubikey', 'tpm2-totp', 'keychain') | Where-Object { $_ -like "$wordToComplete*" }
}
