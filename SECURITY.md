# Security Policy

Dryade takes security seriously. We appreciate the security community's
efforts in responsibly disclosing vulnerabilities.

## Supported Versions

| Version       | Supported          |
| ------------- | ------------------ |
| v1.0.0-beta   | :white_check_mark: |
| < v1.0.0-beta | :x:                |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, report vulnerabilities by emailing: **security@dryade.ai**

Include "SECURITY" in the subject line for faster routing.

### What to Include

- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Any suggested remediation (optional)

### Response Timeline

| Stage                | Target       |
| -------------------- | ------------ |
| Acknowledgment       | 48 hours     |
| Initial assessment   | 7 days       |
| Fix (Critical)       | 30 days      |
| Fix (High)           | 60 days      |
| Fix (Medium/Low)     | 90 days      |

## Scope

### In Scope

- Dryade core application and API
- Authentication and authorization logic
- Plugin system and plugin loader
- Infrastructure configuration
- Web interface (workbench)

### Out of Scope

- Third-party dependencies (report directly to upstream maintainers)
- Social engineering attacks
- Physical security
- Denial of service via resource exhaustion (unless bypassing rate limits)
- Issues in unsupported or end-of-life versions

## Disclosure Policy

We follow a coordinated disclosure process:

1. **Report** -- Send details to security@dryade.ai
2. **Acknowledgment** -- We confirm receipt within 48 hours
3. **Assessment** -- We assess severity and assign a CVE if warranted (within 7 days)
4. **Fix** -- We develop and test a patch within the SLA for the severity level
5. **Coordinated release** -- We coordinate timing with the reporter
6. **Patch release** -- Fix is released and announced
7. **CVE publication** -- CVE ID assigned and published (if applicable)
8. **Credit** -- Reporter credited in release notes (with permission)

We request a maximum 90-day disclosure window from the date of report to
allow sufficient time for remediation.

## PGP Key

For encrypted communications, use our PGP key:

- **Fingerprint:** `36DC 5EEF AA04 D129 7EC8 4978 2140 521C 8BC6 4275`
- **Key server:** [keys.openpgp.org](https://keys.openpgp.org/search?q=security%40dryade.ai)
- **Algorithm:** RSA 4096-bit, expires 2028-03-14

## GitHub Security Advisories

We use [GitHub Security Advisories](https://github.com/DryadeAI/Dryade/security/advisories)
to manage and disclose vulnerabilities. If you prefer, you can also report
through GitHub's private vulnerability reporting feature.

## Safe Harbor

We will not pursue legal action against security researchers who:

- Disclose vulnerabilities to us before public disclosure
- Do not access, modify, or delete user data
- Do not disrupt service availability
- Act in good faith throughout the process

## Credit

We believe in recognizing the contributions of security researchers.
With your permission, we will credit you in our release notes and
security advisories.

## Contact

- Security reports: security@dryade.ai
- General inquiries: contact@dryade.ai
- Legal questions: legal@dryade.ai
