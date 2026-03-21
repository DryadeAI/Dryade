import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  gettingStarted: [
    {
      type: 'doc',
      id: 'index',
      label: 'What is Dryade?',
    },
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/quick-start',
        'getting-started/onboarding-guide',
      ],
    },
  ],

  usingDryade: [
    {
      type: 'category',
      label: 'Using Dryade',
      collapsed: false,
      items: [
        'using-dryade/chat',
        'using-dryade/agents',
        'using-dryade/workflows',
        'using-dryade/knowledge',
        'using-dryade/mcp',
        'using-dryade/settings',
      ],
    },
  ],

  developerGuide: [
    {
      type: 'category',
      label: 'Developer Guide',
      collapsed: false,
      items: [
        'developer-guide/authentication',
        'developer-guide/websocket',
      ],
    },
  ],

  pluginDevelopment: [
    {
      type: 'category',
      label: 'Plugin Development',
      collapsed: false,
      items: [
        'plugin-development/structure',
        'plugin-development/manifest',
        'plugin-development/ui-sandbox',
        'plugin-development/testing',
        'plugin-development/publishing',
      ],
    },
  ],

  reference: [
    {
      type: 'category',
      label: 'Reference',
      collapsed: false,
      items: [
        'reference/license',
        'reference/tiers',
        'reference/changelog',
        'reference/troubleshooting',
      ],
    },
  ],

  community: [
    {
      type: 'category',
      label: 'Community',
      collapsed: false,
      items: [
        'community/index',
        'community/discord',
        'community/contributing',
        'community/examples',
      ],
    },
  ],
};

export default sidebars;
