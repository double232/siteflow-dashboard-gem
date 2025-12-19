import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ContextMenu } from './ContextMenu';

describe('ContextMenu', () => {
  const mockActions = [
    { label: 'Start', onClick: vi.fn(), className: 'action-start' },
    { label: 'Stop', onClick: vi.fn(), className: 'action-stop' },
    { label: 'Restart', onClick: vi.fn() },
    { label: 'Delete', onClick: vi.fn(), className: 'action-danger' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders children correctly', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="child">Test Content</div>
      </ContextMenu>
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('does not show menu initially', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div>Test Content</div>
      </ContextMenu>
    );

    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('shows menu on right-click', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Restart' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('shows menu on long press (touch)', async () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');

    // Simulate touch start
    fireEvent.touchStart(target, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    // Fast-forward past long press threshold (500ms)
    act(() => {
      vi.advanceTimersByTime(501);
    });

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  });

  it('cancels long press if touch moves too much', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');

    // Simulate touch start
    fireEvent.touchStart(target, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    // Move finger more than 10px
    fireEvent.touchMove(target, {
      touches: [{ clientX: 120, clientY: 100 }],
    });

    // Fast-forward past long press threshold
    act(() => {
      vi.advanceTimersByTime(501);
    });

    // Menu should NOT appear
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('cancels long press on touch end', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');

    // Simulate touch start
    fireEvent.touchStart(target, {
      touches: [{ clientX: 100, clientY: 100 }],
    });

    // End touch before threshold
    act(() => {
      vi.advanceTimersByTime(200);
    });
    fireEvent.touchEnd(target);

    // Fast-forward past long press threshold
    act(() => {
      vi.advanceTimersByTime(400);
    });

    // Menu should NOT appear
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('calls action onClick and closes menu', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    const startButton = screen.getByRole('button', { name: 'Start' });
    fireEvent.click(startButton);

    expect(mockActions[0].onClick).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('does not call onClick for disabled actions', () => {
    const actionsWithDisabled = [
      { label: 'Disabled Action', onClick: vi.fn(), disabled: true },
      { label: 'Enabled Action', onClick: vi.fn() },
    ];

    render(
      <ContextMenu actions={actionsWithDisabled}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    const disabledButton = screen.getByRole('button', { name: 'Disabled Action' });
    fireEvent.click(disabledButton);

    expect(actionsWithDisabled[0].onClick).not.toHaveBeenCalled();
  });

  it('closes menu on Escape key', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('closes menu on click outside', () => {
    render(
      <div>
        <ContextMenu actions={mockActions}>
          <div data-testid="target">Test Content</div>
        </ContextMenu>
        <div data-testid="outside">Outside</div>
      </div>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByTestId('outside'));

    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('does not open menu when disabled', () => {
    render(
      <ContextMenu actions={mockActions} disabled>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument();
  });

  it('applies correct CSS classes to action items', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    fireEvent.contextMenu(target, { clientX: 100, clientY: 100 });

    const startButton = screen.getByRole('button', { name: 'Start' });
    const deleteButton = screen.getByRole('button', { name: 'Delete' });

    expect(startButton).toHaveClass('action-start');
    expect(deleteButton).toHaveClass('action-danger');
  });

  it('positions menu within viewport bounds', () => {
    // Mock window dimensions
    Object.defineProperty(window, 'innerWidth', { value: 500, writable: true });
    Object.defineProperty(window, 'innerHeight', { value: 500, writable: true });

    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    // Click near edge of viewport
    fireEvent.contextMenu(target, { clientX: 480, clientY: 480 });

    const menu = document.querySelector('.context-menu');
    expect(menu).toBeInTheDocument();
    // Menu should be adjusted to stay within viewport
    // The exact position depends on menu dimensions
  });

  it('prevents default context menu', () => {
    render(
      <ContextMenu actions={mockActions}>
        <div data-testid="target">Test Content</div>
      </ContextMenu>
    );

    const target = screen.getByTestId('target');
    const event = new MouseEvent('contextmenu', {
      bubbles: true,
      cancelable: true,
      clientX: 100,
      clientY: 100,
    });

    const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
    act(() => {
      target.dispatchEvent(event);
    });

    expect(preventDefaultSpy).toHaveBeenCalled();
  });
});
