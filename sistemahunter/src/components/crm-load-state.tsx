import { useEffect } from 'react';
import { useQueryErrorResetBoundary } from '@tanstack/react-query';
import { Link, useRouter, type ErrorComponentProps } from '@tanstack/react-router';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function CrmPending() {
  return <main className="crm-denied" aria-busy="true"><RefreshCw size={30}/><h1>Carregando atendimento…</h1></main>;
}

export function CrmLoadError({ reset }: ErrorComponentProps) {
  const router = useRouter();
  const queryError = useQueryErrorResetBoundary();
  useEffect(() => { queryError.reset(); }, [queryError.reset]);
  return <main className="crm-denied"><RefreshCw size={36}/><h1>Não foi possível conectar ao CRM</h1><p role="alert">Verifique sua conexão e tente novamente. Seus dados continuam salvos.</p><Button onClick={() => { queryError.reset(); void router.invalidate(); reset(); }}><RefreshCw size={17}/>Tentar novamente</Button><Button asChild variant="ghost"><Link to="/auth">Voltar ao login</Link></Button></main>;
}