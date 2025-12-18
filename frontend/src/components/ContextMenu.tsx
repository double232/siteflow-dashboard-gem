import { useEffect, useRef, useState, useCallback } from 'react';

interface MenuAction {
  label: string;
  onClick: () => void;
  className?: string;
  disabled?: boolean;
}

interface Props {
  actions: MenuAction[];
  children: React.ReactNode;
  disabled?: boolean;
}

export const ContextMenu = ({ actions, children, disabled = false }: Props) => {
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const menuRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const longPressTimer = useRef<number | null>(null);
  const touchStartPos = useRef<{ x: number; y: number } | null>(null);

  const openMenu = useCallback((x: number, y: number) => {
    if (disabled) return;

    // Adjust position to stay within viewport
    const menuWidth = 160;
    const menuHeight = actions.length * 44 + 16;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let adjustedX = x;
    let adjustedY = y;

    if (x + menuWidth > viewportWidth) {
      adjustedX = viewportWidth - menuWidth - 8;
    }
    if (y + menuHeight > viewportHeight) {
      adjustedY = viewportHeight - menuHeight - 8;
    }

    setPosition({ x: adjustedX, y: adjustedY });
    setIsOpen(true);
  }, [disabled, actions.length]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    openMenu(e.clientX, e.clientY);
  }, [openMenu]);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (disabled) return;
    const touch = e.touches[0];
    touchStartPos.current = { x: touch.clientX, y: touch.clientY };

    longPressTimer.current = window.setTimeout(() => {
      if (touchStartPos.current) {
        openMenu(touchStartPos.current.x, touchStartPos.current.y);
        // Vibrate for haptic feedback if supported
        if (navigator.vibrate) {
          navigator.vibrate(50);
        }
      }
    }, 500);
  }, [disabled, openMenu]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!touchStartPos.current || !longPressTimer.current) return;

    const touch = e.touches[0];
    const dx = Math.abs(touch.clientX - touchStartPos.current.x);
    const dy = Math.abs(touch.clientY - touchStartPos.current.y);

    // Cancel long press if moved more than 10px
    if (dx > 10 || dy > 10) {
      if (longPressTimer.current) {
        clearTimeout(longPressTimer.current);
        longPressTimer.current = null;
      }
    }
  }, []);

  const handleTouchEnd = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    touchStartPos.current = null;
  }, []);

  const handleActionClick = useCallback((action: MenuAction) => {
    if (action.disabled) return;
    setIsOpen(false);
    action.onClick();
  }, []);

  // Close menu on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isOpen]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (longPressTimer.current) {
        clearTimeout(longPressTimer.current);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className="context-menu-container"
      onContextMenu={handleContextMenu}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
    >
      {children}

      {isOpen && (
        <div
          ref={menuRef}
          className="context-menu"
          style={{ left: position.x, top: position.y }}
        >
          {actions.map((action, index) => (
            <button
              key={index}
              type="button"
              className={`context-menu__item ${action.className || ''} ${action.disabled ? 'context-menu__item--disabled' : ''}`}
              onClick={() => handleActionClick(action)}
              disabled={action.disabled}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
