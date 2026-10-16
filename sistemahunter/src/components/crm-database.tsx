import { ArrowUpRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table';
import { stages, leadStage, type CrmLead } from '@/lib/crm';
import { maskWhatsApp } from '@/lib/lead-schema';

export function CrmDatabase({ leads, open }: { leads: CrmLead[]; open: (id: string) => void }) {
  return <Table aria-label="Base de leads" className="crm-database"><TableHeader><TableRow>{['Nome', 'Oficina', 'WhatsApp', 'E-mail', 'Equipe', 'Faturamento mensal', 'Etapa', 'Recebido em', 'Próximo retorno', 'Ficha'].map(label => <TableHead key={label}>{label}</TableHead>)}</TableRow></TableHeader><TableBody>{leads.length === 0 && <TableRow><TableCell colSpan={10}>Nenhum lead encontrado.</TableCell></TableRow>}{leads.map(lead => <TableRow key={lead.id}><TableCell>{lead.name}</TableCell><TableCell>{lead.workshop}</TableCell><TableCell>{maskWhatsApp(lead.whatsapp)}</TableCell><TableCell>{lead.email}</TableCell><TableCell>{lead.employees}</TableCell><TableCell>{lead.revenue}</TableCell><TableCell>{stages.find(stage => stage.id === leadStage(lead))?.label}</TableCell><TableCell>{new Date(lead.created_at).toLocaleString('pt-BR')}</TableCell><TableCell>{lead.state?.follow_up?.split('-').reverse().join('/') ?? '—'}</TableCell><TableCell><Button size="icon" variant="ghost" title="Abrir ficha" aria-label={'Abrir ficha de '+lead.name} onClick={() => open(lead.id)}><ArrowUpRight size={17}/></Button></TableCell></TableRow>)}</TableBody></Table>;
}