# 🔍 Competitor Scout — Cohab Premium vs Valor Imobiliária

Roda toda segunda-feira às 8h e envia um relatório de inteligência competitiva por e-mail.

---

## 📁 Estrutura do projeto

```
competitor-scout/
├── .github/
│   └── workflows/
│       └── scout.yml       ← agendamento automático
├── scout.py                ← script principal
├── requirements.txt
└── README.md
```

---

## ⚙️ Configuração — passo a passo

### 1. Criar o repositório no GitHub

1. Acesse [github.com/new](https://github.com/new)
2. Nome: `competitor-scout` (pode ser privado ✅)
3. Clique em **Create repository**
4. Faça upload dos arquivos deste projeto

---

### 2. Configurar os Secrets

Vá em **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | Sua chave da API Anthropic ([pegar aqui](https://console.anthropic.com/)) |
| `GMAIL_USER` | Seu e-mail Gmail (ex: `cohab@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Senha de App do Gmail (veja abaixo) |
| `EMAIL_DESTINO` | E-mail que vai receber o relatório |

---

### 3. Criar Senha de App no Gmail

O Gmail não aceita sua senha normal. Você precisa criar uma **Senha de App**:

1. Acesse [myaccount.google.com/security](https://myaccount.google.com/security)
2. Ative **Verificação em duas etapas** (se ainda não tiver)
3. Vá em **Senhas de app**
4. Selecione: App → `Outro (nome personalizado)` → digite `Competitor Scout`
5. Clique em **Gerar**
6. Copie a senha de 16 caracteres → cole no secret `GMAIL_APP_PASSWORD`

---

### 4. Testar manualmente

Após configurar os secrets:

1. Vá em **Actions** no seu repositório
2. Clique em **🏠 Competitor Scout Semanal**
3. Clique em **Run workflow** → **Run workflow**
4. Aguarde ~2 minutos e verifique seu e-mail

---

## 🕐 Agendamento

O script roda automaticamente **toda segunda-feira às 8h (horário de Brasília)**.

Para mudar o horário, edite a linha `cron` em `.github/workflows/scout.yml`:

```yaml
- cron: '0 11 * * 1'   # segunda às 11:00 UTC = 08:00 BRT
```

Referência de cron: [crontab.guru](https://crontab.guru)

---

## 📊 O que você recebe por e-mail

- **🎯 Oportunidades** — imóveis da Valor que não estão na Cohab (com foto, preço e link direto)
- **🤝 Em ambos** — já captados, sem ação necessária
- **🧐 Para revisar** — pares com similaridade média, para o corretor decidir

O relatório também fica salvo como artefato no GitHub por 30 dias (**Actions → seu run → Artifacts**).
