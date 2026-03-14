import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    'setup',
    'architecture',
    {
      type: 'category',
      label: 'Features',
      collapsed: false,
      items: [
        'features/dashboard',
        'features/contacts',
        'features/suggestions',
        'features/organizations',
        'features/identity',
        'features/notifications',
        'features/settings',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      collapsed: false,
      items: [
        'features/gmail',
        'features/telegram',
        'features/twitter',
      ],
    },
    'api-reference',
  ],
};

export default sidebars;
