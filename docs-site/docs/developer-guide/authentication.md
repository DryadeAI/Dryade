---
title: Authentication
sidebar_position: 1
---

# Authentication

Dryade uses **JWT-based authentication** with httpOnly cookies for session management. This page covers how to register, log in, refresh tokens, and authenticate API requests.

## How Authentication Works

When a user logs in, Dryade issues a JSON Web Token (JWT) that is stored as an httpOnly cookie. This token is automatically sent with every request from the browser. For programmatic API access, you can also pass the token via the `Authorization` header.

**Authentication flow:**

1. Register or log in to receive a JWT
2. The token is set as an httpOnly cookie (browser) or returned in the response (API)
3. Include the token in subsequent requests
4. Refresh the token before it expires

## Registration

Create a new user account:

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-secure-password",
    "name": "Your Name"
  }'
```

**Response:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "name": "Your Name",
  "created_at": "2026-01-15T10:00:00Z"
}
```

## Login

Authenticate and receive a JWT:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-secure-password"
  }'
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1...",
  "token_type": "bearer"
}
```

The token is also set as an httpOnly cookie for browser-based access.

## Using Tokens in API Calls

### Browser (automatic)

If you logged in through the Dryade UI, the httpOnly cookie is sent automatically with every request. No additional setup is needed.

### Programmatic Access

For scripts, integrations, or external applications, include the token in the `Authorization` header:

```bash
curl http://localhost:8000/api/agents \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1..."
```

**JavaScript example:**

```javascript
const response = await fetch('http://localhost:8000/api/agents', {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
});

const agents = await response.json();
```

## Token Refresh

Tokens expire after a configured period. Refresh them before expiration to maintain your session:

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1..."
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1...(new token)",
  "token_type": "bearer"
}
```

**JavaScript refresh example:**

```javascript
async function refreshToken(currentToken) {
  const response = await fetch('http://localhost:8000/api/auth/refresh', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${currentToken}`,
    },
  });

  if (response.ok) {
    const data = await response.json();
    return data.access_token;
  }

  // Token expired or invalid -- redirect to login
  throw new Error('Token refresh failed');
}
```

## Error Responses

| Status | Meaning | Action |
|--------|---------|--------|
| `401 Unauthorized` | Token missing, expired, or invalid | Log in again or refresh the token |
| `403 Forbidden` | Valid token but insufficient permissions | Check your account tier and permissions |
| `422 Unprocessable Entity` | Invalid request body | Check required fields in the request |

## Multi-Factor Authentication (MFA)

Dryade supports optional TOTP-based multi-factor authentication. When MFA is enabled on an account, the login flow requires an additional verification step:

1. Submit credentials to `/api/auth/login`
2. If MFA is enabled, the response includes `mfa_required: true`
3. Submit the TOTP code to `/api/auth/mfa/verify` to complete authentication

MFA can be configured in **Settings > Security** within the Dryade UI.

## API Reference

The complete list of authentication endpoints and their parameters will be available in the auto-generated API Reference, built from the OpenAPI specification.

## Best Practices

- **Never store tokens in localStorage** -- use httpOnly cookies when possible
- **Refresh tokens proactively** -- refresh before expiration, not after a 401
- **Use HTTPS in production** -- tokens sent over HTTP can be intercepted
- **Rotate credentials** -- change passwords periodically and revoke unused tokens
