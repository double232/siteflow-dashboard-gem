import { useState, useEffect } from 'react';

import { useAuditLogs, useBackupSummary, useContainerAction, useDeployFromGitHub, useDeprovisionSite, useFolderDeploy, useHealth, usePullLatest, useProvisionSite, useReloadCaddy, useSiteAction, useSites, useUploadDeploy } from '../api/hooks';
import { SiteCardGrid } from '../components/SiteCardGrid';
import type { TemplateType } from '../api/types/provision';

type Theme = 'light' | 'dark';

const getInitialTheme = (): Theme => {
  const stored = localStorage.getItem('theme') as Theme | null;
  if (stored) return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

export const SimpleDashboard = () => {
  const { data: siteData, isFetching: sitesLoading, refetch: refetchSites } = useSites({ useWebSocket: true });
  const { data: auditData, refetch: refetchAudit } = useAuditLogs();
  const { data: healthData } = useHealth();
  const { data: backupData } = useBackupSummary();
  const { mutateAsync: actOnContainer } = useContainerAction();
  const { mutateAsync: actOnSite, isPending: siteActionPending } = useSiteAction();
  const { mutateAsync: provisionSite, isPending: provisionPending } = useProvisionSite();
  const { mutateAsync: deprovisionSite } = useDeprovisionSite();
  const { mutateAsync: deployFromGitHub, isPending: deployPending } = useDeployFromGitHub();
  const { mutateAsync: pullLatest, isPending: pullPending } = usePullLatest();
  const { mutateAsync: uploadDeploy, isPending: uploadPending } = useUploadDeploy();
  const { mutateAsync: folderDeploy, isPending: folderPending } = useFolderDeploy();
  const reloadCaddy = useReloadCaddy();

  const [commandHistory, setCommandHistory] = useState<CommandResult[]>([]);
  const [showProvision, setShowProvision] = useState(false);
  const [provisionName, setProvisionName] = useState('');
  const [provisionDomain, setProvisionDomain] = useState('');
  const [provisionSource, setProvisionSource] = useState<'none' | 'git' | 'folder' | 'zip'>('none');
  const [provisionGitUrl, setProvisionGitUrl] = useState('');
  const [provisionFiles, setProvisionFiles] = useState<FileList | null>(null);
  const [provisionStatus, setProvisionStatus] = useState('');
  const [deploySite, setDeploySite] = useState<string | null>(null);
  const [deployMode, setDeployMode] = useState<'git' | 'upload'>('git');
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

  // Detect project type from files
  const detectFromFiles = (files: FileList): string => {
    const fileNames: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      fileNames.push(path);
    }
    if (fileNames.some(f => f.includes('package.json'))) return 'node';
    if (fileNames.some(f => f.includes('requirements.txt'))) return 'python';
    if (fileNames.some(f => f.includes('pyproject.toml'))) return 'python';
    if (fileNames.some(f => f.includes('manage.py'))) return 'python';
    if (fileNames.some(f => f.includes('wp-config.php'))) return 'wordpress';
    if (fileNames.some(f => f.includes('wp-content/'))) return 'wordpress';
    return 'static';
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
      let detectedType = 'static';
      const domain = provisionDomain || `${provisionName}.double232.com`;

      // Step 1: Detect type (skip for 'none')
      if (provisionSource !== 'none') {
        setProvisionStatus('Detecting project type...');
        if (provisionSource === 'git') {
          if (!provisionGitUrl) {
            addToHistory({ title: 'provision', output: 'Please enter a Git URL', isError: true, timestamp: new Date() });
            setProvisionStatus('');
            return;
          }
          const { data } = await import('../api/client').then(m => m.apiClient.post('/api/provision/detect', { git_url: provisionGitUrl }));
          detectedType = data.detected_type;
        } else if (provisionFiles && provisionFiles.length > 0) {
          detectedType = detectFromFiles(provisionFiles);
        }
      }

      // Step 2: Provision
      setProvisionStatus(`Creating ${detectedType} site...`);
      await provisionSite({ name: provisionName, template: detectedType as TemplateType, domain });

      // Step 3: Deploy content (skip for 'none')
      if (provisionSource !== 'none') {
        setProvisionStatus('Deploying content...');
        if (provisionSource === 'git') {
          await deployFromGitHub({ site: provisionName, repo_url: provisionGitUrl, branch: 'main' });
        } else if (provisionSource === 'folder' && provisionFiles) {
          await folderDeploy({ site: provisionName, files: provisionFiles });
        } else if (provisionSource === 'zip' && provisionFiles?.[0]) {
          await uploadDeploy({ site: provisionName, file: provisionFiles[0] });
        }
      }

      addToHistory({
        title: `provision: ${provisionName}`,
        output: provisionSource === 'none'
          ? `Site created with landing page at ${domain}`
          : `Site created with ${detectedType} template and content deployed`,
        isError: false,
        timestamp: new Date(),
      });
      setProvisionName('');
      setProvisionDomain('');
      setProvisionGitUrl('');
      setProvisionFiles(null);
      setProvisionSource('none');
      setProvisionStatus('');
      setShowProvision(false);
      refetchSites();
    } catch (e) {
      setProvisionStatus('');
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

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!deploySite || !e.target.files?.[0]) return;
    const file = e.target.files[0];

    addToHistory({
      title: `${deploySite}: uploading`,
      output: `Uploading ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)...`,
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await uploadDeploy({ site: deploySite, file });
      addToHistory({
        title: `${deploySite}: upload deploy`,
        output: result.output || 'Deployed successfully',
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      setDeploySite(null);
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `${deploySite}: upload deploy`,
        output: e instanceof Error ? e.message : 'Upload failed',
        isError: true,
        timestamp: new Date(),
      });
    }
    // Reset file input
    e.target.value = '';
  };

  const handleFolderUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!deploySite || !e.target.files?.length) return;
    const files = e.target.files;

    addToHistory({
      title: `${deploySite}: uploading folder`,
      output: `Uploading ${files.length} files...`,
      isError: false,
      timestamp: new Date(),
    });

    try {
      const result = await folderDeploy({ site: deploySite, files });
      addToHistory({
        title: `${deploySite}: folder deploy`,
        output: result.output || 'Deployed successfully',
        isError: result.status === 'error',
        timestamp: new Date(),
      });
      setDeploySite(null);
      refetchSites();
    } catch (e) {
      addToHistory({
        title: `${deploySite}: folder deploy`,
        output: e instanceof Error ? e.message : 'Upload failed',
        isError: true,
        timestamp: new Date(),
      });
    }
    e.target.value = '';
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

  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  return (
    <div className="simple-dashboard">
      <header className="dashboard__header">
        <h1>SiteFlow Dashboard</h1>
        <div className="header-controls">
          <button onClick={() => setShowProvision(!showProvision)}>
            {showProvision ? 'Cancel' : 'New Site'}
          </button>
          <button onClick={handleShowAudit}>Audit</button>
          <button onClick={() => refetchSites()} disabled={sitesLoading}>Refresh</button>
          <button onClick={handleReloadCaddy} disabled={reloadCaddy.isPending}>Reload Caddy</button>
          <button onClick={toggleTheme} className="theme-toggle">
            {theme === 'light' ? 'Dark' : 'Light'}
          </button>
        </div>
      </header>

      {showProvision && (
        <form className="provision-bar" onSubmit={handleProvision}>
          <input
            type="text"
            value={provisionName}
            onChange={(e) => setProvisionName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
            placeholder="site-name"
            required
            disabled={provisionPending}
          />
          <input
            type="text"
            value={provisionDomain}
            onChange={(e) => setProvisionDomain(e.target.value)}
            placeholder={`${provisionName || 'site'}.double232.com`}
            disabled={provisionPending}
          />
          <div className="template-buttons">
            <button
              type="button"
              className={`template-btn ${provisionSource === 'none' ? 'template-btn--active' : ''}`}
              onClick={() => setProvisionSource('none')}
              disabled={provisionPending}
            >
              None
            </button>
            <button
              type="button"
              className={`template-btn ${provisionSource === 'git' ? 'template-btn--active' : ''}`}
              onClick={() => setProvisionSource('git')}
              disabled={provisionPending}
            >
              Git
            </button>
            <button
              type="button"
              className={`template-btn ${provisionSource === 'folder' ? 'template-btn--active' : ''}`}
              onClick={() => setProvisionSource('folder')}
              disabled={provisionPending}
            >
              Folder
            </button>
            <button
              type="button"
              className={`template-btn ${provisionSource === 'zip' ? 'template-btn--active' : ''}`}
              onClick={() => setProvisionSource('zip')}
              disabled={provisionPending}
            >
              Zip
            </button>
          </div>
          {provisionSource === 'git' && (
            <input
              type="text"
              value={provisionGitUrl}
              onChange={(e) => setProvisionGitUrl(e.target.value)}
              placeholder="https://github.com/user/repo"
              disabled={provisionPending}
            />
          )}
          {provisionSource === 'folder' && (
            <label className="file-input-btn">
              {provisionFiles ? `${provisionFiles.length} files` : 'Choose Folder'}
              <input
                type="file"
                onChange={(e) => setProvisionFiles(e.target.files)}
                disabled={provisionPending}
                hidden
                {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
              />
            </label>
          )}
          {provisionSource === 'zip' && (
            <label className="file-input-btn">
              {provisionFiles?.[0]?.name || 'Choose Zip'}
              <input
                type="file"
                accept=".zip"
                onChange={(e) => setProvisionFiles(e.target.files)}
                disabled={provisionPending}
                hidden
              />
            </label>
          )}
          {provisionStatus && <span className="provision-status">{provisionStatus}</span>}
          <button type="submit" disabled={provisionPending || !provisionName}>
            {provisionPending ? 'Creating...' : 'Create'}
          </button>
        </form>
      )}

      {deploySite && (
        <div className="deploy-bar">
          <span className="deploy-bar__label">Deploy to {deploySite}:</span>
          <div className="deploy-bar__mode">
            <button
              type="button"
              className={`mode-btn ${deployMode === 'git' ? 'mode-btn--active' : ''}`}
              onClick={() => setDeployMode('git')}
            >
              Git
            </button>
            <button
              type="button"
              className={`mode-btn ${deployMode === 'upload' ? 'mode-btn--active' : ''}`}
              onClick={() => setDeployMode('upload')}
            >
              Upload
            </button>
          </div>
          {deployMode === 'git' ? (
            <form className="deploy-bar__form" onSubmit={handleDeploy}>
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
                {deployPending ? 'Deploying...' : 'Clone'}
              </button>
            </form>
          ) : (
            <div className="deploy-bar__upload">
              <label className="upload-btn">
                {uploadPending ? 'Uploading...' : '.zip file'}
                <input
                  type="file"
                  accept=".zip"
                  onChange={handleUpload}
                  disabled={uploadPending}
                  hidden
                />
              </label>
              <label className="upload-btn">
                {folderPending ? 'Uploading...' : 'Folder'}
                <input
                  type="file"
                  onChange={handleFolderUpload}
                  disabled={folderPending}
                  hidden
                  {...{ webkitdirectory: '', directory: '' } as React.InputHTMLAttributes<HTMLInputElement>}
                />
              </label>
            </div>
          )}
          <button type="button" onClick={() => setDeploySite(null)}>Cancel</button>
        </div>
      )}

      <div className="dashboard-layout">
        <main className="dashboard-layout__cards">
          <SiteCardGrid
            sites={siteData?.sites}
            healthData={healthData}
            backupData={backupData}
            isLoading={sitesLoading}
            onSiteAction={handleSiteAction}
            onViewLogs={handleViewLogs}
            onDeprovision={handleDeprovision}
            onDeploy={(siteName) => setDeploySite(siteName)}
            onPull={handlePull}
            isActionPending={siteActionPending || deployPending || pullPending || uploadPending || folderPending}
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
