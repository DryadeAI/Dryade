---
title: Settings
sidebar_position: 6
---

# Settings

The Settings page is where you manage LLM providers, API keys, MCP servers, and your personal preferences. You can access it from the sidebar at any time.

![Settings page showing LLM provider cards for OpenAI, Anthropic, and local vLLM with connection status](/img/screenshots/settings-page.png)

## LLM Provider Configuration

### Adding a Provider

1. Go to **Settings > LLM Providers**
2. Click **Add Provider**
3. Select the provider type (OpenAI, Anthropic, Google, vLLM, or OpenAI-compatible)
4. Enter your API key or endpoint URL
5. Click **Test Connection** to verify
6. Save the configuration

### Managing Providers

You can configure multiple providers simultaneously:

| Action | How |
|--------|-----|
| **Switch default model** | Select a different model from the provider's model list |
| **Edit API key** | Click the provider entry and update the key |
| **Remove a provider** | Click the delete button on the provider entry |
| **Test connection** | Click Test to verify the provider is reachable |

### Supported Providers

| Provider | What you need |
|----------|---------------|
| **OpenAI** | API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| **Anthropic** | API key from [console.anthropic.com](https://console.anthropic.com/) |
| **Google** | API key from [aistudio.google.com](https://aistudio.google.com/) |
| **Local vLLM** | Endpoint URL (e.g., `http://localhost:8080/v1`) |
| **OpenAI-compatible** | Base URL + API key for any compatible endpoint |

You can use multiple providers at the same time and switch between models in the [Chat](/using-dryade/chat) interface.

## API Key Management

API keys are stored encrypted in your Dryade database. They are only sent to the corresponding LLM provider when making requests.

### Security Notes

- Keys are never exposed in the UI after initial entry
- Keys are stored with encryption at rest
- Each key is only used for its designated provider
- You can rotate keys at any time by editing the provider configuration

### Rotating a Key

1. Generate a new key from your provider's dashboard
2. Go to Settings > LLM Providers
3. Edit the provider entry
4. Replace the old key with the new one
5. Test the connection
6. Save

The old key can then be revoked from the provider's dashboard.

## MCP Server Management

Configure which MCP tool servers are available to agents.

### Enabling Servers

1. Go to **Settings > MCP Servers**
2. Toggle servers on or off
3. For servers that need credentials (GitHub, Linear), enter the required API keys
4. Changes take effect immediately

### Server Status

The MCP Servers section shows the status of each configured server:

| Status | Meaning |
|--------|---------|
| **Running** | Server is active and tools are available |
| **Stopped** | Server is disabled or not started |
| **Error** | Server encountered an issue (check logs) |

You can restart individual servers from this page if they stop responding.

For detailed information about each MCP server, see the [MCP Servers](/using-dryade/mcp) page.

## Theme and Preferences

Customize the Dryade interface to your liking:

### Appearance

- **Dark mode** -- The default theme, optimized for extended use
- **Light mode** -- A bright theme for well-lit environments
- **System** -- Automatically match your operating system preference

### Display Preferences

- **Language** -- Interface language setting
- **Notification preferences** -- Configure which notifications you receive

## User Profile

Manage your account information:

- **Name** -- Your display name shown in conversations and the UI
- **Email** -- Your login email address
- **Password** -- Change your account password
- **MFA** -- Enable or disable multi-factor authentication (TOTP)

### Multi-Factor Authentication

For additional account security, enable TOTP-based MFA:

1. Go to **Settings > Security**
2. Click **Enable MFA**
3. Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.)
4. Enter the verification code to confirm
5. Save your recovery codes in a secure location

Once enabled, you will need both your password and a TOTP code to log in.

## Deferred Onboarding Steps

If you skipped any optional steps during the [onboarding wizard](/getting-started/onboarding-guide), you can complete them here:

| Skipped Step | Where to configure |
|-------------|-------------------|
| Additional LLM providers | Settings > LLM Providers |
| MCP servers | Settings > MCP Servers |
| Preferences | Settings > Preferences |

Everything that the onboarding wizard offers is also available through Settings, so there is no need to run the wizard again.

## Tips

- **Test connections after adding or changing keys.** The Test Connection button verifies that your key is valid and the provider is reachable before you rely on it.
- **Keep API keys rotated.** If a key may have been compromised, rotate it immediately from both the provider dashboard and Dryade Settings.
- **Enable MCP servers as needed.** You do not need to enable everything at once. Start with the servers relevant to your current work and add more later.
- **Use dark mode for extended sessions.** It reduces eye strain during long work sessions.
