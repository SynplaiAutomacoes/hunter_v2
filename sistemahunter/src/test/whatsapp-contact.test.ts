import { describe, expect, it } from 'vitest';
import { whatsappContactHref } from '@/lib/whatsapp-contact';

describe('Hunter Auto WhatsApp contact', () => {
  it('targets the supplied Brazilian phone number', () => {
    expect(new URL(whatsappContactHref).pathname).toBe('/5511998058438');
  });
  it('prefills the supplied message', () => {
    expect(new URL(whatsappContactHref).searchParams.get('text')).toBe('Quero conhecer melhor o sistema.');
  });
});