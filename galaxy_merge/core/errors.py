class GalaxyMergeError(Exception):
    pass


class SafetyBlocked(GalaxyMergeError):
    def __init__(self, message: str, decision: str = "block"):
        self.decision = decision
        super().__init__(message)


class ToolError(GalaxyMergeError):
    pass


class ProviderError(GalaxyMergeError):
    pass


class SessionError(GalaxyMergeError):
    pass


class ConfigError(GalaxyMergeError):
    pass
