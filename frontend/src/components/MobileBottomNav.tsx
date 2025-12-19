import type { ReactNode } from 'react';

export type MobileTab = 'sites' | 'backups' | 'console' | 'settings';

interface Props {
  activeTab: MobileTab;
  onTabChange: (tab: MobileTab) => void;
  unreadConsoleCount?: number;
}

interface NavItem {
  id: MobileTab;
  icon: ReactNode;
  label: string;
}

const navItems: NavItem[] = [
  {
    id: 'sites',
    label: 'Sites',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="mobile-bottom-nav__icon-svg" fill="none" stroke="currentColor" strokeWidth="1.6">
        <rect x="4" y="4" width="6" height="6" rx="1.5" />
        <rect x="14" y="4" width="6" height="6" rx="1.5" />
        <rect x="4" y="14" width="6" height="6" rx="1.5" />
        <rect x="14" y="14" width="6" height="6" rx="1.5" />
      </svg>
    ),
  },
  {
    id: 'backups',
    label: 'Backups',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="mobile-bottom-nav__icon-svg" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M12 5v5l3-3m-3 3-3-3" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M6 12a6 6 0 1 0 6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'console',
    label: 'Console',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="mobile-bottom-nav__icon-svg" fill="none" stroke="currentColor" strokeWidth="1.6">
        <polyline points="5 7 10 12 5 17" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="17" x2="19" y2="17" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className="mobile-bottom-nav__icon-svg" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />
        <path d="M19.4 12a7.4 7.4 0 0 0-.09-1.12l2.11-1.65-2-3.46-2.5 1a7.4 7.4 0 0 0-1.94-1.12l-.38-2.65h-4l-.39 2.64a7.4 7.4 0 0 0-1.94 1.13l-2.5-1-2 3.46 2.11 1.65A7.5 7.5 0 0 0 4.6 12c0 .38.03.75.09 1.12L2.58 14.8l2 3.46 2.5-1a7.4 7.4 0 0 0 1.94 1.12l.39 2.62h4l.38-2.64a7.4 7.4 0 0 0 1.94-1.12l2.5 1 2-3.46-2.11-1.65c.06-.37.09-.74.09-1.13Z" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

export const MobileBottomNav = ({ activeTab, onTabChange, unreadConsoleCount = 0 }: Props) => {
  return (
    <nav className="mobile-bottom-nav" aria-label="Primary">
      <ul className="mobile-bottom-nav__items">
        {navItems.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={`mobile-bottom-nav__item ${activeTab === item.id ? 'mobile-bottom-nav__item--active' : ''}`}
              onClick={() => onTabChange(item.id)}
              aria-label={item.label}
              aria-current={activeTab === item.id ? 'page' : undefined}
            >
              <span className="mobile-bottom-nav__icon" aria-hidden="true">{item.icon}</span>
              <span className="mobile-bottom-nav__label">{item.label}</span>
              {item.id === 'console' && unreadConsoleCount > 0 && (
                <span className="mobile-bottom-nav__badge" aria-live="polite">
                  {unreadConsoleCount > 99 ? '99+' : unreadConsoleCount}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
};
