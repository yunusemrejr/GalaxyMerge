import re
from pathlib import Path
from typing import Any

SENSITIVE_PATTERNS: list[str] = [
    r"api_key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"api_token\s*[:=]\s*['\"][^'\"]+['\"]",
    r"sk-[a-zA-Z0-9]{20,}(?:[^a-zA-Z0-9]|$)",
    r"AKIA[0-9A-Z]{16}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"github_pat_[a-zA-Z0-9]{36}",
    r"gho_[a-zA-Z0-9]{36}",
    r"ghu_[a-zA-Z0-9]{36}",
    r"ghr_[a-zA-Z0-9]{36}",
    r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
    r"token\s*[:=]\s*['\"][^'\"]+['\"]",
    r"password\s*[:=]\s*['\"][^'\"]+['\"]",
    r"secret\s*[:=]\s*['\"][^'\"]+['\"]",
    r"access_key_id\s*[:=]\s*['\"][^'\"]+['\"]",
    r"secret_access_key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}",
    r"sk_live_[a-zA-Z0-9]{24,}",
    r"sk_test_[a-zA-Z0-9]{24,}",
    r"rk_live_[a-zA-Z0-9]{24,}",
    r"rk_test_[a-zA-Z0-9]{24,}",
    r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
    r"xox[bpsar]-[a-zA-Z0-9-]+",
    r"xoxa-[a-zA-Z0-9-]+",
    r"https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[a-zA-Z0-9]+",
    r"pypi-[a-zA-Z0-9]{60,}",
    r"AC[a-f0-9]{32}",
    r"[a-f0-9]{32}@project\.appspot\.com",
]

SENSITIVE_PATH_PARTS: list[str] = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.staging",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "token.json",
    "token.yaml",
    "tokens.json",
    ".ssh/",
    ".aws/",
    ".gnupg/",
    ".docker/",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "*.pem",
    "*.key",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".gitconfig",
    "service-account-key",
    "kubeconfig",
    ".kube/config",
    ".azure/",
    "*.p12",
    "*.pfx",
    "htpasswd",
    "shadow",
    ".vault-token",
    ".terraform.rc",
]

ENV_VAR_PATTERN = re.compile(
    r"\$\{?(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|"
    r"DEEPSEEK_API_KEY|OPENROUTER_API_KEY|NVIDIA_API_KEY|OLLAMA_API_KEY|"
    r"MINIMAX_API_KEY|STEPFUN_API_KEY|STREAMLAKE_API_KEY|KIMI_API_KEY|"
    r"GITHUB_TOKEN|GH_TOKEN|AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|"
    r"DIGITALOCEAN_TOKEN|HUGGINGFACE_TOKEN|REPLICATE_API_TOKEN|"
    r"AZURE_CLIENT_SECRET|AZURE_TENANT_ID|GOOGLE_APPLICATION_CREDENTIALS|"
    r"FIREBASE_TOKEN|NPM_TOKEN|PYPI_TOKEN|SLACK_TOKEN|"
    r"STRIPE_SECRET_KEY|STRIPE_PUBLISHABLE_KEY|"
    r"SENDGRID_API_KEY|TWILIO_AUTH_TOKEN|TWILIO_ACCOUNT_SID)\}?"
)

# Also catch bare env-var-style assignments like OPENAI_API_KEY=sk-...
ENV_ASSIGN_PATTERN = re.compile(
    r"(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY|"
    r"DEEPSEEK_API_KEY|OPENROUTER_API_KEY|NVIDIA_API_KEY|OLLAMA_API_KEY|"
    r"MINIMAX_API_KEY|STEPFUN_API_KEY|STREAMLAKE_API_KEY|KIMI_API_KEY|"
    r"GITHUB_TOKEN|GH_TOKEN|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|"
    r"DIGITALOCEAN_TOKEN|HUGGINGFACE_TOKEN|REPLICATE_API_TOKEN|"
    r"AZURE_CLIENT_SECRET|AZURE_TENANT_ID|GOOGLE_APPLICATION_CREDENTIALS|"
    r"FIREBASE_TOKEN|NPM_TOKEN|PYPI_TOKEN|SLACK_TOKEN|"
    r"STRIPE_SECRET_KEY|STRIPE_PUBLISHABLE_KEY|"
    r"SENDGRID_API_KEY|TWILIO_AUTH_TOKEN|TWILIO_ACCOUNT_SID)"
    r"\s*=\s*\S+"
)

ENV_NAME_MAP = {
    "OPENAI_API_KEY": "sk-...",
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "GOOGLE_API_KEY": "AIza...",
    "DEEPSEEK_API_KEY": "sk-...",
    "GEMINI_API_KEY": "AIza...",
    "OPENROUTER_API_KEY": "sk-or-...",
    "NVIDIA_API_KEY": "nvapi-...",
    "OLLAMA_API_KEY": "ollama-...",
    "MINIMAX_API_KEY": "sk-...",
    "STEPFUN_API_KEY": "sk-...",
    "STREAMLAKE_API_KEY": "sk-...",
    "KIMI_API_KEY": "sk-...",
    "GITHUB_TOKEN": "ghp_...",
    "GH_TOKEN": "ghp_...",
    "AWS_SECRET_ACCESS_KEY": "AKIA...",
    "AWS_ACCESS_KEY_ID": "AKIA...",
    "AZURE_CLIENT_SECRET": "***...",
    "AZURE_TENANT_ID": "***...",
    "GOOGLE_APPLICATION_CREDENTIALS": "path/to/sa.json",
    "FIREBASE_TOKEN": "***...",
    "NPM_TOKEN": "npm_...",
    "PYPI_TOKEN": "pypi-...",
    "SLACK_TOKEN": "xoxb-...",
    "STRIPE_SECRET_KEY": "sk_live_...",
    "STRIPE_PUBLISHABLE_KEY": "pk_live_...",
    "SENDGRID_API_KEY": "SG....",
    "TWILIO_AUTH_TOKEN": "***...",
    "TWILIO_ACCOUNT_SID": "AC...",
}


class CredentialPolicy:
    def __init__(self, workroot: Path):
        self.workroot = workroot.resolve()

    def check_path(self, path: Path) -> dict[str, Any]:
        resolved_str = str(path.resolve())
        workroot_str = str(self.workroot) + "/"

        if not resolved_str.startswith(workroot_str):
            return {"decision": "block", "reason": "path outside WorkRoot"}

        path_lower = resolved_str.lower()
        for part in SENSITIVE_PATH_PARTS:
            if part.startswith("*."):
                ext = part[1:]
                if path_lower.endswith(ext):
                    return {
                        "decision": "block",
                        "reason": f"sensitive file extension: {part}",
                    }
            elif part in path_lower:
                return {
                    "decision": "block",
                    "reason": f"sensitive file pattern: {part}",
                }

        return {"decision": "allow", "reason": "not a credential path"}

    def scan_text(self, text: str) -> list[dict[str, Any]]:
        findings = []
        for pattern in SENSITIVE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                findings.append(
                    {
                        "pattern": pattern,
                        "start": m.start(),
                        "end": m.end(),
                        "decision": "redact",
                    }
                )

        env_matches = ENV_VAR_PATTERN.finditer(text)
        for m in env_matches:
            var_name = m.group(1) or m.group(2)
            if var_name:
                findings.append(
                    {
                        "pattern": f"env_var:{var_name}",
                        "start": m.start(),
                        "end": m.end(),
                        "decision": "redact",
                        "note": f"environment variable reference: {var_name}",
                    }
                )

        assign_matches = ENV_ASSIGN_PATTERN.finditer(text)
        for m in assign_matches:
            var_name = m.group(1)
            findings.append(
                {
                    "pattern": f"env_assign:{var_name}",
                    "start": m.start(),
                    "end": m.end(),
                    "decision": "redact",
                    "note": f"environment variable assignment: {var_name}",
                }
            )

        return findings

    def redact(self, text: str) -> str:
        for pattern in SENSITIVE_PATTERNS:
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)

        def redact_env_var(m: re.Match) -> str:
            var_name = m.group(1)
            return m.group(0)[: min(4, len(m.group(0)))] + f"***{var_name}***"

        text = ENV_VAR_PATTERN.sub(redact_env_var, text)

        def redact_env_assign(m: re.Match) -> str:
            var_name = m.group(1)
            return f"{var_name}=***REDACTED***"

        text = ENV_ASSIGN_PATTERN.sub(redact_env_assign, text)

        return text


def redact_text(text: str) -> str:
    """Redact credential-shaped values from text without requiring a WorkRoot."""
    return CredentialPolicy(Path.cwd()).redact(text)
