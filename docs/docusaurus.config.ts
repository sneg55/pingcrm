import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'PingCRM',
  tagline: 'AI-powered personal networking CRM',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://docs.pingcrm.xyz',
  baseUrl: '/',

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/sneg55/pingcrm/tree/main/docs/',
          routeBasePath: '/',
        },
        blog: false,
        gtag: {
          trackingID: 'G-WVR19X9096',
          anonymizeIP: true,
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        indexBlog: false,
        docsRouteBasePath: '/',
        highlightSearchTermsOnTargetPage: true,
      },
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'PingCRM',
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://pingcrm.xyz',
          label: 'Waitlist',
          position: 'right',
        },
        {
          href: 'https://github.com/sneg55/pingcrm',
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
            { label: 'Getting Started', to: '/setup' },
            { label: 'Architecture', to: '/architecture' },
          ],
        },
        {
          title: 'Features',
          items: [
            { label: 'Contacts', to: '/features/contacts' },
            { label: 'Suggestions', to: '/features/suggestions' },
            { label: 'Organizations', to: '/features/organizations' },
          ],
        },
        {
          title: 'Integrations',
          items: [
            { label: 'Gmail', to: '/features/gmail' },
            { label: 'Telegram', to: '/features/telegram' },
            { label: 'Twitter/X', to: '/features/twitter' },
          ],
        },
        {
          title: 'Community',
          items: [
            { label: 'Contributing', to: '/contributing' },
            { label: 'GitHub', href: 'https://github.com/sneg55/pingcrm' },
            { label: 'Waitlist (Hosted)', href: 'https://pingcrm.xyz' },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} PingCRM. Licensed under AGPL-3.0.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'python', 'sql'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
