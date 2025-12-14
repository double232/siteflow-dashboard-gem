import { useState } from 'react';

import { useContainerAction, useReloadCaddy, useSiteAction, useSites } from '../api/hooks';
import { useWebSocket } from '../api/WebSocketContext';
import { AuditLog } from '../components/AuditLog';
import { ConsoleOutput } from '../components/ConsoleOutput';
import { DeprovisionConfirm } from '../components/DeprovisionConfirm';
import { LogModal } from '../components/LogModal';
import { ProvisionForm } from '../components/ProvisionForm';
import { SiteCardGrid } from '../components/SiteCardGrid';

type ModalType = 'provision' | 'deprovision' | 'audit' | 'logs' | null;

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

export const SimpleDashboard = () => {
  const { data: siteData, isFetching: sitesLoading, refetch: refetchSites } = useSites({ useWebSocket: true });
  const { mutateAsync: actOnContainer, isPending: containerActionPending } = useContainerAction();
  const { mutateAsync: actOnSite, isPending: siteActionPending } = useSiteAction();
  const reloadCaddy = useReloadCaddy();
  const { isConnected } = useWebSocket();

  const [banner, setBanner] = useState<string>('');
  const [modal, setModal] = useState<ModalType>(null);
  const [selectedSiteName, setSelectedSiteName] = useState<string | null>(null);
  const [commandHistory, setCommandHistory] = useState<CommandResult[]>([]);

  const actionPending = containerActionPending || siteActionPending;

  const handleRefresh = () => {
    refetchSites();
  };

  const addToHistory = (result: CommandResult) => {
    setCommandHistory(prev => [result, ...prev]);
  };

  const handleSiteAction = async (siteName: string, action: 'start' | 'stop' | 'restart') => {
    try {
      const response = await actOnSite({ site: siteName, action });
      const isError = response.output.toLowerCase().includes('error') ||
                      response.output.toLowerCase().includes('no such file') ||
                      response.output.toLowerCase().includes('failed');
      addToHistory({
        title: `${siteName}: ${action}`,
        output: response.output,
        isError,
        timestamp: new Date(),
      });
      // Delayed refresh to let docker command complete
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

  const handleViewLogs = (siteName: string) => {
    setSelectedSiteName(siteName);
    setModal('logs');
  };

  const handleDeprovision = (siteName: string) => {
    setSelectedSiteName(siteName);
    setModal('deprovision');
  };

  const handleFetchLogs = async (container: string) => {
    const response = await actOnContainer({ container, action: 'logs' });
    return response.output;
  };

  const handleProvisionSuccess = () => {
    setModal(null);
    setBanner('Site provisioned successfully!');
    handleRefresh();
  };

  const handleDeprovisionSuccess = () => {
    setModal(null);
    setSelectedSiteName(null);
    setBanner('Site deprovisioned successfully!');
    handleRefresh();
  };

  const selectedSite = siteData?.sites.find(s => s.name === selectedSiteName);

  return (
    <div className="simple-dashboard">
      <header className="dashboard__header">
        <h1>SiteFlow Dashboard</h1>
        <div className="header-controls">
          <div className="ws-status">
            <span
              className={`ws-status__indicator ${isConnected ? 'ws-status__indicator--connected' : 'ws-status__indicator--disconnected'}`}
            />
            {isConnected ? 'Live' : 'Polling'}
          </div>
          <button onClick={() => setModal('provision')}>
            New Site
          </button>
          <button onClick={() => setModal('audit')}>
            Audit Log
          </button>
          <button onClick={handleRefresh} disabled={sitesLoading}>
            Refresh
          </button>
          <button
            onClick={() => reloadCaddy.mutateAsync().then((msg) => setBanner(msg))}
            disabled={reloadCaddy.isPending}
          >
            Reload Caddy
          </button>
        </div>
      </header>

      {banner && (
        <div className="banner" onClick={() => setBanner('')}>
          {banner}
        </div>
      )}

      <div className="dashboard-layout">
        <main className="dashboard-layout__cards">
          <SiteCardGrid
            sites={siteData?.sites}
            isLoading={sitesLoading}
            onSiteAction={handleSiteAction}
            onViewLogs={handleViewLogs}
            onDeprovision={handleDeprovision}
            isActionPending={actionPending}
          />
        </main>

        <aside className="dashboard-layout__console">
          <ConsoleOutput
            history={commandHistory}
            onClear={() => setCommandHistory([])}
          />
        </aside>
      </div>

      {/* Provision Modal */}
      {modal === 'provision' && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <ProvisionForm
              onSuccess={handleProvisionSuccess}
              onCancel={() => setModal(null)}
              onOutput={addToHistory}
            />
          </div>
        </div>
      )}

      {/* Deprovision Modal */}
      {modal === 'deprovision' && selectedSiteName && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <DeprovisionConfirm
              siteName={selectedSiteName}
              onSuccess={handleDeprovisionSuccess}
              onCancel={() => setModal(null)}
            />
          </div>
        </div>
      )}

      {/* Audit Log Modal */}
      {modal === 'audit' && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal modal--wide" onClick={(e) => e.stopPropagation()}>
            <button className="modal__close" onClick={() => setModal(null)}>X</button>
            <AuditLog />
          </div>
        </div>
      )}

      {/* Logs Modal */}
      {modal === 'logs' && selectedSite && (
        <LogModal
          siteName={selectedSite.name}
          containers={selectedSite.containers}
          onFetchLogs={handleFetchLogs}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
};
