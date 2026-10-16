REVOKE ALL ON public.profiles FROM anon, authenticated; GRANT SELECT ON public.profiles TO authenticated; GRANT UPDATE(display_name) ON public.profiles TO authenticated; GRANT ALL ON public.profiles TO service_role;
REVOKE ALL ON public.hunter_crm_invites FROM anon, authenticated; GRANT SELECT ON public.hunter_crm_invites TO authenticated; GRANT ALL ON public.hunter_crm_invites TO service_role;
CREATE OR REPLACE FUNCTION public.manage_hunter_invitation(p_name text,p_email text,p_phone text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ BEGIN
 IF NOT public.is_hunter_admin() THEN RAISE EXCEPTION 'Unauthorized'; END IF;
 IF length(trim(p_name)) NOT BETWEEN 1 AND 100 OR p_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' OR length(p_email)>254 THEN RAISE EXCEPTION 'Invalid invitation'; END IF;
 INSERT INTO public.hunter_crm_invites(display_name,email,phone,created_by) VALUES(trim(p_name),lower(trim(p_email)),nullif(p_phone,''),auth.uid()) ON CONFLICT(email) DO UPDATE SET display_name=EXCLUDED.display_name,phone=EXCLUDED.phone,active=true;
 END; $$;