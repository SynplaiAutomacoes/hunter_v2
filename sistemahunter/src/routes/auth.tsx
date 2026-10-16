import { createFileRoute, Link, useNavigate } from '@tanstack/react-router';
import { useEffect, useState } from 'react';
import { ShieldCheck, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { lovable } from '@/integrations/lovable';
import { supabase } from '@/integrations/supabase/client';
import { SmsLogin } from '@/components/sms-login';
import logo from '@/assets/logo_sistema_hunter.png.asset.json';

const title = 'Acesso ao CRM | Hunter Auto';
const description = 'Acesso privado ao CRM comercial Hunter Auto.';
export const Route = createFileRoute('/auth')({ head: () => ({ meta: [{ title }, { name: 'description', content: description }, { property: 'og:title', content: title }, { property: 'og:description', content: description }, { property: 'og:type', content: 'website' }, { name: 'twitter:card', content: 'summary' }, { name: 'robots', content: 'noindex,nofollow' }] }), component: Auth });
function Auth() {
 const navigate = useNavigate();
 const [signedIn,setSignedIn] = useState(false);
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 const [method,setMethod] = useState<'google'|'sms'>('google');
 useEffect(() => { void supabase.auth.getSession().then(({ data }) => { setSignedIn(Boolean(data.session)); if (data.session) void navigate({ to: '/crm' }); }); }, [navigate]);
 async function login() { setBusy(true); setError(''); try { const result = await lovable.auth.signInWithOAuth('google', { redirect_uri: window.location.origin+'/auth' }); if (result.error) setError('Não foi possível entrar com o Google. Tente novamente.'); if (!result.redirected && !result.error) await navigate({ to: '/crm' }); } catch { setError('Não foi possível entrar. Tente novamente.'); } finally { setBusy(false); } }
 return <main className="crm-auth"><img src={logo.url} alt="Hunter Auto"/><div className="crm-auth-body"><ShieldCheck size={32}/><span className="eyebrow">ÁREA COMERCIAL</span><h1>Seu atendimento.<br/>Em um só lugar.</h1><p>Acesso privado da equipe Hunter Auto.</p>{!signedIn && <div className="crm-login-methods"><Button variant={method === 'google' ? 'outline' : 'ghost'} onClick={() => setMethod('google')}>Google</Button><Button variant={method === 'sms' ? 'outline' : 'ghost'} onClick={() => setMethod('sms')}>Código SMS</Button></div>}{signedIn ? <Button variant="conversion" onClick={() => navigate({ to: '/crm' })}>Abrir CRM<ArrowRight size={18}/></Button> : method === 'sms' ? <SmsLogin onSuccess={() => navigate({ to: '/crm' })}/> : <Button variant="conversion" onClick={login} disabled={busy}>{busy ? 'Entrando…' : 'Entrar com Google'}<ArrowRight size={18}/></Button>}{error && <p className="form-error" role="alert">{error}</p>}<Link to="/">Voltar ao site Hunter Auto</Link></div></main>;
}