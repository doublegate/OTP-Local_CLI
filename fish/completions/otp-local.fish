# Fish completion for otp-local

set -l commands doctor tui guide show copy select enroll pick import export audit qr agent unlock

complete -c otp-local -f

# Main commands
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a doctor -d "Inspect system tools and non-authenticating capabilities"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a tui -d "Launch interactive Textual TUI dashboard"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a guide -d "Display bundled operator markdown guides"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a show -d "Output OTP decimal code to terminal"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a copy -d "Copy OTP code to desktop clipboard"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a select -d "Interactively select and retrieve item"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a enroll -d "Enroll new OTP secret or QR code"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a pick -d "Launch desktop quick-picker (wofi/rofi/fzf)"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a import -d "Import OTP credentials from external backups"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a export -d "Export OTP credentials for offline backup or GPG encryption"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a audit -d "Audit stored tokens for duplicate seeds and vulnerabilities"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a qr -d "Display terminal UTF-8 QR code for phone scanning"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a agent -d "Manage background session agent daemon"
complete -c otp-local -n "not __fish_seen_subcommand_from $commands" -a unlock -d "Interactively authenticate or unlock 1Password CLI session"

# doctor options
complete -c otp-local -n "__fish_seen_subcommand_from doctor" -l json -d "Emit machine-readable JSON capability report"

# guide options
complete -c otp-local -n "__fish_seen_subcommand_from guide" -a "optional setup acceptance migration recovery tui"

# pick options
complete -c otp-local -n "__fish_seen_subcommand_from pick" -l launcher -a "auto wofi rofi fzf" -d "Desktop picker binary"
complete -c otp-local -n "__fish_seen_subcommand_from pick" -l no-notify -d "Suppress desktop notification"
complete -c otp-local -n "__fish_seen_subcommand_from pick" -l stdout -d "Output code directly to stdout"

# import options
complete -c otp-local -n "__fish_seen_subcommand_from import" -l format -a "auto aegis bitwarden google-migration uri-list" -d "Import serialization format"
complete -c otp-local -n "__fish_seen_subcommand_from import" -l dry-run -d "Preview tokens without saving"
complete -c otp-local -n "__fish_seen_subcommand_from import" -l apply -d "Commit imported tokens to backend"

# export options
complete -c otp-local -n "__fish_seen_subcommand_from export" -l format -a "uri aegis csv" -d "Export serialization format"
complete -c otp-local -n "__fish_seen_subcommand_from export" -l output -F -d "Destination file (enforced 0600 mode)"
complete -c otp-local -n "__fish_seen_subcommand_from export" -l encrypt-gpg -d "Recipient GPG key ID"
complete -c otp-local -n "__fish_seen_subcommand_from export" -l stdout -d "Output export directly to stdout"

# audit options
complete -c otp-local -n "__fish_seen_subcommand_from audit" -l json -d "Emit machine-readable JSON security report"

# qr options
complete -c otp-local -n "__fish_seen_subcommand_from qr" -l allow-pipe -d "Allow outputting QR code to pipeline"

# agent options
complete -c otp-local -n "__fish_seen_subcommand_from agent" -a "status start stop lock"
complete -c otp-local -n "__fish_seen_subcommand_from agent" -l timeout -d "Idle auto-lock timeout in seconds"

# unlock options
complete -c otp-local -n "__fish_seen_subcommand_from unlock" -l account -d "1Password account shorthand or ID"

# Shared backend flags
for cmd in show copy select enroll pick import export audit qr
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l backend -a "onepassword pass-otp totpm yubikey tpm2-totp"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l account -d "1Password account ID or totpm account"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l vault -d "1Password vault ID"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l store -d "pass-otp password store path"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l key-home -d "pass-otp GNUPGHOME path"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l entry -d "pass-otp entry path"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l config -d "totpm config file path"
    complete -c otp-local -n "__fish_seen_subcommand_from $cmd" -l service -d "totpm service name"
end
