import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { retryCrmConnection } from '@/lib/crm-connection';

describe('CRM connection recovery', () => {
  it('recovers a loader read after two interrupted requests', async () => {
    const client = new QueryClient();
    let attempts = 0;
    const result = await client.ensureQueryData({
      queryKey: ['connection-test'], retry: retryCrmConnection, retryDelay: 0,
      queryFn: async () => {
        attempts += 1;
        if (attempts < 3) throw new TypeError('Failed to fetch');
        return { authorized: true, leads: [{ id: 'saved-lead' }] };
      },
    });
    expect(attempts).toBe(3);
    expect(result.leads[0]?.id).toBe('saved-lead');
    client.clear();
  });
  it('stops retrying persistent transport failures', () => {
    expect(retryCrmConnection(2, new TypeError('Failed to fetch'))).toBe(false);
  });
  it('does not retry authorization or application errors', () => {
    expect(retryCrmConnection(0, new Error('Acesso não autorizado.'))).toBe(false);
    expect(retryCrmConnection(0, new TypeError('Invalid input'))).toBe(false);
  });
});