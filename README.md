# Criador — IA para criação de conteúdo

Um chat no estilo ChatGPT focado em criação de conteúdo: posts para Instagram e LinkedIn,
threads, roteiros de Reels/TikTok/YouTube, artigos de blog com SEO, e-mails de marketing e
ideias de pauta. As respostas chegam em tempo real (streaming) e as conversas ficam salvas no
navegador.

## Como rodar

Requisitos: Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # e coloque sua chave (OpenAI ou Anthropic)
uvicorn app:app --reload
```

Abra http://localhost:8000.

## Configuração (`.env`)

| Variável            | Descrição                                                  |
|---------------------|------------------------------------------------------------|
| `OPENAI_API_KEY`    | Chave da OpenAI (usa `gpt-6-luna` por padrão)              |
| `ANTHROPIC_API_KEY` | Chave da Anthropic (usa `claude-sonnet-4-5` por padrão)    |
| `MODEL`             | Opcional: troca o modelo usado                             |
| `SITE_URL`          | Link público do site (ex.: `https://meusite.com.br`); ativa a indexação automática |
| `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_SERVICE_ACCOUNT_FILE` | Opcional: conta de serviço para cadastrar no Google automaticamente |
| `GOOGLE_OWNER_EMAIL` | Opcional: seu e-mail, adicionado como proprietário no Search Console |
| `GOOGLE_SITE_VERIFICATION` / `BING_SITE_VERIFICATION` / `YANDEX_SITE_VERIFICATION` | Opcional: códigos de verificação manual |
| `INDEXNOW_KEY`      | Opcional: chave IndexNow própria (senão é gerada a partir do domínio) |
| `MONITOR_INTERVAL_MINUTES` | Opcional: de quanto em quanto tempo os sites monitorados são reescaneados (padrão 360, mínimo 5) |
| `MONITOR_MAX_SITES` | Opcional: máximo de sites monitorados (padrão 20) |
| `MONITOR_FILE`      | Opcional: onde salvar os sites monitorados (padrão `data/monitor.json`) |
| `MONITOR_WEBHOOK_URL` | Opcional: URL que recebe um POST JSON a cada alerta (ex.: webhook do Discord/Slack/Zapier) |

Se as duas chaves estiverem definidas, a da OpenAI é usada.

## Publicar no Render (grátis)

1. Crie uma conta em https://render.com entrando com o GitHub.
2. Clique em **New → Blueprint** e escolha este repositório (o `render.yaml` já configura tudo).
3. Quando pedir, cole sua chave em `OPENAI_API_KEY` e clique em **Apply**.
4. Em alguns minutos o site fica no ar em `https://criador-xxxx.onrender.com`.

No Render o link do site é detectado sozinho (`RENDER_EXTERNAL_URL`), então não precisa definir
`SITE_URL`, a não ser que use um domínio próprio. No plano grátis o site "dorme" após 15 minutos
sem visitas e leva cerca de 1 minuto para acordar.

## Analisador de SEO (`/seo`)

Ferramenta para fazer **qualquer site** aparecer mais no Google, com visual de antivírus. Abra
http://localhost:8000/seo (ou `/seo?url=meusite.com.br`), cole o endereço (e, se quiser, a
palavra-chave) e clique no botão grande **ESCANEAR**. Uma barra de progresso mostra cada etapa, e no
fim aparecem **"X problemas encontrados"** e o botão **Corrigir problemas**, com o código pronto de
cada correção e botão **Copiar**. Você recebe:

- uma **nota de 0 a 100** e a lista do que está certo, com aviso ou com erro: HTTPS, velocidade,
  bloqueio de indexação (noindex), `<title>`, meta description, H1/H2, quantidade de texto, `alt`
  das imagens, versão mobile, idioma, link canônico, Open Graph, schema.org, favicon, links
  internos, links quebrados, `robots.txt`, `sitemap.xml` e palavra-chave — cada item com a dica de
  como corrigir;
- um **plano de ação com IA** (precisa da chave OpenAI/Anthropic): correções com o código HTML
  pronto, novos título e description, palavras-chave, ideias de conteúdo e passo a passo para
  cadastrar no Google Search Console e Bing.

Por segurança, só são analisados endereços públicos da internet.

### Monitoramento contínuo

Clique em **Monitorar este site** e o servidor passa a reescanear o site sozinho (a cada 6 h por
padrão, veja `MONITOR_INTERVAL_MINUTES`). Ele cria um alerta quando aparece um problema novo, quando
um problema é resolvido, quando a nota cai 5 pontos ou mais e quando o site fica fora do ar ou volta a
responder. Os alertas aparecem na página, podem virar **notificação do navegador** (botão "Ativar
alertas no navegador") e são enviados ao `MONITOR_WEBHOOK_URL`, se estiver configurado.

### Programa para Windows

`desktop_app.py` é o mesmo scanner em um programa de PC: botão **ESCANEAR**, barra de progresso,
lista de problemas, **Corrigir selecionado / Corrigir todos** (código pronto para copiar) e
**Monitorar continuamente** (reescaneia a cada N minutos e mostra um alerta quando surge um problema).
Não precisa de servidor nem de chave de IA.

- **Baixar o .exe:** no GitHub, abra *Actions → Programa para Windows*, escolha a execução mais
  recente e baixe o artefato `AnalisadorSEO-windows`.
- **Gerar você mesmo (no Windows):**
  ```bash
  pip install httpx==0.28.1 pyinstaller==6.16.0
  pyinstaller --onefile --windowed --name AnalisadorSEO desktop_app.py
  ```
  O programa fica em `dist/AnalisadorSEO.exe`.
- **Rodar pelo código-fonte:** `python desktop_app.py`.

## Aparecer no Google e outros buscadores (automático)

O site já entrega o que os buscadores precisam: `/robots.txt`, `/sitemap.xml`, meta description,
link canônico, Open Graph (prévia ao compartilhar) e dados estruturados (schema.org).

**Basta colocar o link do site em `SITE_URL`** (no `.env` ou nas variáveis da hospedagem). Ao
iniciar, o servidor sozinho:

1. espera o site responder no endereço público;
2. avisa Bing, Yandex, Seznam e Naver via IndexNow (a chave é gerada automaticamente);
3. se houver conta de serviço do Google configurada: verifica a propriedade do site, adiciona no
   Google Search Console e envia o `sitemap.xml`.

O andamento aparece no log do servidor (linhas `SEO:`).

### Google (configuração única)

O Google exige uma credencial para aceitar o cadastro automático:

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um projeto e ative as APIs
   **Site Verification API** e **Google Search Console API**.
2. Em **IAM e administrador → Contas de serviço**, crie uma conta de serviço e gere uma chave JSON.
3. Coloque o conteúdo do JSON em `GOOGLE_SERVICE_ACCOUNT_JSON` (ou o caminho do arquivo em
   `GOOGLE_SERVICE_ACCOUNT_FILE`) e seu e-mail em `GOOGLE_OWNER_EMAIL` para ver o site no
   [Search Console](https://search.google.com/search-console).

A indexação pelo Google costuma levar de alguns dias a algumas semanas.

### Conferir ou reenviar manualmente

```bash
python indexar.py https://meusite.com.br
```

## Estrutura

- `app.py` — servidor FastAPI; monta o prompt de sistema (formato, tom e idioma) e faz streaming da resposta do provedor.
- `seo.py` — indexação automática (IndexNow e Google Search Console).
- `indexar.py` — verifica o SEO do site publicado e reenvia aos buscadores.
- `seo_audit.py` — scanner de SEO de qualquer site (usado pela página `/seo` e pelo programa).
- `monitor.py` — monitoramento contínuo dos sites e alertas.
- `desktop_app.py` — programa para Windows (Tkinter), empacotado em `.exe` pelo GitHub Actions.
- `static/` — interface web (HTML, CSS e JavaScript puro).
