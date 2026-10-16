import { describe, it, expect } from 'vitest';
import { crmUpdateSchema, leadWhatsAppHref } from '@/lib/crm';
describe('CRM rules', () => {
 it('opens the captured Brazilian telephone on WhatsApp', () => { expect(leadWhatsAppHref('11998058438')).toBe('https://wa.me/5511998058438'); });
 it('accepts known stages and rejects arbitrary stages', () => { const input = { lead_id: '123e4567-e89b-42d3-a456-426614174000', stage: 'new', notes: '', follow_up: null }; expect(crmUpdateSchema.safeParse(input).success).toBe(true); expect(crmUpdateSchema.safeParse({ ...input, stage: 'administrator' }).success).toBe(false); });
});