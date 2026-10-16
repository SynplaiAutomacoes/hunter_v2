import { describe, expect, it } from 'vitest';
import { Workbook } from 'exceljs';
import { createLeadWorkbook } from '@/lib/crm-export';
import { readAllCrmRows } from '@/lib/crm-pagination';
import type { CrmLead } from '@/lib/crm';

const lead: CrmLead = {
 id: 'lead-1', submission_id: 'submission-1', name: '=HYPERLINK("https://example.com")', workshop: 'Oficina teste', email: 'teste@example.com', whatsapp: '11998058438', employees: '6 a 10', revenue: 'De R$ 20 mil a R$ 50 mil', consent: true, consent_text: 'Autorizo contato', consent_at: '2026-10-09T23:00:00Z', created_at: '2026-10-09T23:00:00Z', source: 'https://example.com', utm: { utm_source: 'campanha' }, state: { lead_id: 'lead-1', stage: 'contact', notes: 'Retornar amanhã', follow_up: '2026-10-10', updated_at: '2026-10-09T23:10:00Z' },
};
describe('CRM Excel export', () => {
 it('includes all captured fields and follow-up without executing formula-like names', async () => {
  const workbook = new Workbook();
  await workbook.xlsx.load(await createLeadWorkbook([lead]));
  const sheet = workbook.getWorksheet('Leads');
  expect(sheet?.rowCount).toBe(2);
  expect(sheet?.getCell('C2').value).toBe(lead.name);
  expect(sheet?.getCell('E2').value).toBe('11998058438');
  expect(sheet?.getCell('J2').value).toBe('Em atendimento');
  expect(sheet?.getCell('L2').value).toBe('Retornar amanhã');
  expect(sheet?.getCell('O2').value).toBe('Autorizo contato');
  expect(sheet?.getCell('R2').value).toBe('{"utm_source":"campanha"}');
 });
 it('reads more than the API default row limit', async () => {
  const records = Array.from({ length: 1201 }, (_, id) => ({ id }));
  const result = await readAllCrmRows(async (from, to) => ({ data: records.slice(from, to + 1), error: null }));
  expect(result).toHaveLength(1201);
  expect(result[1200]?.id).toBe(1200);
 });
 it('rejects partial exports when a later page fails', async () => {
  await expect(readAllCrmRows(async from => from === 0 ? { data: [{ id: 1 }], error: null } : { data: null, error: 'connection' }, 1)).rejects.toThrow('Não foi possível carregar todos os leads.');
 });
});