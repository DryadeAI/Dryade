# Welcome to your Lovable project

## Project info

**URL**: https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID

## How can I edit this code?

There are several ways of editing your application.

**Use Lovable**

Simply visit the [Lovable Project](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and start prompting.

Changes made via Lovable will be committed automatically to this repo.

**Use your preferred IDE**

If you want to work locally using your own IDE, you can clone this repo and push changes. Pushed changes will also be reflected in Lovable.

The only requirement is having Node.js & npm installed - [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating)

Follow these steps:

```sh
# Step 1: Clone the repository using the project's Git URL.
git clone <YOUR_GIT_URL>

# Step 2: Navigate to the project directory.
cd <YOUR_PROJECT_NAME>

# Step 3: Install the necessary dependencies.
npm i

# Step 4: Start the development server with auto-reloading and an instant preview.
npm run dev
```

**Edit a file directly in GitHub**

- Navigate to the desired file(s).
- Click the "Edit" button (pencil icon) at the top right of the file view.
- Make your changes and commit the changes.

**Use GitHub Codespaces**

- Navigate to the main page of your repository.
- Click on the "Code" button (green button) near the top right.
- Select the "Codespaces" tab.
- Click on "New codespace" to launch a new Codespace environment.
- Edit files directly within the Codespace and commit and push your changes once you're done.

## What technologies are used for this project?

This project is built with:

- Vite
- TypeScript
- React
- shadcn-ui
- Tailwind CSS

## Internationalization (i18n)

This project uses **i18next + react-i18next** for full internationalization.

### Supported Languages

English (en), Français (fr), Español (es), Deutsch (de), Italiano (it), Português BR (pt-BR), 简体中文 (zh-CN), 日本語 (ja), 한국어 (ko), العربية (ar)

### File Structure

```
src/i18n/
  index.ts                    # i18next init & config
  locales/
    en/
      common.json             # Nav, buttons, generic labels
      auth.json               # Login/register strings
      settings.json           # Settings page strings
      dashboard.json          # Dashboard page strings
    fr/ ... (same structure per language)
```

### How to Add a New Language

1. Copy the `src/i18n/locales/en/` folder to `src/i18n/locales/<lang-code>/`
2. Translate all JSON values (keep keys unchanged)
3. Import the new files in `src/i18n/index.ts` and add to the `resources` object
4. Add the language to `supportedLanguages` array in `src/i18n/index.ts`
5. If the language is RTL, add its code to the `rtlLanguages` array

### How to Add New Keys

1. Add the key to `src/i18n/locales/en/<namespace>.json` first
2. Use `t('namespace:key')` in your component (e.g., `t('auth:login.title')`)
3. Add translations for other languages (missing keys fall back to English)

### Fallback Behavior

- If a key is missing in the active language, the English value is shown
- In development mode, missing keys are logged to the console as warnings
- Browser language is auto-detected on first visit; chosen language is persisted in localStorage

### RTL Support

Arabic (`ar`) automatically sets `dir="rtl"` on the `<html>` element. Use Tailwind's `rtl:` variant for any RTL-specific overrides.

### Translation Quality Note

All non-English translations are best-effort and should be reviewed by a native speaker.

## How can I deploy this project?

Simply open [Lovable](https://lovable.dev/projects/REPLACE_WITH_PROJECT_ID) and click on Share -> Publish.

## Can I connect a custom domain to my Lovable project?

Yes, you can!

To connect a domain, navigate to Project > Settings > Domains and click Connect Domain.

Read more here: [Setting up a custom domain](https://docs.lovable.dev/features/custom-domain#custom-domain)
