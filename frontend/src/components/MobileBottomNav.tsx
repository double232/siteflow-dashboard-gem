export type MobileTab = 'sites' | 'backups' | 'console' | 'settings';

interface Props {
  activeTab: MobileTab;
  onTabChange: (tab: MobileTab) => void;
  unreadConsoleCount?: number;
}

interface NavItem {
  id: MobileTab;
  icon: string;
  label: string;
}

const navItems: NavItem[] = [
  { id: 'sites', icon: '[=]', label: 'Sites' },
  { id: 'backups', icon: '[B]', label: 'Backups' },
  { id: 'console', icon: '[>_]', label: 'Console' },
  { id: 'settings', icon: '[*]', label: 'Settings' },
];

export const MobileBottomNav = ({ activeTab, onTabChange, unreadConsoleCount = 0 }: Props) => {
  return (
    <nav className="mobile-bottom-nav">
      <ul className="mobile-bottom-nav__items">
        {navItems.map((item) => (
          <li key={item.id}>
            <button
              className={`mobile-bottom-nav__item ${activeTab === item.id ? 'mobile-bottom-nav__item--active' : ''}`}
              onClick={() => onTabChange(item.id)}
              aria-label={item.label}
              aria-current={activeTab === item.id ? 'page' : undefined}
            >
              <span className="mobile-bottom-nav__icon">{item.icon}</span>
              <span className="mobile-bottom-nav__label">{item.label}</span>
              {item.id === 'console' && unreadConsoleCount > 0 && (
                <span className="mobile-bottom-nav__badge">
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
