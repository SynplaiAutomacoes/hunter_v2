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
        parse(value, mode = 'hours_minutes') {
            let d = onlyDigits(value);

            if (!d) return { hh: '', mm: '' };

            if (mode === 'hours') {
                return { hh: d.slice(0, 2), mm: '' };
            }

            if (mode === 'minutes') {
                let mm = d.slice(0, 2);
                let m = parseInt(mm, 10);
                if (!Number.isNaN(m) && m > 59) m = 59;
                return { hh: '', mm: String(m).padStart(2, '0') };
            }

            // hours_minutes (default)
            d = d.slice(0, 4);
            let hh = d.slice(0, 2);
            let mm = d.slice(2, 4);

            if (mm.length === 2) {
                let m = parseInt(mm, 10);
                if (!Number.isNaN(m) && m > 59) m = 59;
                mm = String(m).padStart(2, '0');
            }

            return { hh, mm };
        },

        formatDisplay(hh, mm, mode = 'hours_minutes') {
            if (mode === 'hours') return hh || '';
            if (mode === 'minutes') return mm || '';
            if (!hh && !mm) return '';
            if (hh && !mm) return hh.length >= 2 ? `${hh}:` : hh;
            return `${hh}:${mm}`;
        },

        normalizeForPost(hh, mm, mode = 'hours_minutes') {
            const h = (hh || '').toString();
            const m = (mm || '').toString();

            if (mode === 'hours') return h ? `${h.padStart(2, '0')}:00:00` : '';
            if (mode === 'minutes') return m ? `00:${m.padStart(2, '0')}:00` : '';

            if (!h && !m) return '';
            return `${h.padStart(2, '0')}:${m.padStart(2, '0')}:00`;
        },

        initFromRaw(raw, mode = 'hours_minutes') {
            const s = (raw ?? '').toString();

            if (mode === 'hours') {
                const m = s.match(/(\d{1,2})/);
                return { hh: m ? m[1].padStart(2, '0') : '', mm: '' };
            }

            if (mode === 'minutes') {
                const m = s.match(/:(\d{2})/);
                return { hh: '', mm: m ? m[1] : '' };
            }

            const m = s.match(/(\d{1,2}):(\d{2})(?::\d{2})?/);
            if (!m) return { hh: '', mm: '' };

            return {
                hh: String(parseInt(m[1], 10)).padStart(2, '0'),
                mm: String(parseInt(m[2], 10)).padStart(2, '0'),
            };
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

        // Formata número inteiro com separador de milhares (pt-BR)
        formatInteger(v) {
            if (!v || v === '-') return v;
            const normalized = this.normalize(v, 'positive');
            if (!normalized || normalized === '-') return '';

            // Converte para número e formata com separador de milhares
            const num = parseInt(normalized, 10);
            if (isNaN(num)) return '';

            return num.toLocaleString('pt-BR');
        },
    };

    const decimal = {
        clean(value) {
            let s = (value ?? '').toString();
            s = s.replace(/,/g, '.');
            s = s.replace(/[^0-9.-]/g, '');
            const parts = s.split('.');
            if (parts.length > 2) {
                s = parts.shift() + '.' + parts.join('');
            }
            if (s.lastIndexOf('-') > 0) {
                s = s.replace(/-/g, '');
                s = '-' + s;
            }
            return s;
        },

        format(value, places = 2) {
            if (value === '' || value === null || value === undefined) return '';
            const n = parseFloat(value);
            if (Number.isNaN(n)) return '';
            return n.toFixed(places);
        },

        formatPtBr(value, places = 2) {
            if (value === '' || value === null || value === undefined) return '';
            const n = parseFloat(value);
            if (Number.isNaN(n)) return '';
            return n.toLocaleString('pt-BR', {
                minimumFractionDigits: places,
                maximumFractionDigits: places,
            });
        }
    };

    const percent = {
        clamp(n, min, max) {
            if (Number.isNaN(n)) return NaN;
            if (n < min) return min;
            if (n > max) return max;
            return n;
        },
        // Entrada livre -> string dot-decimal (ex: "12.34").
        // Aceita tanto "," quanto "." como separador digitado; internamente normaliza para ".".
        normalizeToDotDecimal(value, maxFractionDigits = 6) {
            let s = (value ?? '').toString().trim();
            if (!s) return '';

            // Mantém apenas dígitos e separadores, colapsa múltiplos.
            s = s.replace(/[^0-9.,]/g, '');
            if (!s) return '';

            // Se houver ambos, trata "." como milhar e "," como decimal (padrão pt-BR)
            const hasDot = s.includes('.');
            const hasComma = s.includes(',');
            if (hasDot && hasComma) {
                s = s.replace(/\./g, '');
                s = s.replace(',', '.');
            } else {
                // Caso contrário, usa o último separador como decimal.
                const lastComma = s.lastIndexOf(',');
                const lastDot = s.lastIndexOf('.');
                const decPos = Math.max(lastComma, lastDot);
                if (decPos >= 0) {
                    const intPart = s.slice(0, decPos).replace(/[.,]/g, '');
                    const fracPart = s.slice(decPos + 1).replace(/[.,]/g, '');
                    // Preserva separador final (ex.: "25," enquanto o usuário ainda vai digitar as casas)
                    s = intPart + '.' + fracPart;
                } else {
                    s = s.replace(/[.,]/g, '');
                }
            }

            if (s === '.') return '';
            if (!/^\d+(?:\.\d*)?$/.test(s)) return '';

            // Limita casas (sem apagar o ponto quando ainda não há fração)
            if (s.includes('.')) {
                const [i, f] = s.split('.');
                const frac = (f ?? '').slice(0, maxFractionDigits);
                s = (f === undefined) ? i : (i + '.' + frac);
            }
            // Remove zeros à esquerda (mas preserva "0.x")
            s = s.replace(/^0+(?=\d)/, '');
            if (s.startsWith('.')) s = '0' + s;
            return s;
        },
        // Exibição com separador decimal "." (sem agrupamento de milhar).
        formatDotFromDotDecimal(dotDecimal, fractionDigits = 2) {
            if (!dotDecimal && dotDecimal !== 0) return '';
            const s = (dotDecimal ?? '').toString();
            if (!s) return '';
            const n = Number(s);
            if (Number.isNaN(n)) return '';
            return new Intl.NumberFormat('en-US', {
                useGrouping: false,
                minimumFractionDigits: fractionDigits,
                maximumFractionDigits: fractionDigits,
            }).format(n);
        },
        formatPtBrFromDotDecimal(dotDecimal, fractionDigits = 2) {
            if (!dotDecimal && dotDecimal !== 0) return '';
            const s = (dotDecimal ?? '').toString();
            if (!s) return '';
            const n = Number(s);
            if (Number.isNaN(n)) return '';
            return n.toLocaleString('pt-BR', {
                minimumFractionDigits: fractionDigits,
                maximumFractionDigits: fractionDigits,
            });
        },
        // Converte fração (0..1) -> % (0..100)
        fractionToPercentValue(rawFraction) {
            if (rawFraction === null || rawFraction === undefined) return '';
            const s = rawFraction.toString().trim();
            if (!s) return '';
            const n = Number(s);
            if (Number.isNaN(n)) return '';
            // Suporte defensivo: se vier como 50, assume que já está em percent.
            if (n > 1) return n;
            return n * 100;
        },
        // Converte % -> fração dot-decimal
        percentToFractionDotDecimal(percentValue, maxFractionDigits = 10) {
            const n = Number(percentValue);
            if (Number.isNaN(n)) return '';
            const frac = n / 100;
            // Evita notação científica e corta excesso
            return frac.toFixed(maxFractionDigits).replace(/0+$/, '').replace(/\.$/, '');
        },
    };

    function emitFormattedChange(ref, detail) {
        if (!ref || typeof ref.dispatchEvent !== 'function') return;
        ref.dispatchEvent(new CustomEvent('widget:formatted-change', {
            bubbles: true,
            detail,
        }));
    }

    function emitNativeInputEvents(ref) {
        if (!ref || typeof ref.dispatchEvent !== 'function') return;
        ref.dispatchEvent(new Event('input', { bubbles: true }));
        ref.dispatchEvent(new Event('change', { bubbles: true }));
    }

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
    document.addEventListener('htmx:afterSwap', (e) => {
        applyFormats(e.target);
    });

    //TODO: Estamos normalizando o valor duas vezes, uma vez para o input e outra para o display. Podemos melhorar isso posteriormente.
    const widget = {
        cepInput(raw) {
            return {
                rawValue: raw ?? '',
                init() {
                    const formatted = cep.format(this.rawValue);
                    this.$refs.value.value = formatted;
                    this.$refs.display.value = formatted;
                },
                handleInput(e) {
                    const formatted = cep.format(e.target.value);
                    this.$refs.value.value = formatted;
                    e.target.value = formatted;
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
        durationInput(raw, mode) {
            return {
                rawValue: raw ?? '',
                mode: mode,

                init() {
                    const { hh, mm } = duration.initFromRaw(this.rawValue, this.mode);
                    this.$refs.value.value = duration.normalizeForPost(hh, mm, this.mode);
                    this.$refs.display.value = duration.formatDisplay(hh, mm, this.mode);
                },

                handleInput(e) {
                    const { hh, mm } = duration.parse(e.target.value, this.mode);
                    this.$refs.value.value = duration.normalizeForPost(hh, mm, this.mode);
                    e.target.value = duration.formatDisplay(hh, mm, this.mode);
                },

                handleBlur(e) {
                    let { hh, mm } = duration.parse(e.target.value, this.mode);
                    if (!hh && !mm) return;

                    if (this.mode === 'hours_minutes' || !this.mode) {
                        if (hh && !mm) mm = '00';
                        if (!hh && mm) hh = '00';
                    }

                    this.$refs.value.value = duration.normalizeForPost(hh, mm, this.mode);
                    e.target.value = duration.formatDisplay(hh, mm, this.mode);
                }
            };
        },
        moneyInput(rawDotDecimal, originalDotDecimal = '', warningMessage = '') {
            const normalizeStoredValue = (value) => {
                const stringValue = (value ?? '').toString().trim();
                if (!stringValue) return '';
                if (/^-?\d+(?:\.\d+)?$/.test(stringValue)) {
                    return Number(stringValue).toFixed(2);
                }
                return money.normalizeToDotDecimal(stringValue);
            };

            return {
                rawValue: normalizeStoredValue(rawDotDecimal),
                originalValue: normalizeStoredValue(originalDotDecimal),
                warningMessage: (warningMessage ?? '').toString(),
                isDirty: false,
                maxDigits: 14,
                syncDirtyState(value) {
                    this.isDirty = value !== this.originalValue;
                },
                syncDisplay(value) {
                    this.$refs.amount.value = value;
                    this.$refs.display.value = money.formatPtBrFromDotDecimal(value);
                    this.syncDirtyState(value);
                },
                init() {
                    this.syncDisplay(this.rawValue);
                },
                handleInput(e) {
                    const normalized = money.normalizeToDotDecimal(e.target.value, this.maxDigits);
                    this.syncDisplay(normalized);
                    e.target.value = this.$refs.display.value;
                    emitFormattedChange(this.$refs.amount, {
                        value: normalized,
                        displayValue: e.target.value,
                    });
                },
                restoreOriginal() {
                    this.syncDisplay(this.originalValue);
                    emitNativeInputEvents(this.$refs.display);
                    emitNativeInputEvents(this.$refs.amount);
                    emitFormattedChange(this.$refs.amount, {
                        value: this.originalValue,
                        displayValue: this.$refs.display.value,
                    });
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
                    // Formata o display inicial
                    this.$refs.display.value = number.formatInteger(n);
                },
                handleInput(e) {
                    const n = number.normalize(e.target.value, this.mode);
                    this.$refs.value.value = (n === '-') ? '' : n;
                    // Formata o display durante a digitação
                    e.target.value = number.formatInteger(n);
                    emitNativeInputEvents(this.$refs.value);
                    emitFormattedChange(this.$refs.value, {
                        value: this.$refs.value.value,
                        displayValue: e.target.value,
                    });
                },
            };
        },
        decimalInput(raw, minVal, maxVal, places = 2) {

            const parseLimit = (v) => {
                if (v === null || v === undefined) return null;
                let s = v.toString().trim();

                if (!s || s.toLowerCase() === 'none' || s.toLowerCase() === 'null') return null;
                s = s.replace(',', '.');

                const n = parseFloat(s);
                return Number.isNaN(n) ? null : n;
            };

            return {
                rawValue: (raw ?? '').toString().replace(',', '.'),
                min: parseLimit(minVal),
                max: parseLimit(maxVal),
                places: Number(places),

                init() {
                    if (this.rawValue && !isNaN(parseFloat(this.rawValue))) {
                        const formatted = decimal.formatPtBr(this.rawValue, this.places);
                        this.$refs.display.value = formatted;
                        this.$refs.value.value = decimal.format(this.rawValue, this.places);
                    }
                },

                handleInput(e) {
                    let typed = e.target.value;
                    let cleaned = decimal.clean(typed);

                    if (typed !== cleaned && !typed.endsWith(',') && !typed.endsWith('.')) {
                        e.target.value = cleaned.replace('.', ',');
                    }

                    this.$refs.value.value = cleaned;
                },

                handleBlur(e) {
                    let currentVal = decimal.clean(e.target.value);

                    if (!currentVal || currentVal === '-') {
                        this.$refs.display.value = '';
                        this.$refs.value.value = '';
                        return;
                    }

                    let val = parseFloat(currentVal);

                    if (Number.isNaN(val)) {
                        this.$refs.display.value = '';
                        this.$refs.value.value = '';
                        return;
                    }

                    if (this.min !== null && val < this.min) val = this.min;
                    if (this.max !== null && val > this.max) val = this.max;

                    this.$refs.display.value = decimal.formatPtBr(val, this.places);
                    this.$refs.value.value = decimal.format(val, this.places);
                }
            };
        },
        percentageInput(rawFraction, minPercent, maxPercent, decimalPlaces, behavior = 'free_decimal') {
            return {
                rawValue: (rawFraction ?? '').toString(),
                minPercent: Number(minPercent ?? 0),
                maxPercent: Number(maxPercent ?? 100),
                decimalPlaces: Number(decimalPlaces ?? 2),
                maxParseFractionDigits: 6,
                behavior: (behavior ?? 'free_decimal').toString(),
                formatPercentValue(percentValue) {
                    return percent.formatPtBrFromDotDecimal(percentValue, this.decimalPlaces);
                },
                syncDigitStreamDisplay(digits) {
                    const safeDigits = digits || '0';
                    const maxTotalDigits = String(Math.floor(this.maxPercent)).length + this.decimalPlaces;
                    const trimmedDigits = safeDigits.slice(-maxTotalDigits);
                    const percentValue = Number((parseInt(trimmedDigits, 10) / (10 ** this.decimalPlaces)).toFixed(this.decimalPlaces));
                    const clamped = percent.clamp(percentValue, this.minPercent, this.maxPercent);
                    this.$refs.value.value = percent.percentToFractionDotDecimal(clamped, this.decimalPlaces + 2);
                    this.$refs.display.value = this.formatPercentValue(clamped);
                    emitFormattedChange(this.$refs.value, {
                        value: this.$refs.value.value,
                        displayValue: this.$refs.display.value,
                    });
                },
                init() {
                    const p = percent.fractionToPercentValue(this.rawValue);
                    if (this.behavior === 'digit_stream') {
                        if (p === '') {
                            this.$refs.value.value = '0';
                            this.$refs.display.value = this.formatPercentValue(0);
                            return;
                        }

                        const clamped = percent.clamp(Number(p), this.minPercent, this.maxPercent);
                        this.$refs.value.value = percent.percentToFractionDotDecimal(clamped, this.decimalPlaces + 2);
                        this.$refs.display.value = this.formatPercentValue(clamped);
                        return;
                    }

                    if (p === '') {
                        this.$refs.value.value = '';
                        this.$refs.display.value = '';
                        return;
                    }
                    const clamped = percent.clamp(Number(p), this.minPercent, this.maxPercent);
                    this.$refs.value.value = percent.percentToFractionDotDecimal(clamped, this.decimalPlaces + 2);
                    this.$refs.display.value = this.formatPercentValue(clamped);
                },
                handleInput(e) {
                    if (this.behavior === 'digit_stream') {
                        let digits = onlyDigits(e.target.value);
                        if (!digits) digits = '0';
                        this.syncDigitStreamDisplay(digits);
                        return;
                    }

                    const typed = (e.target.value ?? '').toString();
                    const normalized = percent.normalizeToDotDecimal(typed, this.maxParseFractionDigits);

                    if (!normalized) {
                        this.$refs.value.value = '';
                        emitFormattedChange(this.$refs.value, {
                            value: '',
                            displayValue: e.target.value,
                        });
                        return;
                    }

                    const n = Number(normalized);
                    if (Number.isNaN(n)) return;

                    this.$refs.value.value = percent.percentToFractionDotDecimal(n, this.decimalPlaces + 2);
                    emitFormattedChange(this.$refs.value, {
                        value: this.$refs.value.value,
                        displayValue: typed,
                    });

                    // Permite que o usuário digite o separador decimal sem forçar a formatação imediata
                    // que poderia atrapalhar a digitação das casas decimais.
                    if (typed.endsWith(',') || typed.endsWith('.')) {
                        return;
                    }

                    // Se não estiver no meio da digitação do separador, limpamos caracteres inválidos
                    // mas não aplicamos formatação de milhar ainda para não saltar o cursor.
                    const [intPart, fracPart] = normalized.split('.');
                    let display = intPart;
                    if (fracPart !== undefined) {
                        display += ',' + fracPart.slice(0, this.decimalPlaces);
                    }
                    if (typed !== display) {
                        e.target.value = display;
                    }
                },
                handleBlur() {
                    if (this.behavior === 'digit_stream') {
                        if (!this.$refs.value.value) {
                            this.$refs.value.value = '0';
                        }
                        const percentValue = percent.fractionToPercentValue(this.$refs.value.value) || 0;
                        const clamped = percent.clamp(Number(percentValue), this.minPercent, this.maxPercent);
                        this.$refs.value.value = percent.percentToFractionDotDecimal(clamped, this.decimalPlaces + 2);
                        this.$refs.display.value = this.formatPercentValue(clamped);
                        emitFormattedChange(this.$refs.value, {
                            value: this.$refs.value.value,
                            displayValue: this.$refs.display.value,
                        });
                        return;
                    }

                    const raw = this.$refs.value.value;
                    if (!raw) return;

                    const percentValue = Number(raw) * 100;
                    if (Number.isNaN(percentValue)) return;

                    const clamped = percent.clamp(
                        percentValue,
                        this.minPercent,
                        this.maxPercent
                    );

                    this.$refs.value.value = percent.percentToFractionDotDecimal(clamped, this.decimalPlaces + 2);
                    this.$refs.display.value = this.formatPercentValue(clamped);
                    emitFormattedChange(this.$refs.value, {
                        value: this.$refs.value.value,
                        displayValue: this.$refs.display.value,
                    });
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
        imageInput(initialUrl, clearCheckboxName) {
            return {
                previewUrl: initialUrl || null,
                fileName: null,
                isCleared: false,
                clearCheckboxName: clearCheckboxName,

                handleFile(e) {
                    const file = e.target.files[0];
                    if (file) {
                        // Cria URL temporária para preview
                        this.previewUrl = URL.createObjectURL(file);
                        this.fileName = file.name;
                        this.isCleared = false;
                    }
                },

                remove() {
                    this.previewUrl = null;
                    this.fileName = null;
                    this.isCleared = true;
                    // Limpa o input file real
                    this.$refs.fileInput.value = '';
                },

                restoreOriginal() {
                   this.previewUrl = initialUrl;
                   this.isCleared = false;
                   this.$refs.fileInput.value = '';
                }
            };
        },
    };

    window.formatters = window.formatters || {};
    window.formatters.widget = widget;
})();
