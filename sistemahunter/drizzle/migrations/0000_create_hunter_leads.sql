CREATE TABLE public.hunter_leads (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 submission_id uuid NOT NULL UNIQUE,
 name text NOT NULL CHECK (char_length(name) BETWEEN 3 AND 120),
 workshop text NOT NULL CHECK (char_length(workshop) BETWEEN 2 AND 160),
 email text NOT NULL CHECK (char_length(email) <= 254 AND email ~ '^[^\s@]+@[^\s@]+\.[^\s@]+$'),
 whatsapp text NOT NULL CHECK (whatsapp ~ '^[1-9][0-9]9[0-9]{8}$'),
 employees text NOT NULL CHECK (employees IN ('Somente eu','2 a 5','6 a 10','11 a 20','Mais de 20')),
 revenue text NOT NULL CHECK (revenue IN ('Até R$ 20 mil','De R$ 20 mil a R$ 50 mil','De R$ 50 mil a R$ 100 mil','De R$ 100 mil a R$ 200 mil','Acima de R$ 200 mil','Prefiro não informar')),
 consent boolean NOT NULL CHECK (consent = true),
 consent_text text NOT NULL,
 consent_at timestamptz NOT NULL DEFAULT now(),
 created_at timestamptz NOT NULL DEFAULT now(),
 source text NOT NULL CHECK (char_length(source) <= 2048),
 utm jsonb NOT NULL DEFAULT '{}'::jsonb
);
GRANT INSERT ON public.hunter_leads TO anon, authenticated;
GRANT ALL ON public.hunter_leads TO service_role;
ALTER TABLE public.hunter_leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Visitors may submit consented leads" ON public.hunter_leads FOR INSERT TO anon, authenticated WITH CHECK (consent = true);