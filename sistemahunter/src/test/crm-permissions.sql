-- Run in a transaction with a privileged test connection; creates no users or lead rows.
BEGIN;
DO $$ BEGIN
 IF has_table_privilege('anon','public.profiles','SELECT') THEN RAISE EXCEPTION 'Visitor profiles must be private'; END IF;
 IF has_table_privilege('authenticated','public.hunter_crm_invites','INSERT') THEN RAISE EXCEPTION 'Invitations require admin function'; END IF;
 IF position('is_hunter_admin' in pg_get_functiondef('public.manage_hunter_invitation(text,text,text)'::regprocedure)) = 0 THEN RAISE EXCEPTION 'Only administrators invite'; END IF;
 IF has_table_privilege('anon','public.hunter_leads','SELECT') THEN RAISE EXCEPTION 'Visitors must not read leads'; END IF;
 IF has_table_privilege('anon','public.hunter_crm_state','UPDATE') THEN RAISE EXCEPTION 'Visitors must not modify follow-up'; END IF;
 IF has_table_privilege('authenticated','public.user_roles','INSERT') THEN RAISE EXCEPTION 'Users must not grant themselves access'; END IF;
 IF position('bossensino@gmail.com' in pg_get_functiondef('public.enroll_hunter_operator()'::regprocedure)) = 0 THEN RAISE EXCEPTION 'Authorized operator must match supplied email'; END IF;
 IF position('email_confirmed_at IS NOT NULL' in pg_get_functiondef('public.enroll_hunter_operator()'::regprocedure)) = 0 THEN RAISE EXCEPTION 'Operator email must be verified'; END IF;
END $$;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims','{"sub":"123e4567-e89b-42d3-a456-426614174000","role":"authenticated"}',true);
DO $$ BEGIN
 IF public.is_hunter_operator() THEN RAISE EXCEPTION 'Unassigned user must not be an operator'; END IF;
 IF EXISTS(SELECT 1 FROM public.hunter_leads) THEN RAISE EXCEPTION 'Unassigned users must not read leads'; END IF;
 IF EXISTS(SELECT 1 FROM public.hunter_crm_state) THEN RAISE EXCEPTION 'Unassigned users must not read notes'; END IF;
END $$;
ROLLBACK;