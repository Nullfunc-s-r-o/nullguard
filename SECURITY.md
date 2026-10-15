# Security Policy

Nullfunc s.r.o. takes the security of **NullGuard** and its users seriously. If you discover a security vulnerability, we appreciate your cooperation in responsibly disclosing it to us.

---

## Supported Versions

Only the latest stable release receives active security patches.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

---

## Reporting a Vulnerability

**Please do NOT file public GitHub issues for security vulnerabilities.**

Instead, report security concerns directly and privately to our security team:

📧 **Email:** [contact@nullfunc.com](mailto:contact@nullfunc.com)  
🔒 **Subject:** `[SECURITY] Vulnerability Report: NullGuard`

### What to Include in Your Report

To help us triage and resolve the issue quickly, please provide:
1. **Description:** A detailed explanation of the issue and potential security impact.
2. **Reproduction Steps:** Step-by-step instructions or a Minimal Reproducible Example (Proof-of-Concept).
3. **Affected Versions & Environment:** Operating system, Python version, C++ compiler, and deployment method (Native or Docker).
4. **Suggested Mitigation (Optional):** Any potential patch, fix, or remediation you have identified.

---

## Response Timeline & Disclosure Policy

- **Initial Response:** We will acknowledge receipt of your vulnerability report within **48 hours**.
- **Assessment & Triage:** We will assess the severity and impact, providing updates as we investigate.
- **Resolution & Release:** Once verified, we will develop and test a security fix, releasing a patched version promptly.
- **Coordinated Disclosure:** We kindly request that you maintain confidentiality until an official fix and advisory are published.

---

## Operational Security Recommendations

When deploying NullGuard in production:

1. **API Keys & Credentials:** Never commit API keys or webhook URLs to version control. Pass them through environment variables (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, etc.) as documented in the README.
2. **Docker Socket Access:** When running in Docker, ensure `/var/run/docker.sock` is mounted strictly in read-only mode (`:ro`), as configured by default in `docker-compose.yml`.
3. **Database & Configuration File Permissions:** Ensure your `~/.nullguard/` directory, `config.yaml`, and `nullguard_state.db` have restrictive POSIX permissions (`chmod 600`) to prevent unauthorized local reading of notification targets.
