# OTP-Local NuShell Module
# Structured table outputs, completions, and pipeline integration for NuShell.

def otp_backends [] {
    ["dpapi", "onepassword", "pass-otp", "totpm", "yubikey", "tpm2-totp", "keychain"]
}

def otp_subcommands [] {
    [
        { value: "doctor", description: "Inspect system tools and capabilities" },
        { value: "tui", description: "Launch interactive Textual TUI dashboard" },
        { value: "guide", description: "Display operator markdown guides" },
        { value: "show", description: "Output OTP decimal code to terminal" },
        { value: "copy", description: "Copy OTP code to desktop clipboard" },
        { value: "select", description: "Interactively select and retrieve item" },
        { value: "enroll", description: "Enroll new OTP secret or QR code" },
        { value: "pick", description: "Launch desktop quick-picker" },
        { value: "import", description: "Import OTP credentials from external backups" },
        { value: "export", description: "Export OTP credentials for offline backup" },
        { value: "audit", description: "Audit stored tokens for duplicate seeds" },
        { value: "qr", description: "Display terminal UTF-8 QR code for phone scanning" },
        { value: "agent", description: "Manage background session agent daemon" },
        { value: "unlock", description: "Interactively authenticate or unlock CLI session" }
    ]
}

# External completion specification for otp-local command
export extern "otp-local" [
    subcommand?: string@otp_subcommands
    --backend(-b): string@otp_backends
    --account(-a): string
    --vault(-v): string
    --store: string
    --key-home: string
    --entry: string
    --config: string
    --service: string
    --json
    --apply
    --stdout
    --allow-pipe
    --no-notify
]

# Retrieve a single TOTP code
export def "otp show" [
    account: string
    --backend: string = "dpapi"
] {
    let result = (otp-local show --backend $backend --account $account | str trim)
    $result
}

# Copy an OTP code directly to clipboard
export def "otp copy" [
    account: string
    --backend: string = "dpapi"
] {
    otp-local copy --backend $backend --account $account
}

# Output a structured NuShell table record with TOTP code and metadata
export def "otp record" [
    account: string
    --backend: string = "dpapi"
] {
    let code = (otp show $account --backend $backend)
    let current_sec = (date now | format date "%s" | into int)
    let remaining = (30 - ($current_sec mod 30))
    {
        account: $account,
        backend: $backend,
        code: $code,
        remaining_seconds: $remaining
    }
}
