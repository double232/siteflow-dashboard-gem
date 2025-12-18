import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SiteFilterBar, computeFilterCounts, filterSites } from './SiteFilterBar';
import type { Site } from '../api/types';
import type { HealthResponse } from '../api/types/health';
import type { BackupSummaryResponse } from '../api/types/backups';

// Mock site data
const createMockSite = (name: string, status: 'running' | 'stopped' | 'degraded' = 'running'): Site => ({
  name,
  path: `/opt/sites/${name}`,
  status,
  containers: [],
  caddy_domains: [`${name}.example.com`],
  cloudflare_status: 'active',
});

const mockSites: Site[] = [
  createMockSite('site1', 'running'),
  createMockSite('site2', 'stopped'),
  createMockSite('site3', 'degraded'),
  createMockSite('site4', 'running'),
];

const mockHealthData: HealthResponse = {
  monitors: {
    site1: {
      id: 1,
      name: 'site1',
      status: 2,
      uptime: 99.5,
      heartbeats: [{ status: 1, time: '2024-01-01' }],
    },
    site2: {
      id: 2,
      name: 'site2',
      status: 0,
      uptime: 95.0, // Low uptime - should be an issue
      heartbeats: [{ status: 0, time: '2024-01-01' }], // Down heartbeat
    },
    site4: {
      id: 4,
      name: 'site4',
      status: 2,
      uptime: 100,
      heartbeats: [{ status: 1, time: '2024-01-01' }],
    },
  },
};

const mockBackupData: BackupSummaryResponse = {
  sites: [
    { site: 'site1', overall_status: 'ok', rpo_seconds_db: 3600, rpo_seconds_uploads: 3600, last_db_run: null, last_uploads_run: null, last_verify_run: null, last_snapshot_run: null },
    { site: 'site3', overall_status: 'warn', rpo_seconds_db: 90000, rpo_seconds_uploads: 90000, last_db_run: null, last_uploads_run: null, last_verify_run: null, last_snapshot_run: null },
    { site: 'site4', overall_status: 'fail', rpo_seconds_db: null, rpo_seconds_uploads: null, last_db_run: null, last_uploads_run: null, last_verify_run: null, last_snapshot_run: null },
  ],
  thresholds: {
    db_fresh_hours: 26,
    uploads_fresh_hours: 30,
    verify_fresh_days: 7,
    snapshot_fresh_days: 8,
  },
};

describe('computeFilterCounts', () => {
  it('returns zeros when sites is undefined', () => {
    const counts = computeFilterCounts(undefined, mockHealthData, mockBackupData);
    expect(counts).toEqual({ all: 0, issues: 0, stopped: 0, backup_warnings: 0 });
  });

  it('returns zeros when sites is empty', () => {
    const counts = computeFilterCounts([], mockHealthData, mockBackupData);
    expect(counts).toEqual({ all: 0, issues: 0, stopped: 0, backup_warnings: 0 });
  });

  it('counts all sites correctly', () => {
    const counts = computeFilterCounts(mockSites, mockHealthData, mockBackupData);
    expect(counts.all).toBe(4);
  });

  it('counts stopped and degraded sites correctly', () => {
    const counts = computeFilterCounts(mockSites, mockHealthData, mockBackupData);
    // site2 is stopped, site3 is degraded
    expect(counts.stopped).toBe(2);
  });

  it('counts sites with health issues correctly', () => {
    const counts = computeFilterCounts(mockSites, mockHealthData, mockBackupData);
    // site2 has low uptime (95%) and down heartbeat
    expect(counts.issues).toBe(1);
  });

  it('counts backup warnings correctly', () => {
    const counts = computeFilterCounts(mockSites, mockHealthData, mockBackupData);
    // site3 has warn, site4 has fail
    expect(counts.backup_warnings).toBe(2);
  });

  it('handles case-insensitive site name matching for health', () => {
    const healthWithLowercase: HealthResponse = {
      monitors: {
        site1: { id: 1, name: 'site1', status: 0, uptime: 50, heartbeats: [{ status: 0, time: '2024-01-01' }] },
      },
    };
    const counts = computeFilterCounts([createMockSite('SITE1')], healthWithLowercase, undefined);
    // Should still match despite case difference
    expect(counts.issues).toBe(1);
  });
});

describe('filterSites', () => {
  it('returns undefined when sites is undefined', () => {
    const result = filterSites(undefined, 'all', mockHealthData, mockBackupData);
    expect(result).toBeUndefined();
  });

  it('returns all sites when filter is "all"', () => {
    const result = filterSites(mockSites, 'all', mockHealthData, mockBackupData);
    expect(result).toEqual(mockSites);
  });

  it('filters stopped and degraded sites', () => {
    const result = filterSites(mockSites, 'stopped', mockHealthData, mockBackupData);
    expect(result).toHaveLength(2);
    expect(result?.map(s => s.name)).toContain('site2');
    expect(result?.map(s => s.name)).toContain('site3');
  });

  it('filters sites with health issues', () => {
    const result = filterSites(mockSites, 'issues', mockHealthData, mockBackupData);
    expect(result).toHaveLength(1);
    expect(result?.[0].name).toBe('site2');
  });

  it('filters sites with backup warnings', () => {
    const result = filterSites(mockSites, 'backup_warnings', mockHealthData, mockBackupData);
    expect(result).toHaveLength(2);
    expect(result?.map(s => s.name)).toContain('site3');
    expect(result?.map(s => s.name)).toContain('site4');
  });

  it('returns empty array when no sites match filter', () => {
    const healthySites = [createMockSite('healthy1'), createMockSite('healthy2')];
    const result = filterSites(healthySites, 'stopped', mockHealthData, mockBackupData);
    expect(result).toEqual([]);
  });
});

describe('SiteFilterBar Component', () => {
  it('renders all filter buttons', () => {
    const onFilterChange = vi.fn();
    render(
      <SiteFilterBar
        activeFilter="all"
        onFilterChange={onFilterChange}
        sites={mockSites}
        healthData={mockHealthData}
        backupData={mockBackupData}
      />
    );

    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Issues')).toBeInTheDocument();
    expect(screen.getByText('Stopped')).toBeInTheDocument();
    expect(screen.getByText('Backups')).toBeInTheDocument();
  });

  it('displays correct counts', () => {
    const onFilterChange = vi.fn();
    render(
      <SiteFilterBar
        activeFilter="all"
        onFilterChange={onFilterChange}
        sites={mockSites}
        healthData={mockHealthData}
        backupData={mockBackupData}
      />
    );

    // All: 4, Issues: 1, Stopped: 2, Backups: 2
    const countBadges = document.querySelectorAll('.site-filter-bar__count');
    expect(countBadges).toHaveLength(4);

    // Check individual counts by finding parent buttons
    const allButton = screen.getByText('All').closest('button');
    const issuesButton = screen.getByText('Issues').closest('button');
    const stoppedButton = screen.getByText('Stopped').closest('button');
    const backupsButton = screen.getByText('Backups').closest('button');

    expect(allButton?.querySelector('.site-filter-bar__count')?.textContent).toBe('4');
    expect(issuesButton?.querySelector('.site-filter-bar__count')?.textContent).toBe('1');
    expect(stoppedButton?.querySelector('.site-filter-bar__count')?.textContent).toBe('2');
    expect(backupsButton?.querySelector('.site-filter-bar__count')?.textContent).toBe('2');
  });

  it('calls onFilterChange when clicking a filter button', () => {
    const onFilterChange = vi.fn();
    render(
      <SiteFilterBar
        activeFilter="all"
        onFilterChange={onFilterChange}
        sites={mockSites}
        healthData={mockHealthData}
        backupData={mockBackupData}
      />
    );

    fireEvent.click(screen.getByText('Issues'));
    expect(onFilterChange).toHaveBeenCalledWith('issues');

    fireEvent.click(screen.getByText('Stopped'));
    expect(onFilterChange).toHaveBeenCalledWith('stopped');

    fireEvent.click(screen.getByText('Backups'));
    expect(onFilterChange).toHaveBeenCalledWith('backup_warnings');
  });

  it('applies active class to selected filter', () => {
    const onFilterChange = vi.fn();
    const { rerender } = render(
      <SiteFilterBar
        activeFilter="issues"
        onFilterChange={onFilterChange}
        sites={mockSites}
        healthData={mockHealthData}
        backupData={mockBackupData}
      />
    );

    const issuesButton = screen.getByText('Issues').closest('button');
    expect(issuesButton).toHaveClass('site-filter-bar__btn--active');

    rerender(
      <SiteFilterBar
        activeFilter="stopped"
        onFilterChange={onFilterChange}
        sites={mockSites}
        healthData={mockHealthData}
        backupData={mockBackupData}
      />
    );

    const stoppedButton = screen.getByText('Stopped').closest('button');
    expect(stoppedButton).toHaveClass('site-filter-bar__btn--active');
  });

  it('does not show count badge when count is 0', () => {
    const onFilterChange = vi.fn();
    const healthySites = [createMockSite('healthy1')];

    render(
      <SiteFilterBar
        activeFilter="all"
        onFilterChange={onFilterChange}
        sites={healthySites}
        healthData={undefined}
        backupData={undefined}
      />
    );

    // All should show 1, others should not have badges
    expect(screen.getByText('1')).toBeInTheDocument();
    const countBadges = document.querySelectorAll('.site-filter-bar__count');
    expect(countBadges).toHaveLength(1); // Only the "All" count
  });
});
