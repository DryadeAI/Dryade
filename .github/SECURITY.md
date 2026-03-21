# Security Policy

## Reporting a Vulnerability

Report security vulnerabilities to: **security@dryade.ai**

PGP key available on request. Include "SECURITY" in the subject line for faster routing.

**Please do not open a public GitHub issue for security vulnerabilities.**

## Response Timeline

| Stage | Target |
|---|---|
| Acknowledgement | 72 hours |
| Severity assessment | 7 days |
| Fix (Critical, CVSS 9.0-10.0) | 30 days |
| Fix (High, CVSS 7.0-8.9) | 60 days |
| Fix (Medium, CVSS 4.0-6.9) | 90 days |
| Fix (Low, CVSS 0.1-3.9) | Best effort |

## Disclosure Process

1. **Report** -- Send details to security@dryade.ai (description, reproduction steps, impact assessment)
2. **Acknowledgement** -- We confirm receipt within 72 hours
3. **Assessment** -- We assess severity and assign a CVE if warranted (within 7 days)
4. **Fix** -- We develop and test a patch within the SLA for the severity level
5. **Coordinated disclosure** -- We coordinate release timing with the reporter
6. **Patch release** -- Fix is released and announced
7. **Credit** -- Reporter credited in release notes (unless anonymity requested)

## Scope

**In scope:**
- Dryade core API
- Plugin system and plugin loader
- Authentication and authorization logic
- Infrastructure configuration files
- Frontend application

**Out of scope:**
- Third-party dependencies (report directly to upstream maintainers)
- Social engineering attacks
- Physical security
- Denial of service via resource exhaustion (unless bypassing rate limits)

## Safe Harbor

We will not pursue legal action against researchers who:
- Disclose vulnerabilities to us before public disclosure
- Do not access, modify, or delete user data
- Do not disrupt service availability
- Act in good faith throughout the process
