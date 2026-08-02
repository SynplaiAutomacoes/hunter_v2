# SynplaiSign API

API de assinatura eletrônica no estilo DocuSign, construída com **NestJS + PostgreSQL + Redis + S3 + Resend**.

🌐 **Base URL:** `https://synplaisign.up.railway.app`

---

## 🚀 Rodando localmente

```bash
npm run start:dev
```

## 🏭 Build para produção

```bash
npm run build
npm run start:prod
```

---

## 🔑 Autenticação

Todas as rotas (exceto `/sign/*`) exigem o header:
```
x-api-key: SUA_CHAVE
```

No primeiro boot, a **MASTER KEY** é exibida no console. Guarde-a!

---

## 📋 Referência Completa da API

---

### 🗝️ API Keys

> Todas as rotas abaixo exigem a **Master Key** no header `x-api-key`.

---

#### `POST /api-keys` — Criar API Key

**Request:**
```json
{
  "name": "Meu Sistema"
}
```

**Response `201`:**
```json
{
  "id": "clxxxxx",
  "name": "Meu Sistema",
  "key": "sk_live_abc123...",
  "isActive": true,
  "createdAt": "2026-06-14T20:00:00.000Z",
  "message": "⚠️ Salve esta chave agora. Ela não será exibida novamente."
}
```

---

#### `GET /api-keys` — Listar API Keys

**Response `200`:**
```json
[
  {
    "id": "clxxxxx",
    "name": "Meu Sistema",
    "isMaster": false,
    "isActive": true,
    "createdAt": "2026-06-14T20:00:00.000Z"
  }
]
```

---

#### `DELETE /api-keys/:id` — Revogar API Key

**Response `200`:**
```json
{
  "message": "API key revogada com sucesso."
}
```

---

### 📄 Envelopes

> Rotas abaixo exigem uma **API Key** (ou Master Key) no header `x-api-key`.

---

#### `POST /envelopes` — Criar Envelope

> Envio via **`multipart/form-data`**.

**Campos:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `file` | File (PDF) | ✅ | Arquivo PDF |
| `title` | string | ✅ | Título do documento |
| `message` | string | ❌ | Mensagem para os signatários |
| `expiresAt` | string (ISO date) | ❌ | Data de expiração do envelope |
| `signatories` | JSON string | ✅ | Array de signatários (ver abaixo) |

**Payload `signatories` (JSON string):**
```json
[
  {
    "name": "Maria Souza",
    "email": "maria@cliente.com",
    "phone": "5511999999999",
    "deliveryChannel": "WHATSAPP",
    "order": 0,
    "fieldPage": 1,
    "fieldX": 100,
    "fieldY": 200,
    "fieldWidth": 200,
    "fieldHeight": 60
  },
  {
    "name": "Carlos Lima",
    "email": "carlos@empresa.com",
    "deliveryChannel": "EMAIL",
    "order": 1
  },
  {
    "name": "Ana Costa",
    "email": "ana@empresa.com",
    "phone": "5521888888888",
    "deliveryChannel": "BOTH",
    "order": 2
  }
]
```

> **Canal de entrega (`deliveryChannel`):**
> - `EMAIL` — padrão; envia apenas por e-mail
> - `WHATSAPP` — envia apenas por WhatsApp (requer `phone`)
> - `BOTH` — e-mail + WhatsApp (requer `phone`)
>
> `phone` deve estar no formato internacional **sem** `+`: `55 + DDD + número` (ex. `5511999999999`).
> WhatsApp nativo da SynplaiSign exige a organização configurada (`PATCH /organizations/me` com `whatsappApiUrl` e `whatsappInstance`).

> **Campos de posição da assinatura no PDF (opcionais):**
> - `fieldPage` — Página onde a assinatura aparece (1 = primeira). **Default:** última página.
> - `fieldX` — Posição horizontal em pontos PDF (0 = esquerda). **Default:** margem esquerda.
> - `fieldY` — Posição vertical em pontos PDF (0 = base da página). **Default:** rodapé.
> - `fieldWidth` — Largura do bloco. **Default:** 200.
> - `fieldHeight` — Altura do bloco. **Default:** 60.
>
> *Uma página A4 = 595 × 842 pontos PDF.*

**Response `201`:**
```json
{
  "id": "clENVELOPE_ID",
  "title": "Contrato de Prestação de Serviços",
  "message": "Por favor, assine.",
  "status": "DRAFT",
  "createdAt": "2026-06-14T20:00:00.000Z",
  "signatories": [
    {
      "id": "clSIG_ID_1",
      "name": "Maria Souza",
      "email": "maria@cliente.com",
      "phone": "5511999999999",
      "deliveryChannel": "WHATSAPP",
      "order": 0,
      "status": "PENDING",
      "token": "clTOKEN_ID",
      "viewedAt": null,
      "signedAt": null,
      "declinedAt": null
    }
  ]
}
```

---

#### `GET /envelopes` — Listar Envelopes

**Response `200`:**
```json
[
  {
    "id": "clENVELOPE_ID",
    "title": "Contrato de Prestação de Serviços",
    "status": "SENT",
    "createdAt": "2026-06-14T20:00:00.000Z",
    "signatories": [...]
  }
]
```

---

#### `GET /envelopes/:id` — Buscar Envelope

**Response `200`:**
```json
{
  "id": "clENVELOPE_ID",
  "title": "Contrato de Prestação de Serviços",
  "status": "PARTIALLY_SIGNED",
  "createdAt": "2026-06-14T20:00:00.000Z",
  "signatories": [
    {
      "id": "clSIG_ID_1",
      "name": "João Silva",
      "email": "joao@email.com",
      "order": 1,
      "status": "SIGNED",
      "viewedAt": "2026-06-14T20:10:00.000Z",
      "signedAt": "2026-06-14T20:12:00.000Z",
      "declinedAt": null
    },
    {
      "id": "clSIG_ID_2",
      "name": "Maria Souza",
      "email": "maria@email.com",
      "order": 2,
      "status": "SENT",
      "viewedAt": null,
      "signedAt": null,
      "declinedAt": null
    }
  ]
}
```

---

#### `POST /envelopes/:id/send` — Enviar para Assinatura

> Dispara a entrega aos signatários conforme `deliveryChannel` (e-mail e/ou WhatsApp). O envelope passa de `DRAFT` para `SENT`.

**Request:** sem body.

**Response `200`:**
```json
{
  "id": "clENVELOPE_ID",
  "status": "SENT"
}
```

---

#### `GET /envelopes/:id/download` — URL do PDF Final

> Disponível apenas após o envelope estar `COMPLETED`.

**Response `200`:**
```json
{
  "url": "https://t3.storageapi.dev/...?X-Amz-Signature=...&X-Amz-Expires=3600",
  "expiresIn": 3600
}
```

---

#### `GET /envelopes/:id/audit` — Log de Auditoria

**Response `200`:**
```json
[
  {
    "id": "clLOG_ID",
    "event": "ENVELOPE_CREATED",
    "actorEmail": null,
    "ipAddress": null,
    "metadata": null,
    "createdAt": "2026-06-14T20:00:00.000Z"
  },
  {
    "id": "clLOG_ID_2",
    "event": "DOCUMENT_VIEWED",
    "actorEmail": "joao@email.com",
    "ipAddress": "177.55.100.1",
    "metadata": null,
    "createdAt": "2026-06-14T20:10:00.000Z"
  },
  {
    "id": "clLOG_ID_3",
    "event": "DOCUMENT_SIGNED",
    "actorEmail": "joao@email.com",
    "ipAddress": "177.55.100.1",
    "metadata": { "signatoryName": "João Silva" },
    "createdAt": "2026-06-14T20:12:00.000Z"
  },
  {
    "id": "clLOG_ID_4",
    "event": "ENVELOPE_COMPLETED",
    "actorEmail": null,
    "ipAddress": null,
    "metadata": null,
    "createdAt": "2026-06-14T20:12:01.000Z"
  }
]
```

**Eventos possíveis:**

| Evento | Descrição |
|---|---|
| `ENVELOPE_CREATED` | Envelope criado |
| `ENVELOPE_SENT` | Emails disparados |
| `DOCUMENT_VIEWED` | Signatário abriu o link |
| `DOCUMENT_SIGNED` | Signatário assinou |
| `DOCUMENT_DECLINED` | Signatário recusou |
| `ENVELOPE_COMPLETED` | Todos assinaram |

---

#### `POST /envelopes/:id/void` — Cancelar Envelope

**Request:**
```json
{
  "reason": "Contrato substituído por versão atualizada."
}
```

**Response `200`:**
```json
{
  "message": "Envelope cancelado."
}
```

---

### ✍️ Assinatura (rotas públicas — sem API Key)

> Estas rotas são acessadas pelos signatários via token único recebido por email.

---

#### `GET /sign/:token` — Página de Assinatura (navegador)

> Abre a página HTML para o signatário visualizar o PDF e assinar.
> Marca automaticamente o documento como **VIEWED**.

**Comportamento por status:**

| Status | O que o signatário vê |
|---|---|
| `PENDING` | ⏳ Página "Aguardando sua vez" |
| `SENT` / `VIEWED` | ✍️ Formulário de assinatura com PDF |
| `SIGNED` | ✅ PDF assinado com botão de download |
| `DECLINED` | 😔 Página de recusa |

---

#### `GET /sign/:token/info` — Info do Signatário (API JSON)

**Response `200`:**
```json
{
  "envelopeId": "clENVELOPE_ID",
  "title": "Contrato de Prestação de Serviços",
  "message": "Por favor, assine.",
  "signatoryName": "João Silva",
  "status": "VIEWED"
}
```

---

#### `GET /sign/:token/document` — PDF Original (inline)

> Retorna o PDF original para visualização (antes de assinar).

**Response:** `application/pdf` (binário)

---

#### `GET /sign/:token/signed-document` — PDF Assinado (inline)

> Retorna o PDF com a assinatura embutida (após assinar).

**Response:** `application/pdf` (binário)

---

#### `POST /sign/:token` — Submeter Assinatura

**Request:**
```json
{
  "signature": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."
}
```

> O campo `signature` deve ser uma imagem base64 no formato `data:image/png;base64,...` (capturada do canvas).

**Response `200`:**
```json
{
  "message": "Documento assinado com sucesso!"
}
```

---

#### `POST /sign/:token/decline` — Recusar Assinatura

**Request:**
```json
{
  "reason": "Preciso revisar os termos antes de assinar."
}
```

**Response `200`:**
```json
{
  "message": "Recusa registrada com sucesso."
}
```

---

### 🔔 Webhooks

---

#### `POST /webhooks` — Registrar Webhook

**Request:**
```json
{
  "url": "https://meusite.com/webhooks/synplaisign",
  "events": ["DOCUMENT_SIGNED", "ENVELOPE_COMPLETED"],
  "envelopeId": "clENVELOPE_ID"
}
```

> `envelopeId` é opcional — omita para receber eventos de todos os envelopes da API Key.

**Response `201`:**
```json
{
  "id": "clWEBHOOK_ID",
  "url": "https://meusite.com/webhooks/synplaisign",
  "events": ["DOCUMENT_SIGNED", "ENVELOPE_COMPLETED"],
  "secret": "whsec_abc123...",
  "createdAt": "2026-06-14T20:00:00.000Z"
}
```

> 🔐 Guarde o `secret` — ele é usado para validar as requisições via **HMAC-SHA256** no header `x-synplai-signature`.

---

#### `GET /webhooks` — Listar Webhooks

**Response `200`:**
```json
[
  {
    "id": "clWEBHOOK_ID",
    "url": "https://meusite.com/webhooks/synplaisign",
    "events": ["DOCUMENT_SIGNED", "ENVELOPE_COMPLETED"],
    "isActive": true,
    "createdAt": "2026-06-14T20:00:00.000Z"
  }
]
```

---

#### `DELETE /webhooks/:id` — Remover Webhook

**Response `200`:**
```json
{
  "message": "Webhook removido."
}
```

---

#### Payload recebido no seu servidor (evento webhook)

```json
{
  "event": "DOCUMENT_SIGNED",
  "envelopeId": "clENVELOPE_ID",
  "timestamp": "2026-06-14T20:12:00.000Z",
  "data": {
    "signatoryEmail": "joao@email.com",
    "signatoryName": "João Silva",
    "signedAt": "2026-06-14T20:12:00.000Z"
  }
}
```

**Validação HMAC:**
```js
const crypto = require('crypto');

function verifyWebhook(body, signature, secret) {
  const expected = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(body))
    .digest('hex');
  return `sha256=${expected}` === signature;
}

// No seu endpoint:
const isValid = verifyWebhook(req.body, req.headers['x-synplai-signature'], 'whsec_...');
```

---

## 📊 Status dos Envelopes

| Status | Descrição |
|---|---|
| `DRAFT` | Criado, aguardando envio |
| `SENT` | Emails disparados |
| `PARTIALLY_SIGNED` | Pelo menos 1 assinou, outros pendentes |
| `COMPLETED` | ✅ Todos assinaram |
| `DECLINED` | Algum signatário recusou |
| `VOIDED` | Cancelado manualmente |
| `EXPIRED` | Link expirado |

## 📊 Status dos Signatários

| Status | Descrição |
|---|---|
| `PENDING` | Aguardando a vez (ordem sequencial) |
| `SENT` | Email enviado, aguardando abertura |
| `VIEWED` | Abriu o link de assinatura |
| `SIGNED` | ✅ Assinou o documento |
| `DECLINED` | Recusou a assinatura |

---

## 🩺 Health Check

```
GET /health
```

**Response `200`:**
```json
{
  "status": "ok",
  "service": "SynplaiSign",
  "timestamp": "2026-06-14T20:00:00.000Z"
}
```

---

## 💬 WhatsApp (organização)

Antes de usar `deliveryChannel` `WHATSAPP` ou `BOTH`, configure a organização SynplaiSign:

```
PATCH /organizations/me
Authorization: Bearer <JWT>
```

```json
{
  "whatsappApiUrl": "https://wp-api.synplai.online",
  "whatsappInstance": "a3f9c1"
}
```

A instância precisa estar conectada na WhatsApp Sender API. Sem essa configuração, o envelope ainda é criado/enviado, mas apenas o e-mail é entregue.
