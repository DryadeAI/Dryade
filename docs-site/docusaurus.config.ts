import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import type * as OpenApiPlugin from 'docusaurus-plugin-openapi-docs';

const config: Config = {
  title: 'Dryade Documentation',
  tagline: 'Self-hosted AI orchestration with full data sovereignty',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://docs.dryade.ai',
  baseUrl: '/',

  organizationName: 'DryadeAI',
  projectName: 'Dryade',

  onBrokenLinks: 'warn',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
      onBrokenMarkdownImages: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          docItemComponent: '@theme/ApiItem',
          editUrl: 'https://github.com/DryadeAI/Dryade/tree/main/docs-site/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      'docusaurus-plugin-openapi-docs',
      {
        id: 'api',
        docsPluginId: 'default',
        config: {
          community: {
            specPath: 'openapi/openapi-community.json',
            outputDir: 'docs/developer-guide/api',
            sidebarOptions: {
              groupPathsBy: 'tag',
              categoryLinkSource: 'tag',
            },
          } satisfies OpenApiPlugin.Options,
        },
      },
    ],
  ],

  themes: [
    'docusaurus-theme-openapi-docs',
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexBlog: false,
        docsRouteBasePath: '/',
      },
    ],
  ],

  themeConfig: {
    image: 'img/dryade-social-card.png',
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Dryade',
      logo: {
        alt: 'Dryade Logo',
        src: 'img/dryade-logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'gettingStarted',
          position: 'left',
          label: 'Getting Started',
        },
        {
          type: 'docSidebar',
          sidebarId: 'usingDryade',
          position: 'left',
          label: 'Using Dryade',
        },
        {
          type: 'docSidebar',
          sidebarId: 'developerGuide',
          position: 'left',
          label: 'Developer Guide',
        },
        {
          type: 'docSidebar',
          sidebarId: 'pluginDevelopment',
          position: 'left',
          label: 'Plugin Dev',
        },
        {
          type: 'docSidebar',
          sidebarId: 'reference',
          position: 'left',
          label: 'Reference',
        },
        {
          href: 'https://github.com/DryadeAI/Dryade',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {label: 'Getting Started', to: '/getting-started/installation'},
            {label: 'API Reference', to: '/developer-guide/authentication'},
            {label: 'Plugin Development', to: '/plugin-development/structure'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'Website', href: 'https://dryade.ai'},
            {label: 'GitHub', href: 'https://github.com/DryadeAI/Dryade'},
            {label: 'License (DSUL)', to: '/reference/license'},
          ],
        },
      ],
      copyright: `Copyright ${new Date().getFullYear()} Dryade. Licensed under DSUL.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'typescript', 'yaml', 'toml'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
