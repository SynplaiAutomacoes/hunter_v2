import { createFileRoute } from '@tanstack/react-router';
import { crmQuery } from '@/lib/crm-query';
import { CrmBoard } from '@/components/crm-board';
import { CrmLoadError, CrmPending } from '@/components/crm-load-state';

const title = 'CRM de Atendimento | Hunter Auto';
const description = 'Área privada de atendimento e acompanhamento de leads Hunter Auto.';
export const Route = createFileRoute('/_authenticated/crm')({
  head: () => ({ meta: [{ title }, { name: 'description', content: description }, { property: 'og:title', content: title }, { property: 'og:description', content: description }, { property: 'og:type', content: 'website' }, { name: 'twitter:card', content: 'summary' }, { name: 'robots', content: 'noindex,nofollow' }] }),
  loader: ({ context }) => context.queryClient.ensureQueryData(crmQuery),
  component: CrmBoard,
  pendingComponent: CrmPending,
  errorComponent: CrmLoadError,
});