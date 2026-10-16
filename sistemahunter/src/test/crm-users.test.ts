import { describe,it,expect } from 'vitest';
import { invitationSchema, smsPhoneSchema, otpSchema } from '@/lib/crm-users';
describe('CRM invitations and SMS', () => {
 it('requires the invited Google email and name', () => { expect(invitationSchema.safeParse({ name:'',email:'bad',phone:'' }).success).toBe(false); expect(invitationSchema.parse({ name:'Atendente',email:'TEAM@example.com',phone:'' }).email).toBe('team@example.com'); });
 it('normalizes Brazilian SMS phones', () => { expect(smsPhoneSchema.parse('(11) 99805-8438')).toBe('5511998058438'); expect(smsPhoneSchema.parse('+55 11 99805-8438')).toBe('5511998058438'); expect(smsPhoneSchema.safeParse('123').success).toBe(false); });
 it('requires six numeric OTP digits', () => { expect(otpSchema.safeParse('123456').success).toBe(true); expect(otpSchema.safeParse('12345a').success).toBe(false); });
});