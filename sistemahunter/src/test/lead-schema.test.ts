import { describe, expect, it } from 'vitest';
import { leadSchema, maskWhatsApp, employeeOptions, revenueOptions } from '@/lib/lead-schema';
const valid = {submission_id:'123e4567-e89b-42d3-a456-426614174000',name:'Maria Silva',workshop:'Oficina Teste',email:'maria@example.com',whatsapp:'(11) 99999-1234',employees:'2 a 5',revenue:'Prefiro não informar',consent:true,source:'https://example.com/',utm:{}};
describe('Hunter lead rules', () => {
 it('requires every mandatory field', () => { for(const field of ['name','workshop','email','whatsapp','employees','revenue']) expect(leadSchema.safeParse({...valid,[field]:''}).success).toBe(false); });
 it('requires explicit consent', () => { expect(leadSchema.safeParse({...valid,consent:false}).success).toBe(false); expect(leadSchema.safeParse(valid).success).toBe(true); });
 it('rejects invalid email', () => { expect(leadSchema.safeParse({...valid,email:'invalid'}).success).toBe(false); });
 it('requires a Brazilian mobile number with DDD', () => { expect(leadSchema.safeParse({...valid,whatsapp:'999991234'}).success).toBe(false); expect(leadSchema.parse(valid).whatsapp).toBe('11999991234'); });
 it('masks WhatsApp in Brazilian format', () => { expect(maskWhatsApp('11999991234')).toBe('(11) 99999-1234'); });
 it('accepts only the requested employee brackets', () => { expect(employeeOptions).toEqual(['Somente eu','2 a 5','6 a 10','11 a 20','Mais de 20']); expect(leadSchema.safeParse({...valid,employees:'100'}).success).toBe(false); });
 it('accepts the requested revenue brackets including opt-out', () => { expect(revenueOptions).toEqual(['Até R$ 20 mil','De R$ 20 mil a R$ 50 mil','De R$ 50 mil a R$ 100 mil','De R$ 100 mil a R$ 200 mil','Acima de R$ 200 mil','Prefiro não informar']); expect(leadSchema.safeParse({...valid,revenue:'Outro'}).success).toBe(false); });
});
