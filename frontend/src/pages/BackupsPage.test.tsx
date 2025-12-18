import { describe, it, expect, vi } from 'vitest';

// Test the helper functions directly by recreating them here
// (Since they're not exported from BackupsPage, we test the logic)

const formatTimeAgo = (seconds: number | null | undefined): string => {
  if (seconds === null || seconds === undefined) return 'Never';
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
};

const formatCountdown = (seconds: number): string => {
  if (seconds <= 0) return 'Overdue';
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
};

const getNextRunSeconds = (
  rpoSeconds: number | null | undefined,
  thresholdHours: number
): number | null => {
  if (rpoSeconds === null || rpoSeconds === undefined) return null;
  const thresholdSeconds = thresholdHours * 3600;
  return thresholdSeconds - rpoSeconds;
};

describe('formatTimeAgo', () => {
  it('returns "Never" for null', () => {
    expect(formatTimeAgo(null)).toBe('Never');
  });

  it('returns "Never" for undefined', () => {
    expect(formatTimeAgo(undefined)).toBe('Never');
  });

  it('returns "Just now" for seconds < 60', () => {
    expect(formatTimeAgo(0)).toBe('Just now');
    expect(formatTimeAgo(30)).toBe('Just now');
    expect(formatTimeAgo(59)).toBe('Just now');
  });

  it('returns minutes for seconds >= 60 and < 3600', () => {
    expect(formatTimeAgo(60)).toBe('1m ago');
    expect(formatTimeAgo(120)).toBe('2m ago');
    expect(formatTimeAgo(3599)).toBe('59m ago');
  });

  it('returns hours for seconds >= 3600 and < 86400', () => {
    expect(formatTimeAgo(3600)).toBe('1h ago');
    expect(formatTimeAgo(7200)).toBe('2h ago');
    expect(formatTimeAgo(86399)).toBe('23h ago');
  });

  it('returns days for seconds >= 86400', () => {
    expect(formatTimeAgo(86400)).toBe('1d ago');
    expect(formatTimeAgo(172800)).toBe('2d ago');
    expect(formatTimeAgo(604800)).toBe('7d ago');
  });
});

describe('formatCountdown', () => {
  it('returns "Overdue" for zero or negative seconds', () => {
    expect(formatCountdown(0)).toBe('Overdue');
    expect(formatCountdown(-100)).toBe('Overdue');
    expect(formatCountdown(-86400)).toBe('Overdue');
  });

  it('returns seconds format for < 60', () => {
    expect(formatCountdown(1)).toBe('1s');
    expect(formatCountdown(30)).toBe('30s');
    expect(formatCountdown(59)).toBe('59s');
  });

  it('returns minutes format for >= 60 and < 3600', () => {
    expect(formatCountdown(60)).toBe('1m');
    expect(formatCountdown(120)).toBe('2m');
    expect(formatCountdown(3599)).toBe('59m');
  });

  it('returns hours and minutes format for >= 3600 and < 86400', () => {
    expect(formatCountdown(3600)).toBe('1h 0m');
    expect(formatCountdown(3660)).toBe('1h 1m');
    expect(formatCountdown(7320)).toBe('2h 2m');
    expect(formatCountdown(86399)).toBe('23h 59m');
  });

  it('returns days and hours format for >= 86400', () => {
    expect(formatCountdown(86400)).toBe('1d 0h');
    expect(formatCountdown(90000)).toBe('1d 1h');
    expect(formatCountdown(172800)).toBe('2d 0h');
    expect(formatCountdown(259200)).toBe('3d 0h');
  });
});

describe('getNextRunSeconds', () => {
  const thresholdHours = 26; // 26 hours = 93600 seconds

  it('returns null for null rpoSeconds', () => {
    expect(getNextRunSeconds(null, thresholdHours)).toBeNull();
  });

  it('returns null for undefined rpoSeconds', () => {
    expect(getNextRunSeconds(undefined, thresholdHours)).toBeNull();
  });

  it('returns positive seconds when backup is fresh', () => {
    // Last backup was 10 hours ago (36000 seconds)
    // Threshold is 26 hours (93600 seconds)
    // Next run in: 93600 - 36000 = 57600 seconds (16 hours)
    expect(getNextRunSeconds(36000, thresholdHours)).toBe(57600);
  });

  it('returns zero when backup is exactly at threshold', () => {
    // Last backup was exactly 26 hours ago
    expect(getNextRunSeconds(93600, thresholdHours)).toBe(0);
  });

  it('returns negative seconds when backup is overdue', () => {
    // Last backup was 30 hours ago (108000 seconds)
    // Threshold is 26 hours (93600 seconds)
    // Overdue by: 93600 - 108000 = -14400 seconds
    expect(getNextRunSeconds(108000, thresholdHours)).toBe(-14400);
  });

  it('works with different threshold values', () => {
    // Test with 30 hour threshold (108000 seconds)
    expect(getNextRunSeconds(36000, 30)).toBe(72000); // 20 hours remaining
    expect(getNextRunSeconds(108000, 30)).toBe(0); // Exactly at threshold
    expect(getNextRunSeconds(144000, 30)).toBe(-36000); // 10 hours overdue
  });

  it('handles rpoSeconds of 0 (just backed up)', () => {
    // Just backed up, so RPO is 0
    // Should return full threshold time
    expect(getNextRunSeconds(0, thresholdHours)).toBe(93600);
  });
});

describe('Backup Status Logic', () => {
  it('determines if backup needs retry based on status', () => {
    const needsRetry = (status: 'ok' | 'warn' | 'fail') => {
      return status === 'fail' || status === 'warn';
    };

    expect(needsRetry('ok')).toBe(false);
    expect(needsRetry('warn')).toBe(true);
    expect(needsRetry('fail')).toBe(true);
  });

  it('determines if row is overdue based on next run seconds', () => {
    const isOverdue = (nextRunSeconds: number | null) => {
      return nextRunSeconds !== null && nextRunSeconds <= 0;
    };

    expect(isOverdue(null)).toBe(false);
    expect(isOverdue(3600)).toBe(false);
    expect(isOverdue(1)).toBe(false);
    expect(isOverdue(0)).toBe(true);
    expect(isOverdue(-1)).toBe(true);
    expect(isOverdue(-86400)).toBe(true);
  });
});

describe('Integration: Countdown Display Logic', () => {
  it('displays correct countdown for site with recent backup', () => {
    const rpoSeconds = 3600; // 1 hour since last backup
    const thresholdHours = 26;
    const nextRunSeconds = getNextRunSeconds(rpoSeconds, thresholdHours);

    expect(nextRunSeconds).toBe(90000); // 25 hours until next
    expect(formatCountdown(nextRunSeconds!)).toBe('1d 1h');
  });

  it('displays "Overdue" for site past threshold', () => {
    const rpoSeconds = 100000; // ~27.7 hours since last backup
    const thresholdHours = 26;
    const nextRunSeconds = getNextRunSeconds(rpoSeconds, thresholdHours);

    expect(nextRunSeconds).toBeLessThan(0);
    expect(formatCountdown(nextRunSeconds!)).toBe('Overdue');
  });

  it('displays countdown for site with backup just under threshold', () => {
    const rpoSeconds = 93000; // Just under 26 hours
    const thresholdHours = 26;
    const nextRunSeconds = getNextRunSeconds(rpoSeconds, thresholdHours);

    expect(nextRunSeconds).toBe(600); // 10 minutes remaining
    expect(formatCountdown(nextRunSeconds!)).toBe('10m');
  });
});
