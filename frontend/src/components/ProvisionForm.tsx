import { useState, useRef } from 'react';

import { apiClient } from '../api/client';

interface CommandResult {
  title: string;
  output: string;
  isError: boolean;
  timestamp: Date;
}

interface ProvisionFormProps {
  onSuccess?: () => void;
  onCancel?: () => void;
  onOutput?: (result: CommandResult) => void;
}

type SourceType = 'git' | 'folder' | 'zip';

// Client-side detection from file list
const detectFromFiles = (files: File[]): string => {
  const fileNames = files.map(f => f.name.split('/').pop() || f.name);
  const paths = files.map(f => (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name);

  // Check for indicators
  if (fileNames.includes('package.json') || paths.some(p => p.includes('package.json'))) {
    return 'node';
  }
  if (fileNames.includes('requirements.txt') || paths.some(p => p.includes('requirements.txt'))) {
    return 'python';
  }
  if (fileNames.includes('pyproject.toml') || paths.some(p => p.includes('pyproject.toml'))) {
    return 'python';
  }
  if (fileNames.includes('manage.py') || paths.some(p => p.includes('manage.py'))) {
    return 'python';
  }
  if (fileNames.includes('wp-config.php') || paths.some(p => p.includes('wp-config.php'))) {
    return 'wordpress';
  }
  if (paths.some(p => p.includes('wp-content/'))) {
    return 'wordpress';
  }

  return 'static';
};

export const ProvisionForm = ({ onSuccess, onCancel, onOutput }: ProvisionFormProps) => {
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [sourceType, setSourceType] = useState<SourceType>('git');
  const [gitUrl, setGitUrl] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [status, setStatus] = useState('');

  const folderInputRef = useRef<HTMLInputElement>(null);
  const zipInputRef = useRef<HTMLInputElement>(null);

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (fileList) {
      setFiles(Array.from(fileList));
    }
  };

  const handleZipSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (fileList && fileList[0]) {
      setFiles([fileList[0]]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    if (!name.match(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/) && name.length >= 2) {
      if (!name.match(/^[a-z0-9]+$/)) {
        setError('Name must be lowercase alphanumeric with hyphens');
        setIsSubmitting(false);
        return;
      }
    }

    try {
      let detectedType = 'static';

      // Step 1: Detect project type
      setStatus('Detecting project type...');

      if (sourceType === 'git') {
        if (!gitUrl) {
          setError('Please enter a Git URL');
          setIsSubmitting(false);
          return;
        }
        // Detect from git
        const detectRes = await apiClient.post('/api/provision/detect', { git_url: gitUrl });
        detectedType = detectRes.data.detected_type;
        setStatus(`Detected: ${detectedType}`);
      } else if (sourceType === 'folder' || sourceType === 'zip') {
        if (files.length === 0) {
          setError(`Please select ${sourceType === 'zip' ? 'a zip file' : 'a folder'}`);
          setIsSubmitting(false);
          return;
        }
        // Detect from files client-side
        detectedType = detectFromFiles(files);
        setStatus(`Detected: ${detectedType}`);
      }

      // Step 2: Provision site with detected template
      setStatus(`Creating ${detectedType} site...`);
      await apiClient.post('/api/provision/', {
        name,
        template: detectedType,
        domain: domain || undefined,
      });

      // Step 3: Deploy content
      setStatus('Deploying content...');

      if (sourceType === 'git') {
        await apiClient.post('/api/deploy/github', {
          site: name,
          repo_url: gitUrl,
          branch: 'main',
        });
      } else if (sourceType === 'folder') {
        const formData = new FormData();
        formData.append('site', name);
        for (const file of files) {
          const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
          formData.append('files', file, path);
        }
        await apiClient.post('/api/deploy/folder', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 600000,
        });
      } else if (sourceType === 'zip') {
        const formData = new FormData();
        formData.append('site', name);
        formData.append('file', files[0]);
        await apiClient.post('/api/deploy/upload', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 300000,
        });
      }

      setStatus('Done!');
      onOutput?.({
        title: `provision: ${name}`,
        output: `Site '${name}' created with ${detectedType} template and content deployed`,
        isError: false,
        timestamp: new Date(),
      });
      onSuccess?.();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to provision site';
      setError(errorMsg);
      setStatus('');
      onOutput?.({
        title: `provision: ${name}`,
        output: errorMsg,
        isError: true,
        timestamp: new Date(),
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="panel provision-form">
      <div className="panel__title">New Site</div>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="site-name">Site Name</label>
          <input
            id="site-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
            placeholder="my-site"
            required
            disabled={isSubmitting}
          />
        </div>

        <div className="form-group">
          <label htmlFor="domain">Domain (optional)</label>
          <input
            id="domain"
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="mysite.example.com"
            disabled={isSubmitting}
          />
        </div>

        <div className="form-group">
          <label>Source</label>
          <div className="source-tabs">
            <button
              type="button"
              className={`source-tab ${sourceType === 'git' ? 'source-tab--active' : ''}`}
              onClick={() => setSourceType('git')}
              disabled={isSubmitting}
            >
              Git
            </button>
            <button
              type="button"
              className={`source-tab ${sourceType === 'folder' ? 'source-tab--active' : ''}`}
              onClick={() => setSourceType('folder')}
              disabled={isSubmitting}
            >
              Folder
            </button>
            <button
              type="button"
              className={`source-tab ${sourceType === 'zip' ? 'source-tab--active' : ''}`}
              onClick={() => setSourceType('zip')}
              disabled={isSubmitting}
            >
              Zip
            </button>
          </div>
        </div>

        {sourceType === 'git' && (
          <div className="form-group">
            <label htmlFor="git-url">Repository URL</label>
            <input
              id="git-url"
              type="text"
              value={gitUrl}
              onChange={(e) => setGitUrl(e.target.value)}
              placeholder="https://github.com/user/repo"
              disabled={isSubmitting}
            />
          </div>
        )}

        {sourceType === 'folder' && (
          <div className="form-group">
            <label>Select Folder</label>
            <input
              ref={folderInputRef}
              type="file"
              webkitdirectory=""
              directory=""
              multiple
              onChange={handleFolderSelect}
              disabled={isSubmitting}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="file-select-btn"
              onClick={() => folderInputRef.current?.click()}
              disabled={isSubmitting}
            >
              {files.length > 0 ? `${files.length} files selected` : 'Choose Folder'}
            </button>
          </div>
        )}

        {sourceType === 'zip' && (
          <div className="form-group">
            <label>Select Zip File</label>
            <input
              ref={zipInputRef}
              type="file"
              accept=".zip"
              onChange={handleZipSelect}
              disabled={isSubmitting}
              style={{ display: 'none' }}
            />
            <button
              type="button"
              className="file-select-btn"
              onClick={() => zipInputRef.current?.click()}
              disabled={isSubmitting}
            >
              {files.length > 0 ? files[0].name : 'Choose Zip File'}
            </button>
          </div>
        )}

        {status && <div className="form-status">{status}</div>}
        {error && <div className="form-error">{error}</div>}

        <div className="form-actions">
          <button type="button" onClick={onCancel} disabled={isSubmitting}>
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting || !name}>
            {isSubmitting ? 'Creating...' : 'Create Site'}
          </button>
        </div>
      </form>
    </div>
  );
};
