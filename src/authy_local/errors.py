"""Static diagnostics: external output must never become an error message."""

MESSAGES = {
    2: "Invalid command or scope. See --help.",
    3: "Required capability is unavailable or unsupported.",
    4: "Backend request failed. Check the native app privately.",
    5: "Backend response failed validation or exceeded a limit.",
    6: "Clipboard or selector operation failed.",
    7: "Operation exceeded its deadline.",
    130: "Operation cancelled.",
}


class AppError(Exception):
    def __init__(self, exit_code: int):
        self.exit_code = exit_code
        super().__init__(MESSAGES[exit_code])
