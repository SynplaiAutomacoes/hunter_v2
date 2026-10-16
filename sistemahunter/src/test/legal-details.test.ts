import { describe, expect, it } from 'vitest';
import { legalDetails, privacyContactHref } from '@/lib/legal-details';

describe('Supplied Hunter Auto legal details', () => {
  it('identifies the supplier with the supplied legal name', () => {
    expect(legalDetails.supplierLegalName).toBe('Boss Ensino e Consultoria LTDA');
  });
  it('uses the supplied supplier address', () => {
    expect(legalDetails.supplierAddress).toBe('Av Guacy Fernandes Domingues, 85, Embu Mirim, Itapecerica da Serra SP');
  });
  it('identifies the supplier with the supplied CNPJ', () => {
    expect(legalDetails.supplierCnpj).toBe('52.198.562/0001-95');
  });
  it('directs privacy requests to the official email', () => {
    expect(privacyContactHref).toBe('mailto:bossensino@gmail.com');
  });
  it('sets the stated retention period to two years', () => {
    expect(legalDetails.retentionYears).toBe(2);
  });
  it('accepts deletion requests by email', () => {
    expect(legalDetails.deletionRequestMethod).toBe('email');
  });
});