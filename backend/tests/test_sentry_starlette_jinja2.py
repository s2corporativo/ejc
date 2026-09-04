# -*- coding: utf-8 -*-
"""`jinja2` é requisito do sentry-sdk[fastapi], não template engine órfã.

Regressão real, introduzida por mim no #1316 e detectada só pelo CI: ao apagar
`core/document_template_engine.py` como código morto, removi `jinja2` do
`requirements.txt` junto — o engine era o único importador DIRETO. Só que o
sentry-sdk também precisa dela, por um caminho que nenhuma busca por `import
jinja2` encontra:

    StarletteIntegration.setup_once()
      └─ patch_templates()
           ├─ `import markupsafe` → decide se "há Jinja2 no ambiente"
           └─ `from starlette.templating import Jinja2Templates`

O guarda do sentry (2.13.0) assume que **markupsafe presente implica Jinja2
presente**, porque markupsafe é dependência do Jinja2. A premissa é falsa aqui:
`markupsafe` continua instalado puxado por **Mako**, que vem do Alembic. Sem
jinja2, o `from starlette.templating import ...` levanta
`ImportError: jinja2 must be installed`, o erro ESCAPA do `setup_once()`, e a
integração não registra — só que os patches dela já foram instalados. A partir
daí, todo request que passa pelo handler de exceção patcheado lê
`integration.failed_request_status_codes` de um `None`:

    AttributeError: 'NoneType' object has no attribute 'failed_request_status_codes'

Foram **56 testes** reprovando na `main`. Não aparecia para quem já tinha jinja2
no ambiente — só em instalação limpa, que é exatamente o que o CI faz. Foi o que
me escapou: rodei a suíte inteira várias vezes num venv anterior à remoção.

Este teste checa a PRÉ-CONDIÇÃO de propósito, em vez de inicializar o Sentry:
`sentry_sdk.init()` tem efeito global e poluiria os outros testes — que é o
próprio modo de falha aqui. O import é o que decide, e é o que quebra se alguém
"limpar" a dependência de novo.
"""
from __future__ import annotations

import importlib.util


def test_jinja2_esta_instalada():
    """Se cair, `requirements.txt` perdeu jinja2 — leia o comentário de lá."""
    assert importlib.util.find_spec("jinja2") is not None, (
        "jinja2 sumiu do ambiente: o sentry-sdk[fastapi] não vai registrar a "
        "StarletteIntegration e ~56 testes reprovam com AttributeError em "
        "'NoneType'.failed_request_status_codes"
    )


def test_starlette_templating_importa():
    """O import EXATO que o `patch_templates()` do sentry faz."""
    from starlette.templating import Jinja2Templates

    assert Jinja2Templates is not None


def test_markupsafe_sozinha_nao_garante_jinja2():
    """Documenta por que o guarda do sentry não basta — e por que este teste existe.

    O sentry deduz a presença de Jinja2 a partir de markupsafe. Aqui markupsafe
    chega por Mako (Alembic), então ela estaria presente mesmo sem jinja2 e o
    guarda passaria batido. É isso que torna a dependência fácil de remover por
    engano e obrigatória de travar por teste.
    """
    assert importlib.util.find_spec("markupsafe") is not None
    assert importlib.util.find_spec("mako") is not None, (
        "Mako saiu do ambiente: reavalie este teste — a premissa quebrada do "
        "sentry dependia dela para manter markupsafe instalada sem jinja2"
    )
