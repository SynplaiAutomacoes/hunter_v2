/*
 * Formatação (widgets + tabelas)
 * -----------------------------
 * Este arquivo centraliza regras de formatação/normalização de valores (CPF/CNPJ,
 * CEP, telefone, RG, moeda, duração e números) e também a integração com o DOM.
 *
 * 1) Widgets (inputs) com Alpine
 *    - Os templates chamam factories em `window.formatters.widget.*` via `x-data`.
 *    - Cada factory mantém:
 *        - um input visível (apenas UI) com a máscara/formatado
 *        - um input hidden (valor “raw”) que é o que vai no POST
 *
 * 2) Tabelas (apenas exibição) via `data-hf`
 *    - Para formatar qualquer texto renderizado no HTML, use:
 *        - `data-hf="<kind>"` (ex.: "cnpj", "cpf", "phone", "money")
 *        - opcional `data-hf-raw="..."` com o valor fonte (recomendado)
 *    - O script varre o DOM e substitui `textContent` pelo valor formatado.
 *    - A aplicação é automática:
 *        - no `DOMContentLoaded` (página inicial)
 *        - e após swaps do HTMX (`htmx:afterSwap`) apenas no `e.target`.
 *
 * Observações:
 * - Se o valor estiver vazio/undefined, os formatadores retornam string vazia.
 * - Valores `None` em tabelas devem ser tratados no template (exibindo "None")
 *   e não recebem `data-hf`.
 *
 * Formatos suportados (kind): cpf, cnpj, cpf_cnpj/cpfcnpj/cpf_or_cnpj, cep,
 * phone/telefone, rg, money.
 */
(function () {
    const onlyDigits = (v) => (v ?? '').toString().replace(/\D/g, '');

    const doc = {
        formatCpf(d) {
            d = onlyDigits(d).slice(0, 11);
            if (!d) return '';
            d = d.replace(/^(\d{3})(\d)/, '$1.$2');
            d = d.replace(/^(\d{3})\.(\d{3})(\d)/, '$1.$2.$3');
            d = d.replace(/^(\d{3})\.(\d{3})\.(\d{3})(\d{1,2})$/, '$1.$2.$3-$4');
            return d;
        },
        formatCnpj(d) {
            d = onlyDigits(d).slice(0, 14);
            if (!d) return '';
            d = d.replace(/^(\d{2})(\d)/, '$1.$2');
            d = d.replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3');
            d = d.replace(/^(\d{2})\.(\d{3})\.(\d{3})(\d)/, '$1.$2.$3/$4');
            d = d.replace(/^(\d{2})\.(\d{3})\.(\d{3})\/(\d{4})(\d{1,2})$/, '$1.$2.$3/$4-$5');
            return d;
        },
        formatCpfOrCnpj(d) {
            const digits = onlyDigits(d);
            if (!digits) return '';
            return digits.length <= 11 ? this.formatCpf(digits) : this.formatCnpj(digits);
        },
    };

    const cep = {
        normalize(v) {
            return onlyDigits(v).slice(0, 8);
        },
        format(v) {
            const d = this.normalize(v);
            if (!d) return '';
            if (d.length <= 5) return d;
            return d.slice(0, 5) + '-' + d.slice(5);
        },
    };

    const phone = {
        normalizeToE164BR(v) {
            let d = onlyDigits(v);
            if (d.startsWith('55')) d = d.slice(2);
            d = d.slice(0, 11);
            if (!d) return '';
            return '+55' + d;
        },
        formatBRFromDigits(v) {
            const d = onlyDigits(v).replace(/^55/, '').slice(0, 11);
            if (!d) return '';

            const dd = d.slice(0, 2);
            const rest = d.slice(2);

            if (d.length <= 2) return `(${dd}`;
            if (rest.length <= 5) return `(${dd}) ${rest}`;

            const first = rest.slice(0, 5);
            const last = rest.slice(5, 9);
            return `(${dd}) ${first}-${last}`;
        },
        formatFromE164BR(v) {
            // Aceita +55..., 55..., ou só dígitos.
            let d = onlyDigits(v);
            if (d.startsWith('55')) d = d.slice(2);
            return this.formatBRFromDigits(d);
        },
    };

    const rg = {
        normalize(v) {
            let s = (v ?? '').toString().toUpperCase();
            s = s.replace(/[^0-9X]/g, '');
            s = s.replace(/X+/g, 'X');
            if (s.includes('X')) {
                s = s.replace(/X/g, '');
                s = s + 'X';
            }
            if (s.length > 9) s = s.slice(0, 9);
            return s;
        },
        format(v) {
            const normalized = this.normalize(v);
            if (!normalized) return '';
            if (normalized.length <= 1) return normalized;

            let body = normalized.slice(0, -1);
            const dv = normalized.slice(-1);

            body = onlyDigits(body).slice(0, 8);

            if (body.length > 2) body = body.slice(0, 2) + '.' + body.slice(2);
            if (body.length > 6) body = body.slice(0, 6) + '.' + body.slice(6);

            return body + '-' + dv;
        },
    };

    const money = {
        // Normaliza entrada livre -> string com '.' e 2 casas (ex: '1234.56')
        normalizeToDotDecimal(value, maxDigits = 14) {
            let digits = onlyDigits(value);
            if (digits === '') return '';
            if (digits.length > maxDigits) digits = digits.slice(0, maxDigits);
            return (parseInt(digits, 10) / 100).toFixed(2);
        },
        formatPtBrFromDotDecimal(dotDecimal) {
            if (!dotDecimal) return '';
            const n = Number(dotDecimal);
            if (Number.isNaN(n)) return '';
            return n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },
    };

    const duration = {
        toHHMM(value) {
            let d = onlyDigits(value).slice(0, 4);
            if (!d) return { hh: '', mm: '' };
            let hh = d.slice(0, 2);
            let mm = d.slice(2, 4);
            if (mm.length === 2) {
                let m = parseInt(mm, 10);
                if (Number.isNaN(m)) m = 0;
                if (m > 59) m = 59;
                mm = String(m).padStart(2, '0');
            }
            return { hh, mm };
        },
        formatDisplay(hh, mm) {
            if (!hh && !mm) return '';
            if (hh && !mm) return hh;
            return `${hh}:${mm}`;
        },
        normalizeForPost(hh, mm) {
            if ((hh ?? '').length !== 2 || (mm ?? '').length !== 2) return '';
            return `${hh}:${mm}:00`;
        },
        initFromRaw(raw) {
            const s = (raw ?? '').toString();
            const m = s.match(/(\d{1,2}):(\d{2})(?::\d{2})?/);
            if (!m) return { hh: '', mm: '' };
            const hh = String(parseInt(m[1], 10)).padStart(2, '0').slice(0, 2);
            const mm = String(parseInt(m[2], 10)).padStart(2, '0');
            return { hh, mm };
        },
    };

    const number = {
        normalize(v, mode = 'positive') {
            let s = (v ?? '').toString().trim();
            s = s.replace(/[^\d-]/g, '');
            s = s.replace(/-/g, '');
            const wantMinus = ((v ?? '').toString().trim().startsWith('-'));
            if (wantMinus) s = '-' + s;
            if (s === '-') return s;

            const sign = s.startsWith('-') ? '-' : '';
            let digits = s.replace(/-/g, '');
            digits = digits.replace(/^0+(?=\d)/, '');
            if (!digits) return '';

            if (mode === 'positive') return digits;
            if (mode === 'negative') return '-' + digits;
            return sign + digits;
        },
    };

    function formatValue(kind, raw) {
        const k = (kind ?? '').toString().toLowerCase();
        if (!raw && raw !== 0) return '';

        if (k === 'cpf') return doc.formatCpf(raw);
        if (k === 'cnpj') return doc.formatCnpj(raw);
        if (k === 'cpf_cnpj' || k === 'cpfcnpj' || k === 'cpf_or_cnpj') return doc.formatCpfOrCnpj(raw);
        if (k === 'cep') return cep.format(raw);
        if (k === 'phone' || k === 'telefone') return phone.formatFromE164BR(raw);
        if (k === 'rg') return rg.format(raw);
        if (k === 'money') {
            // Tenta interpretar valor já vindo como dot-decimal; se não, normaliza como digitado.
            const s = (raw ?? '').toString();
            const dotDecimal = /^-?\d+(?:\.\d+)?$/.test(s) ? s : money.normalizeToDotDecimal(s);
            return money.formatPtBrFromDotDecimal(dotDecimal);
        }
        return (raw ?? '').toString();
    }

    function applyFormats(root) {
        const scope = root || document;
        scope.querySelectorAll('[data-hf]').forEach((el) => {
            const kind = el.dataset.hf;
            const raw = (el.dataset.hfRaw ?? el.textContent ?? '').toString();
            const formatted = formatValue(kind, raw);
            el.textContent = formatted;
        });
    }

    // Auto-aplica em páginas e após swaps HTMX.
    document.addEventListener('DOMContentLoaded', () => applyFormats(document));
    document.addEventListener('htmx:afterSwap', (e) => applyFormats(e.target));

    //TODO: Estamos normalizando o valor duas vezes, uma vez para o input e outra para o display. Podemos melhorar isso posteriormente.
    const widget = {
        cepInput(raw) {
            return {
                rawValue: raw ?? '',
                init() {
                    const n = cep.normalize(this.rawValue);
                    this.$refs.value.value = n;
                    this.$refs.display.value = cep.format(n);
                },
                handleInput(e) {
                    const normalized = cep.normalize(e.target.value);
                    this.$refs.value.value = normalized;
                    e.target.value = cep.format(normalized);
                },
            };
        },
        docInput(raw, docMode) {
            return {
                rawValue: raw ?? '',
                docMode: (docMode || 'both').toString(),
                mode() {
                    return (this.docMode || 'both').toLowerCase();
                },
                maxDigitsForMode(digits) {
                    const m = this.mode();
                    if (m === 'cpf') return 11;
                    if (m === 'cnpj') return 14;
                    return digits.length <= 11 ? 11 : 14;
                },
                format(digits) {
                    if (!digits) return '';
                    const m = this.mode();
                    if (m === 'cpf') return doc.formatCpf(digits);
                    if (m === 'cnpj') return doc.formatCnpj(digits);
                    return doc.formatCpfOrCnpj(digits);
                },
                init() {
                    let d = onlyDigits(this.rawValue);
                    const maxDigits = this.maxDigitsForMode(d);
                    d = d.slice(0, maxDigits);
                    this.$refs.value.value = d;
                    this.$refs.display.value = this.format(d);
                },
                handleInput(e) {
                    let digits = onlyDigits(e.target.value);
                    const maxDigits = this.maxDigitsForMode(digits);
                    if (digits.length > maxDigits) digits = digits.slice(0, maxDigits);
                    this.$refs.value.value = digits;
                    e.target.value = this.format(digits);
                },
            };
        },
        durationInput(raw) {
            return {
                rawValue: raw ?? '',
                init() {
                    const { hh, mm } = duration.initFromRaw(this.rawValue);
                    this.$refs.value.value = duration.normalizeForPost(hh, mm);
                    this.$refs.display.value = duration.formatDisplay(hh, mm);
                },
                handleInput(e) {
                    const { hh, mm } = duration.toHHMM(e.target.value);
                    this.$refs.value.value = duration.normalizeForPost(hh, mm);
                    e.target.value = duration.formatDisplay(hh, mm);
                },
            };
        },
        moneyInput(rawDotDecimal) {
            return {
                rawValue: (rawDotDecimal ?? '').toString(),
                maxDigits: 14,
                init() {
                    this.$refs.amount.value = this.rawValue;
                    this.$refs.display.value = money.formatPtBrFromDotDecimal(this.rawValue);
                },
                handleInput(e) {
                    const normalized = money.normalizeToDotDecimal(e.target.value, this.maxDigits);
                    this.$refs.amount.value = normalized;
                    e.target.value = money.formatPtBrFromDotDecimal(normalized);
                },
            };
        },
        numberInput(raw, mode) {
            return {
                rawValue: raw ?? '',
                mode: (mode || 'positive').toString(),
                init() {
                    const n = number.normalize(this.rawValue, this.mode);
                    this.$refs.value.value = (n === '-') ? '' : n;
                    this.$refs.display.value = n;
                },
                handleInput(e) {
                    const n = number.normalize(e.target.value, this.mode);
                    this.$refs.value.value = (n === '-') ? '' : n;
                    e.target.value = n;
                },
            };
        },
        phoneInput(raw) {
            return {
                rawValue: raw ?? '',
                init() {
                    let d = onlyDigits(this.rawValue);
                    if (d.startsWith('55')) d = d.slice(2);
                    d = d.slice(0, 11);
                    this.$refs.value.value = d ? ('+55' + d) : '';
                    this.$refs.display.value = phone.formatBRFromDigits(d);
                },
                handleInput(e) {
                    const digits = onlyDigits(e.target.value).replace(/^55/, '').slice(0, 11);
                    this.$refs.value.value = digits ? ('+55' + digits) : '';
                    e.target.value = phone.formatBRFromDigits(digits);
                },
            };
        },
        rgInput(raw) {
            return {
                rawValue: raw ?? '',
                init() {
                    const n = rg.normalize(this.rawValue);
                    this.$refs.value.value = n;
                    this.$refs.display.value = rg.format(n);
                },
                handleInput(e) {
                    const normalized = rg.normalize(e.target.value);
                    this.$refs.value.value = normalized;
                    e.target.value = rg.format(normalized);
                },
            };
        },
    };

    window.formatters = window.formatters || {};
    window.formatters.widget = widget;
})();
