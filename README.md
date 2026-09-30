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

Se as duas chaves estiverem definidas, a da OpenAI é usada.

## Estrutura

- `app.py` — servidor FastAPI; monta o prompt de sistema (formato, tom e idioma) e faz streaming da resposta do provedor.
- `static/` — interface web (HTML, CSS e JavaScript puro).
