import { useEffect, useState } from 'react';
import { useMutation, useQueryClient, useSuspenseQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Search, LogOut, MessageCircle, ArrowUpRight, X, Save, Users, CalendarDays, RefreshCw, Mail, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { supabase } from '@/integrations/supabase/client';
import { stages, leadStage, leadWhatsAppHref, type CrmLead } from '@/lib/crm';
import { saveCrmLead } from '@/lib/crm.functions';
import { crmQuery } from '@/lib/crm-query';
import { maskWhatsApp } from '@/lib/lead-schema';
import { CrmUsers } from '@/components/crm-users';
import { CrmDatabase } from '@/components/crm-database';
import { downloadLeadWorkbook } from '@/lib/crm-export';
import { Download, Columns3, Table2 } from 'lucide-react';
import logo from '@/assets/logo_sistema_hunter.png.asset.json';

const date = (value: string) => new Date(value).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
export function CrmBoard() {
 const { data, isRefetchError } = useSuspenseQuery(crmQuery);
 const queryClient = useQueryClient();
 const navigate = useNavigate();
 const [search, setSearch] = useState('');
 const [view, setView] = useState<'kanban' | 'database'>('kanban');
 const [exporting, setExporting] = useState(false);
 async function exportLeads() {
  setExporting(true); setError('');
  try { await downloadLeadWorkbook(visible); }
  catch { setError('Não foi possível exportar. Tente novamente.'); }
  finally { setExporting(false); }
 }
 const [selected, setSelected] = useState<string | null>(null);
 const [live, setLive] = useState(false);
 const [error, setError] = useState('');
 useEffect(() => {
  if (!data.authorized) return;
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: ['hunter-crm'] }); };
  const channel = supabase.channel('hunter-crm-operator').on('postgres_changes', { event: '*', schema: 'public', table: 'hunter_leads' }, refresh).on('postgres_changes', { event: '*', schema: 'public', table: 'hunter_crm_state' }, refresh).subscribe(status => { setLive(status === 'SUBSCRIBED'); if (status === 'SUBSCRIBED') refresh(); });
  const reconnect = () => refresh();
  window.addEventListener('online', reconnect);
  return () => { void supabase.removeChannel(channel); window.removeEventListener('online', reconnect); };
 }, [data.authorized, queryClient]);
 const mutation = useMutation({ mutationFn: (input: Parameters<typeof saveCrmLead>[0]) => saveCrmLead(input), onSuccess: () => { setError(''); void queryClient.invalidateQueries({ queryKey: ['hunter-crm'] }); }, onError: () => setError('Não foi possível salvar. Tente novamente.') });
 async function logout() { await queryClient.cancelQueries(); queryClient.clear(); await supabase.auth.signOut(); await navigate({ to: '/auth', replace: true }); }
 function move(lead: CrmLead, stage: string) { mutation.mutate({ data: { lead_id: lead.id, stage: stage as 'new' | 'contact' | 'demo' | 'negotiation' | 'won' | 'lost', notes: lead.state?.notes ?? '', follow_up: lead.state?.follow_up ?? null } }); }
 const visible = data.leads.filter(lead => `${lead.name} ${lead.workshop} ${lead.whatsapp} ${lead.email}`.toLowerCase().includes(search.toLowerCase()));
 const current = data.leads.find(lead => lead.id === selected);
 return <div className="crm-shell"><header className="crm-header"><img src={logo.url} alt="Hunter Auto"/><div className="crm-header-title"><span>Relacionamento</span><strong>CRM de atendimento</strong></div><div className="crm-account-actions">{data.authorized && <CrmUsers/>}<Button variant="ghost" size="icon" title="Sair" aria-label="Sair" onClick={logout}><LogOut size={19}/></Button></div></header>
 {!data.authorized ? <main className="crm-denied"><Users size={36}/><h1>Acesso restrito</h1><p>Esta conta não está autorizada a acessar os contatos.</p><Button onClick={logout}>Trocar conta</Button></main> : <main className="crm-main"><div className="crm-title-row"><div className="min-w-0"><span className="eyebrow">HUNTER AUTO · COMERCIAL</span><h1>Atendimento de leads</h1></div><span className="crm-live"><i data-live={live}/>{live ? 'Ao vivo' : 'Reconectando'}</span></div><div className="crm-stats"><div><span>Total de leads</span><strong>{data.leads.length}</strong></div><div><span>Aguardando atendimento</span><strong>{data.leads.filter(lead => leadStage(lead) === 'new').length}</strong></div><div><span>Em negociação</span><strong>{data.leads.filter(lead => leadStage(lead) === 'negotiation').length}</strong></div><div><span>Convertidos</span><strong>{data.leads.filter(lead => leadStage(lead) === 'won').length}</strong></div></div><div className="crm-data-actions"><div role="group" aria-label="Visualização dos leads"><Button variant={view === 'kanban' ? 'default' : 'outline'} aria-pressed={view === 'kanban'} onClick={() => setView('kanban')}><Columns3 size={16}/>Kanban</Button><Button variant={view === 'database' ? 'default' : 'outline'} aria-pressed={view === 'database'} onClick={() => setView('database')}><Table2 size={16}/>Base de leads</Button></div><Button variant="outline" disabled={exporting || visible.length === 0} onClick={() => void exportLeads()}><Download size={16}/>{exporting ? 'Exportando…' : search ? 'Exportar resultados' : 'Exportar Excel'}</Button></div><div className="crm-toolbar"><label className="crm-search"><Search size={18}/><input aria-label="Buscar leads" placeholder="Buscar nome, oficina, telefone ou e-mail" value={search} onChange={event => setSearch(event.target.value)}/></label><Button variant="outline" size="icon" title="Atualizar leads" aria-label="Atualizar leads" onClick={() => queryClient.invalidateQueries({ queryKey: ['hunter-crm'] })}><RefreshCw size={17}/></Button><span>{visible.length} contatos</span></div>{error && <p role="alert" className="form-error">{error}</p>}{view === 'database' ? <CrmDatabase leads={visible} open={setSelected}/> : <div className="crm-kanban">{stages.map(stage => { const leads = visible.filter(lead => leadStage(lead) === stage.id); return <section className={'crm-column crm-stage-'+stage.id} key={stage.id} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); const lead = data.leads.find(item => item.id === event.dataTransfer.getData('text/plain')); if (lead && !mutation.isPending) move(lead, stage.id); }}><header><span className="crm-stage-dot"/><h2>{stage.label}</h2><span>{leads.length}</span></header><div className="crm-column-body">{leads.length === 0 && <div className="crm-empty">Nenhum lead nesta etapa</div>}{leads.map(lead => <article className="crm-lead" key={lead.id} draggable={!mutation.isPending} onDragStart={event => event.dataTransfer.setData('text/plain', lead.id)}><div className="crm-card-heading"><span className="crm-avatar">{lead.name.slice(0,1).toUpperCase()}</span><div className="min-w-0"><h3>{lead.name}</h3><p>{lead.workshop}</p></div><GripVertical size={15}/></div><p className="crm-phone">{maskWhatsApp(lead.whatsapp)}</p><div className="crm-card-meta"><span><Users size={12}/>{lead.employees}</span><span>{lead.revenue}</span></div>{lead.state?.follow_up && <p className="crm-followup"><CalendarDays size={13}/>Retorno: {lead.state.follow_up.split('-').reverse().join('/')}</p>}<div className="crm-card-footer"><small>{date(lead.created_at)}</small><Button size="icon" variant="ghost" title="Abrir ficha" aria-label={'Abrir ficha de '+lead.name} onClick={() => setSelected(lead.id)}><ArrowUpRight size={17}/></Button><Button asChild variant="ghost" size="icon"><a href={leadWhatsAppHref(lead.whatsapp)} target="_blank" rel="noopener noreferrer" aria-label={'WhatsApp de '+lead.name} title="Abrir WhatsApp"><MessageCircle size={17}/></a></Button></div><select aria-label={'Etapa de '+lead.name} value={leadStage(lead)} disabled={mutation.isPending} onChange={event => move(lead,event.target.value)}>{stages.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></article>)}</div></section>; })}</div>}</main>}
 {isRefetchError && <p role="alert" className="form-error px-6 pb-4">A conexão foi interrompida. Os últimos dados carregados estão sendo mantidos; tentando atualizar novamente.</p>}
 {current && <LeadDetail key={current.id} lead={current} close={() => setSelected(null)} save={input => mutation.mutate({ data: input }, { onSuccess: () => setSelected(null) })} saving={mutation.isPending} error={error}/>}
 </div>;
}

function LeadDetail({ lead, close, save, saving, error }: { lead: CrmLead; close: () => void; save: (input: { lead_id: string; stage: 'new' | 'contact' | 'demo' | 'negotiation' | 'won' | 'lost'; notes: string; follow_up: string | null }) => void; saving: boolean; error: string }) {
 const [stage,setStage] = useState(leadStage(lead));
 const [notes,setNotes] = useState(lead.state?.notes ?? '');
 const [followUp,setFollowUp] = useState(lead.state?.follow_up ?? '');
 return <Dialog open onOpenChange={open => { if (!open) close(); }}><DialogContent className="crm-detail"><DialogTitle>{lead.name}</DialogTitle><DialogDescription>{lead.workshop}</DialogDescription><div className="crm-detail-actions"><Button asChild variant="conversion"><a href={leadWhatsAppHref(lead.whatsapp)} target="_blank" rel="noopener noreferrer"><MessageCircle size={17}/>WhatsApp</a></Button><Button asChild variant="outline"><a href={'mailto:'+lead.email}><Mail size={17}/>E-mail</a></Button></div><dl className="crm-fields">{[['Telefone',maskWhatsApp(lead.whatsapp)],['E-mail',lead.email],['Equipe',lead.employees],['Faturamento mensal',lead.revenue],['Recebido em',date(lead.created_at)],['Origem',lead.source],['Consentimento',lead.consent ? 'Autorizado em '+date(lead.consent_at) : 'Não autorizado'],['Autorização',lead.consent_text],...Object.entries(lead.utm ?? {}).map(([key,value]) => [key,String(value)])].map(([label,value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><form className="crm-detail-form" onSubmit={event => { event.preventDefault(); save({ lead_id: lead.id, stage: stage as 'new' | 'contact' | 'demo' | 'negotiation' | 'won' | 'lost', notes, follow_up: followUp || null }); }}><label>Etapa do atendimento<select value={stage} onChange={event => setStage(event.target.value)}>{stages.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label>Próximo retorno<input type="date" value={followUp} onChange={event => setFollowUp(event.target.value)}/></label><label>Anotações<textarea rows={4} maxLength={10000} value={notes} onChange={event => setNotes(event.target.value)}/></label>{error && <p role="alert" className="form-error">{error}</p>}<Button type="submit" variant="conversion" disabled={saving}><Save size={16}/>{saving ? 'Salvando…' : 'Salvar atendimento'}</Button></form></DialogContent></Dialog>;
}