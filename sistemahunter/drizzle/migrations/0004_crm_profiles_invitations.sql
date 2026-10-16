CREATE OR REPLACE FUNCTION public.is_hunter_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$ SELECT EXISTS(SELECT 1 FROM public.user_roles WHERE user_id=auth.uid() AND role='admin'); $$;
REVOKE ALL ON FUNCTION public.is_hunter_admin() FROM PUBLIC; GRANT EXECUTE ON FUNCTION public.is_hunter_admin() TO authenticated;
CREATE TABLE public.profiles (id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE, display_name text NOT NULL DEFAULT '' CHECK(length(display_name)<=100), created_at timestamptz NOT NULL DEFAULT now());
GRANT SELECT ON public.profiles TO authenticated; GRANT UPDATE(display_name) ON public.profiles TO authenticated; GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Own or admin profile read" ON public.profiles FOR SELECT TO authenticated USING(id=auth.uid() OR public.is_hunter_admin());
CREATE POLICY "Own profile name update" ON public.profiles FOR UPDATE TO authenticated USING(id=auth.uid()) WITH CHECK(id=auth.uid());
CREATE TABLE public.hunter_crm_invites (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), display_name text NOT NULL CHECK(length(display_name) BETWEEN 1 AND 100), email text NOT NULL UNIQUE CHECK(length(email)<=254), phone text UNIQUE CHECK(phone ~ '^55[1-9][0-9]{10}$'), active boolean NOT NULL DEFAULT true, created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
GRANT SELECT ON public.hunter_crm_invites TO authenticated; GRANT ALL ON public.hunter_crm_invites TO service_role;
ALTER TABLE public.hunter_crm_invites ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Admins read invitations" ON public.hunter_crm_invites FOR SELECT TO authenticated USING(public.is_hunter_admin());
CREATE OR REPLACE FUNCTION public.enroll_hunter_operator() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ DECLARE invited_name text; BEGIN
 INSERT INTO public.profiles(id,display_name) VALUES(NEW.id,'') ON CONFLICT DO NOTHING;
 IF lower(NEW.email)='bossensino@gmail.com' AND NEW.email_confirmed_at IS NOT NULL THEN
  INSERT INTO public.user_roles(user_id,role) VALUES(NEW.id,'admin'),(NEW.id,'operator') ON CONFLICT DO NOTHING;
 ELSE
  SELECT display_name INTO invited_name FROM public.hunter_crm_invites WHERE active AND ((lower(email)=lower(NEW.email) AND NEW.email_confirmed_at IS NOT NULL) OR (phone=NEW.phone AND NEW.phone_confirmed_at IS NOT NULL)) LIMIT 1;
  IF invited_name IS NOT NULL THEN INSERT INTO public.user_roles(user_id,role) VALUES(NEW.id,'operator') ON CONFLICT DO NOTHING; UPDATE public.profiles SET display_name=invited_name WHERE id=NEW.id AND display_name=''; END IF;
 END IF; RETURN NEW; END; $$;
INSERT INTO public.profiles(id) SELECT id FROM auth.users ON CONFLICT DO NOTHING;
INSERT INTO public.user_roles(user_id,role) SELECT id,'admin'::public.hunter_crm_role FROM auth.users WHERE lower(email)='bossensino@gmail.com' AND email_confirmed_at IS NOT NULL ON CONFLICT DO NOTHING;
CREATE OR REPLACE FUNCTION public.claim_hunter_invitation() RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ DECLARE u record; n text; BEGIN
 SELECT id,email,phone,email_confirmed_at,phone_confirmed_at INTO u FROM auth.users WHERE id=auth.uid();
 IF u.id IS NULL THEN RAISE EXCEPTION 'Unauthorized'; END IF;
 SELECT display_name INTO n FROM public.hunter_crm_invites WHERE active AND ((lower(email)=lower(u.email) AND u.email_confirmed_at IS NOT NULL) OR (phone=u.phone AND u.phone_confirmed_at IS NOT NULL)) LIMIT 1;
 IF n IS NOT NULL THEN INSERT INTO public.user_roles(user_id,role) VALUES(u.id,'operator') ON CONFLICT DO NOTHING; UPDATE public.profiles SET display_name=n WHERE id=u.id AND display_name=''; END IF; END; $$;
REVOKE ALL ON FUNCTION public.claim_hunter_invitation() FROM PUBLIC; GRANT EXECUTE ON FUNCTION public.claim_hunter_invitation() TO authenticated;
CREATE OR REPLACE FUNCTION public.manage_hunter_invitation(p_name text,p_email text,p_phone text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ BEGIN
 IF NOT public.is_hunter_admin() THEN RAISE EXCEPTION 'Unauthorized'; END IF;
 IF length(trim(p_name)) NOT BETWEEN 1 AND 100 OR p_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' OR length(p_email)>254 THEN RAISE EXCEPTION 'Invalid invitation'; END IF;
 INSERT INTO public.hunter_crm_invites(display_name,email,phone,created_by) VALUES(trim(p_name),lower(trim(p_email)),p_phone,auth.uid()) ON CONFLICT(email) DO UPDATE SET display_name=EXCLUDED.display_name,phone=EXCLUDED.phone,active=true;
 END; $$;
CREATE OR REPLACE FUNCTION public.revoke_hunter_invitation(p_id uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$ DECLARE i record; BEGIN
 IF NOT public.is_hunter_admin() THEN RAISE EXCEPTION 'Unauthorized'; END IF;
 SELECT * INTO i FROM public.hunter_crm_invites WHERE id=p_id;
 UPDATE public.hunter_crm_invites SET active=false WHERE id=p_id;
 DELETE FROM public.user_roles r USING auth.users u WHERE r.user_id=u.id AND r.role='operator' AND (lower(u.email)=i.email OR u.phone=i.phone) AND NOT EXISTS(SELECT 1 FROM public.user_roles a WHERE a.user_id=u.id AND a.role='admin');
 END; $$;
REVOKE ALL ON FUNCTION public.manage_hunter_invitation(text,text,text),public.revoke_hunter_invitation(uuid) FROM PUBLIC; GRANT EXECUTE ON FUNCTION public.manage_hunter_invitation(text,text,text),public.revoke_hunter_invitation(uuid) TO authenticated;