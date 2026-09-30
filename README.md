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
| `OPENAI_API_KEY`    | Chave da OpenAI (usa `gpt-4o-mini` por padrão)             |
| `ANTHROPIC_API_KEY` | Chave da Anthropic (usa `claude-sonnet-4-5` por padrão)    |
| `MODEL`             | Opcional: troca o modelo usado                             |
| `SITE_URL`          | Endereço público do site (ex.: `https://meusite.com.br`)   |
| `GOOGLE_SITE_VERIFICATION` / `BING_SITE_VERIFICATION` / `YANDEX_SITE_VERIFICATION` | Códigos de verificação de propriedade dos buscadores |
| `INDEXNOW_KEY`      | Chave para avisar Bing/Yandex sobre páginas novas          |

Se as duas chaves estiverem definidas, a da OpenAI é usada.

## Aparecer no Google e outros buscadores

O site já entrega o que os buscadores precisam: `/robots.txt`, `/sitemap.xml`, meta description,
link canônico, Open Graph (prévia ao compartilhar) e dados estruturados (schema.org).

1. Publique o site num endereço público e defina `SITE_URL` no `.env`.
2. **Google**: entre no [Google Search Console](https://search.google.com/search-console), adicione
   o site como "Prefixo do URL", escolha verificação por "Tag HTML", copie só o valor de `content`
   para `GOOGLE_SITE_VERIFICATION`, reinicie o servidor e clique em Verificar. Depois, em
   **Sitemaps**, envie `sitemap.xml`.
3. **Bing** (também alimenta DuckDuckGo, Yahoo e Ecosia): no
   [Bing Webmaster Tools](https://www.bing.com/webmasters) importe do Search Console ou use
   `BING_SITE_VERIFICATION`.
4. **IndexNow** (Bing, Yandex, Seznam, Naver): gere uma chave com
   `python -c "import uuid; print(uuid.uuid4().hex)"`, coloque em `INDEXNOW_KEY` e publique.
5. Rode a ferramenta para verificar o SEO e avisar os buscadores sempre que atualizar o site:

```bash
python indexar.py https://meusite.com.br
```

A indexação pelo Google costuma levar de alguns dias a algumas semanas.

## Estrutura

- `app.py` — servidor FastAPI; monta o prompt de sistema (formato, tom e idioma) e faz streaming da resposta do provedor.
- `indexar.py` — verifica o SEO do site publicado e envia as URLs do sitemap via IndexNow.
- `static/` — interface web (HTML, CSS e JavaScript puro).
