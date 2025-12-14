import { useState } from 'react';

import { useProvisionSite, useTemplates } from '../api/hooks';
import type { TemplateType } from '../api/types/provision';

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

export const ProvisionForm = ({ onSuccess, onCancel, onOutput }: ProvisionFormProps) => {
  const { data: templatesData, isLoading: templatesLoading } = useTemplates();
  const { mutateAsync: provisionSite, isPending } = useProvisionSite();

  const [name, setName] = useState('');
  const [template, setTemplate] = useState<TemplateType>('static');
  const [domain, setDomain] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!name.match(/^[a-z0-9][a-z0-9-]*[a-z0-9]$/)) {
      setError('Name must be lowercase alphanumeric with hyphens, min 2 characters');
      return;
    }

    try {
      const result = await provisionSite({
        name,
        template,
        domain: domain || undefined,
      });
      onOutput?.({
        title: `provision: ${name}`,
        output: result.message || 'Site provisioned successfully',
        isError: false,
        timestamp: new Date(),
      });
      onSuccess?.();
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to provision site';
      setError(errorMsg);
      onOutput?.({
        title: `provision: ${name}`,
        output: errorMsg,
        isError: true,
        timestamp: new Date(),
      });
    }
  };

  if (templatesLoading) {
    return <div className="panel provision-form">Loading templates...</div>;
  }

  const templates = templatesData?.templates || [];

  return (
    <div className="panel provision-form">
      <div className="panel__title">Provision New Site</div>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="site-name">Site Name</label>
          <input
            id="site-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase())}
            placeholder="my-site"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="template">Template</label>
          <select
            id="template"
            value={template}
            onChange={(e) => setTemplate(e.target.value as TemplateType)}
          >
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>

        {templates.find((t) => t.id === template) && (
          <div className="template-info">
            <p>{templates.find((t) => t.id === template)?.description}</p>
            <p>
              <strong>Stack:</strong> {templates.find((t) => t.id === template)?.stack}
            </p>
          </div>
        )}

        <div className="form-group">
          <label htmlFor="domain">Domain (optional)</label>
          <input
            id="domain"
            type="text"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="example.com"
          />
        </div>

        {error && <div className="form-error">{error}</div>}

        <div className="form-actions">
          <button type="button" onClick={onCancel} disabled={isPending}>
            Cancel
          </button>
          <button type="submit" disabled={isPending || !name}>
            {isPending ? 'Provisioning...' : 'Provision Site'}
          </button>
        </div>
      </form>
    </div>
  );
};
