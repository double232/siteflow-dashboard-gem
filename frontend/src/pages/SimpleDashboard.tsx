import { useState } from 'react';

import { useAuditLogs, useContainerAction, useDeployFromGitHub, useDeprovisionSite, usePullLatest, useProvisionSite, useReloadCaddy, useSiteAction, useSites, useTemplates } from '../api/hooks';
import { useWebSocket } from '../api/WebSocketContext';
import { SiteCardGrid } from '../components/SiteCardGrid';
import type { TemplateType } from '../api/types/provision';

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

export const SimpleDashboard = () => {
  const { data: siteData, isFetching: sitesLoading, refetch: refetchSites } = useSites({ useWebSocket: true });
  const { data: templatesData } = useTemplates();
  const { data: auditData, refetch: refetchAudit } = useAuditLogs();
  const { mutateAsync: actOnContainer } = useContainerAction();
  const { mutateAsync: actOnSite, isPending: siteActionPending } = useSiteAction();
  const { mutateAsync: provisionSite, isPending: provisionPending } = useProvisionSite();
  const { mutateAsync: deprovisionSite } = useDeprovisionSite();
  const { mutateAsync: deployFromGitHub, isPending: deployPending } = useDeployFromGitHub();
  const { mutateAsync: pullLatest, isPending: pullPending } = usePullLatest();
  const reloadCaddy = useReloadCaddy();
  const { isConnected } = useWebSocket();

  const [commandHistory, setCommandHistory] = useState<CommandResult[]>([]);
  const [showProvision, setShowProvision] = useState(false);
  const [provisionName, setProvisionName] = useState('');
  const [provisionTemplate, setProvisionTemplate] = useState<TemplateType>('static');
  const [provisionDomain, setProvisionDomain] = useState('');
  const [deploySite, setDeploySite] = useState<string | null>(null);
  const [deployRepo, setDeployRepo] = useState('');
  const [deployBranch, setDeployBranch] = useState('main');

  const addToHistory = (result: CommandResult) => {
    setCommandHistory(prev => [result, ...prev]);
  };

  const handleSiteAction = async (siteName: string, action: 'start' | 'stop' | 'restart') => {
    try {
      const response = await actOnSite({ site: siteName, action });
      const isError = response.output.toLowerCase().includes('error') ||
                      response.output.toLowerCase().includes('failed');
      addToHistory({
        title: `${siteName}: ${action}`,
        output: response.output,
        isError,
        timestamp: new Date(),
      });
      if (!isError) {
        setTimeout(() => refetchSites(), 2000);
      }
    } catch (e) {
      addToHistory({
        title: `${siteName}: ${action}`,
        output: e instanceof Error ? e.message : 'Action failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleViewLogs = async (siteName: string) => {
    const site = siteData?.sites.find(s => s.name === siteName);
    if (!site?.containers.length) {
      addToHistory({
        title: `${siteName}: logs`,
        output: 'No containers found',
        isError: true,
        timestamp: new Date(),
      });
      return;
    }

    for (const container of site.containers) {
      try {
        const response = await actOnContainer({ container: container.name, action: 'logs' });
        addToHistory({
          title: `${container.name}: logs`,
          output: response.output || '(empty)',
          isError: false,
          timestamp: new Date(),
        });
      } catch (e) {
        addToHistory({
          title: `${container.name}: logs`,
          output: e instanceof Error ? e.message : 'Failed to fetch logs',
          isError: true,
          timestamp: new Date(),
        });
      }
    }
  };

  const handleDeprovision = async (siteName: string) => {
    if (!confirm(`Delete site "${siteName}"? This will stop containers and remove files.`)) {
      return;
    }
    try {
      const response = await deprovisionSite({ name: siteName, remove_volumes: true, remove_files: true });
      addToHistory({
        title: `${siteName}: deprovision`,
        output: response.message || 'Site removed',
        isError: false,
        timestamp: new Date(),
      });
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `${siteName}: deprovision`,
        output: e instanceof Error ? e.message : 'Failed to deprovision',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleProvision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!provisionName.match(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/) && provisionName.length > 1) {
      addToHistory({
        title: 'provision',
        output: 'Name must be lowercase alphanumeric with hyphens',
        isError: true,
        timestamp: new Date(),
      });
      return;
    }
    try {
      const domain = provisionDomain || `${provisionName}.double232.com`;
      const result = await provisionSite({
        name: provisionName,
        template: provisionTemplate,
        domain,
      });
      addToHistory({
        title: `provision: ${provisionName}`,
        output: result.message || 'Site provisioned',
        isError: false,
        timestamp: new Date(),
      });
      setProvisionName('');
      setProvisionDomain('');
      setShowProvision(false);
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `provision: ${provisionName}`,
        output: e instanceof Error ? e.message : 'Provision failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleShowAudit = async () => {
    await refetchAudit();
    const logs = auditData?.logs || [];
    if (logs.length === 0) {
      addToHistory({
        title: 'audit log',
        output: 'No audit entries found',
        isError: false,
        timestamp: new Date(),
      });
      return;
    }
    const output = logs.slice(0, 20).map(e =>
      `[${new Date(e.timestamp).toLocaleString()}] ${e.action_type} ${e.target_name}: ${e.status}${e.error_message ? ' - ' + e.error_message : ''}`
    ).join('\n');
    addToHistory({
      title: 'audit log (last 20)',
      output,
      isError: false,
      timestamp: new Date(),
    });
  };

  const handleReloadCaddy = async () => {
    try {
      const msg = await reloadCaddy.mutateAsync();
      addToHistory({
        title: 'caddy: reload',
        output: msg,
        isError: msg.toLowerCase().includes('failed'),
        timestamp: new Date(),
      });
    } catch (e) {
      addToHistory({
        title: 'caddy: reload',
        output: e instanceof Error ? e.message : 'Reload failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deploySite || !deployRepo) return;

    addToHistory({
      title: `${deploySite}: deploying`,
      output: `Cloning ${deployRepo} (${deployBranch})...`,
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await deployFromGitHub({
        site: deploySite,
        repo_url: deployRepo,
        branch: deployBranch,
      });
      addToHistory({
        title: `${deploySite}: deploy`,
        output: result.output || 'Deployed successfully',
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      setDeploySite(null);
      setDeployRepo('');
      setDeployBranch('main');
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `${deploySite}: deploy`,
        output: e instanceof Error ? e.message : 'Deploy failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const handlePull = async (siteName: string) => {
    addToHistory({
      title: `${siteName}: pulling`,
      output: 'Pulling latest changes...',
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await pullLatest({ site: siteName });
      addToHistory({
        title: `${siteName}: pull`,
        output: result.output || 'Pulled successfully',
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `${siteName}: pull`,
        output: e instanceof Error ? e.message : 'Pull failed',
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  const templates = templatesData?.templates || [];

  return (
    <div className="simple-dashboard">
      <header className="dashboard__header">
        <h1>SiteFlow Dashboard</h1>
        <div className="header-controls">
          <div className="ws-status">
            <span className={`ws-status__indicator ${isConnected ? 'ws-status__indicator--connected' : 'ws-status__indicator--disconnected'}`} />
            {isConnected ? 'Live' : 'Polling'}
          </div>
          <button onClick={() => setShowProvision(!showProvision)}>
            {showProvision ? 'Cancel' : 'New Site'}
          </button>
          <button onClick={handleShowAudit}>Audit</button>
          <button onClick={() => refetchSites()} disabled={sitesLoading}>Refresh</button>
          <button onClick={handleReloadCaddy} disabled={reloadCaddy.isPending}>Reload Caddy</button>
        </div>
      </header>

      {showProvision && (
        <form className="provision-bar" onSubmit={handleProvision}>
          <input
            type="text"
            value={provisionName}
            onChange={(e) => setProvisionName(e.target.value.toLowerCase())}
            placeholder="site-name"
            required
          />
          <div className="template-buttons">
            {templates.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`template-btn ${provisionTemplate === t.id ? 'template-btn--active' : ''}`}
                onClick={() => setProvisionTemplate(t.id)}
              >
                {t.id}
              </button>
            ))}
          </div>
          <input
            type="text"
            value={provisionDomain}
            onChange={(e) => setProvisionDomain(e.target.value)}
            placeholder={`${provisionName || 'site'}.double232.com`}
          />
          <button type="submit" disabled={provisionPending || !provisionName}>
            {provisionPending ? 'Creating...' : 'Create'}
          </button>
        </form>
      )}

      {deploySite && (
        <form className="deploy-bar" onSubmit={handleDeploy}>
          <span className="deploy-bar__label">Deploy to {deploySite}:</span>
          <input
            type="text"
            value={deployRepo}
            onChange={(e) => setDeployRepo(e.target.value)}
            placeholder="github.com/user/repo"
            required
          />
          <input
            type="text"
            value={deployBranch}
            onChange={(e) => setDeployBranch(e.target.value)}
            placeholder="main"
            className="deploy-bar__branch"
          />
          <button type="submit" disabled={deployPending || !deployRepo}>
            {deployPending ? 'Deploying...' : 'Deploy'}
          </button>
          <button type="button" onClick={() => setDeploySite(null)}>Cancel</button>
        </form>
      )}

      <div className="dashboard-layout">
        <main className="dashboard-layout__cards">
          <SiteCardGrid
            sites={siteData?.sites}
            isLoading={sitesLoading}
            onSiteAction={handleSiteAction}
            onViewLogs={handleViewLogs}
            onDeprovision={handleDeprovision}
            onDeploy={(siteName) => setDeploySite(siteName)}
            onPull={handlePull}
            isActionPending={siteActionPending || deployPending || pullPending}
          />
        </main>

        <aside className="dashboard-layout__console">
          <div className="console-output">
            <div className="console-output__header">
              <span className="console-output__title">Console Output</span>
              {commandHistory.length > 0 && (
                <button className="console-output__clear" onClick={() => setCommandHistory([])}>Clear</button>
              )}
            </div>
            <div className="console-output__content">
              {commandHistory.length === 0 ? (
                <p className="console-output__placeholder">Command output will appear here</p>
              ) : (
                commandHistory.map((result, index) => (
                  <div
                    key={`${result.timestamp.getTime()}-${index}`}
                    className={`console-output__entry ${result.isError ? 'console-output__entry--error' : 'console-output__entry--success'}`}
                  >
                    <div className="console-output__entry-header">
                      <span className="console-output__entry-title">{result.title}</span>
                      <span className="console-output__entry-time">
                        {result.timestamp.toLocaleTimeString()}
                      </span>
                    </div>
                    <pre className="console-output__entry-output">{result.output}</pre>
                  </div>
                ))
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
};
