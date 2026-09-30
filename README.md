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

Se as duas chaves estiverem definidas, a da OpenAI é usada.

## Publicar no Render (grátis)

1. Crie uma conta em https://render.com entrando com o GitHub.
2. Clique em **New → Blueprint** e escolha este repositório (o `render.yaml` já configura tudo).
3. Quando pedir, cole sua chave em `OPENAI_API_KEY` e clique em **Apply**.
4. Em alguns minutos o site fica no ar em `https://criador-xxxx.onrender.com`.

No Render o link do site é detectado sozinho (`RENDER_EXTERNAL_URL`), então não precisa definir
`SITE_URL`, a não ser que use um domínio próprio. No plano grátis o site "dorme" após 15 minutos
sem visitas e leva cerca de 1 minuto para acordar.

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
- `static/` — interface web (HTML, CSS e JavaScript puro).
