"""Contrato do pré-voo e do resumo do workflow `Deploy VPS`.

O deploy automático morreu em 2026-08-06 e ficou morto por um dia sem que o
sintoma dissesse o porquê. Este arquivo trava as quatro propriedades que a
correção estabeleceu — todas escritas como invariante, não como texto:

1. **`dubious ownership`.** O `actions/checkout` registra `safe.directory` num
   HOME temporário que ele desfaz no post-cleanup; as etapas `run:` seguintes
   voltam a ver um repositório de outro dono e QUALQUER comando git morre. O
   pré-voo começa por `git rev-parse HEAD` — reprovava no primeiro comando, sem
   chegar a checar nada. Todo git do job precisa carregar a exceção, e ela só
   pode ser dada depois de conferir de quem é o workspace.

2. **Falha muda.** As pré-condições eram `test` puros, que não imprimem nada ao
   falhar. Cada uma precisa da sua própria mensagem.

3. **Reprovação silenciosa por `-e`.** O `shell: bash` do GitHub é
   `bash --noprofile --norc -eo pipefail {0}` — o `-e` vem LIGADO e nenhum
   `set -uo pipefail` o desliga. Uma checagem escrita sem `||` aborta o passo
   calada. O que se afirma aqui é a ausência de checagem desguarnecida, não a
   ausência de uma string: a primeira versão deste teste procurava
   `set -euo pipefail` no texto e passava enquanto a propriedade não valia.

4. **Resumo honesto.** A partir do `rsync` produção está reescrita, e o rollback
   restaura imagens — não a árvore nem o schema. Um resumo de dois estados
   afirmaria "nada foi implantado" numa falha de health check, que acontece
   depois de tudo já ter sido trocado.

A suíte lê o YAML fonte (sem depender de PyYAML), no mesmo padrão de
`test_governanca_workflow.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "deploy-vps.yml"

PASSO_PRE_VOO = "Confirmar SHA e runtime de produção"
PASSO_RESUMO = "Resumo da implantação"

# As seis pré-condições que o pré-voo verifica. Cada uma precisa de mensagem
# própria: uma reprovação sem nome custa uma rodada de deploy para diagnosticar.
PRE_CONDICOES = (
    "rev-parse",
    "/opt/ejc",
    "/opt/ejc/.env",
    "ejc_db",
    "python3",
    "rsync",
)


def _passos() -> dict[str, str]:
    """Mapa nome do step → corpo bruto, na ordem de declaração."""
    texto = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "\n    steps:" in texto, "deploy-vps.yml não declara `steps:` no job"
    corpo = texto.split("\n    steps:", 1)[1]
    blocos = re.split(r"\n      - name: ", corpo)[1:]
    passos: dict[str, str] = {}
    for bloco in blocos:
        nome, _, resto = bloco.partition("\n")
        passos[nome.strip()] = resto
    return passos


def _comandos(corpo: str) -> list[str]:
    """Linhas executáveis do step — sem comentários de YAML nem de shell.

    Os comentários deste workflow explicam por que o git morria; procurar `git`
    no texto bruto acharia a explicação e não o comando.
    """
    return [
        linha for linha in corpo.splitlines() if not linha.lstrip().startswith("#")
    ]


def _script(nome_do_passo: str) -> str:
    """Corpo do bloco `run: |` de um step, já sem a indentação do YAML.

    Sem PyYAML de propósito: ele não está em `requirements.txt`, e
    `test_governanca_workflow.py` já lê o YAML fonte pela mesma razão. Um teste
    que depende de dependência transitória quebra no dia em que ela sai.
    """
    corpo = _passos()[nome_do_passo]
    _, _, resto = corpo.partition("run: |\n")
    assert resto, f"o passo '{nome_do_passo}' não declara um bloco `run: |`"

    linhas = resto.splitlines()
    recuo = len(linhas[0]) - len(linhas[0].lstrip())
    saida: list[str] = []
    for linha in linhas:
        if linha.strip() and len(linha) - len(linha.lstrip()) < recuo:
            break  # dedentou: acabou o bloco escalar
        saida.append(linha[recuo:])
    return "\n".join(saida)


def _invoca_git(linha: str) -> bool:
    """Linha que EXECUTA git — não a que apenas cita o comando numa mensagem.

    As mensagens de reprovação citam o comando ("git rev-parse HEAD falhou"), e
    procurar `git` no texto cru acharia a citação. Apagar o conteúdo entre
    aspas também não serve: a chamada real é
    `"$(git -c safe.directory="$GITHUB_WORKSPACE" rev-parse HEAD)"`, cujas
    aspas aninhadas qualquer varredura ingênua recorta no lugar errado. Quem
    emite texto é `reprovar` ou `echo`; o resto é comando.
    """
    if re.match(r"\s*(reprovar|echo)\b", linha):
        return False
    # `git\s+\w` não serve: a chamada corrigida é `git -c …`, e o caractere
    # seguinte é um hífen.
    return bool(re.search(r"(^|[^\w-])git\s+[-\w]", linha))


def test_todo_comando_git_do_job_carrega_a_excecao_de_propriedade():
    """Sem a exceção, o comando morre em 'detected dubious ownership'.

    Afirmado sobre TODOS os steps, não sobre um passo nomeado: um `git` novo
    escrito sem `-c safe.directory` reintroduz exatamente o defeito de origem.
    """
    desguarnecidos = [
        (nome, linha.strip())
        for nome, corpo in _passos().items()
        for linha in _comandos(corpo)
        if _invoca_git(linha) and "safe.directory" not in linha
    ]
    assert not desguarnecidos, (
        "comando git sem `-c safe.directory` — volta a morrer em 'detected "
        f"dubious ownership' no runner self-hosted: {desguarnecidos}"
    )


def test_a_excecao_so_vale_depois_de_conferir_o_dono_do_workspace():
    """`safe.directory` desliga uma proteção real; não pode ser dada às cegas.

    Um `.git/config` hostil executa comando arbitrário (`core.fsmonitor`) já no
    `rev-parse`. Confiar no workspace é aceitável porque ele é do próprio
    runner — mas isso precisa ser VERIFICADO, não presumido.
    """
    corpo = _passos()[PASSO_PRE_VOO]
    linhas = _comandos(corpo)
    texto = "\n".join(linhas)

    assert "stat -c %u" in texto and "id -u" in texto, (
        "o pré-voo não confere de quem é o workspace antes de confiar nele"
    )

    i_dono = next(i for i, ln in enumerate(linhas) if "stat -c %u" in ln)
    i_git = next(i for i, ln in enumerate(linhas) if _invoca_git(ln))
    assert i_dono < i_git, (
        "o git roda antes da conferência de dono — a verificação não protege "
        "nada se o comando que ela deveria condicionar já executou"
    )


def test_cada_pre_condicao_do_pre_voo_se_identifica_ao_reprovar():
    """`test` puro não imprime nada; a falha precisa dizer qual checagem caiu."""
    corpo = _passos()[PASSO_PRE_VOO]
    assert "::error::" in corpo, (
        "o pré-voo não emite nenhum ::error:: — a falha volta a ser muda"
    )

    for marcador in PRE_CONDICOES:
        assert marcador in corpo, f"pré-condição '{marcador}' sumiu do pré-voo"

    # Uma chamada a `reprovar` por pré-condição, mais as do bloco de propriedade.
    # Contar `::error::` não serve: ele aparece uma vez, dentro do helper.
    mensagens = re.findall(r'reprovar "([^"]+)"', corpo)
    assert len(mensagens) > len(PRE_CONDICOES), (
        f"{len(mensagens)} mensagens para {len(PRE_CONDICOES)} pré-condições — "
        "alguma reprova sem se identificar"
    )
    assert len(set(mensagens)) == len(mensagens), (
        "duas pré-condições compartilham a mesma mensagem — a reprovação deixa "
        "de dizer qual delas caiu"
    )


def test_nenhuma_checagem_do_pre_voo_pode_abortar_o_passo_em_silencio():
    """O `-e` do `shell: bash` do GitHub continua ativo; só `set +e` o desliga.

    Esta é a propriedade que a versão anterior deste teste ACHOU que estava
    afirmando ao procurar a string `set -euo pipefail`. Aqui ela é afirmada de
    verdade: o passo desliga o `-e` explicitamente e nenhuma checagem fica sem
    o seu `||`.
    """
    corpo = _passos()[PASSO_PRE_VOO]
    linhas = _comandos(corpo)

    assert any(ln.strip() == "set +e" for ln in linhas), (
        "o pré-voo não desliga o `-e` que o `shell: bash` do GitHub liga por "
        "padrão — uma checagem sem `||` abortaria o passo calada"
    )

    # Checagem = linha que testa condição. Só é segura se emendar num `||`,
    # aqui ou na linha seguinte (o arquivo quebra as mensagens em duas linhas).
    emendadas = "\n".join(linhas).replace("||\n", "|| ")
    nuas = [
        ln.strip()
        for ln in emendadas.splitlines()
        if re.match(r"\s*(\[|test |command -v|docker ps)", ln) and "||" not in ln
    ]
    assert not nuas, (
        f"checagem sem `||` no pré-voo: {nuas} — reprova sem imprimir nada"
    )

    assert re.search(r"exit 1", corpo), "o pré-voo precisa reprovar o job ao fim"


def _resumo(job_status: str, sync_outcome: str, tmp_path) -> str:
    """Executa o `run:` do resumo de verdade e devolve o que ele escreveu.

    Grep no YAML provaria só que certas palavras existem no arquivo — não que a
    ramificação escolhe a certa. O `run:` do resumo é bash puro sobre variáveis
    de ambiente (as expressões saíram para `env:`), então dá para rodá-lo.
    """
    import subprocess

    script = _script(PASSO_RESUMO)
    # Arquivo próprio por invocação: o resumo APENDA (`>>`), como o GitHub
    # espera, então reusar o mesmo caminho misturaria as saídas e faria um
    # cenário passar com o texto do anterior.
    saida = tmp_path / f"summary-{job_status}-{sync_outcome or 'vazio'}.md"
    subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        check=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GITHUB_STEP_SUMMARY": str(saida),
            "JOB_STATUS": job_status,
            "SYNC_OUTCOME": sync_outcome,
            "TARGET_SHA": "0" * 40,
            "REVISAO_ANTERIOR": "126_case_status",
            "MIGRATIONS_PENDENTES": "0",
            "RUN_SEEDS": "1",
            "REQUIRE_PREDEPLOY_BACKUP": "1",
        },
    )
    return saida.read_text(encoding="utf-8")


def test_resumo_so_afirma_producao_intacta_quando_o_rsync_nao_rodou(tmp_path):
    """`failure` no rsync NÃO prova que produção está intacta.

    `rsync --delete` reescreve e apaga arquivo a arquivo e só então retorna
    erro: pode ter mexido em `/opt/ejc` e falhado no meio. Dizer "nada foi
    implantado" aí é pior que o defeito original, porque produção fica num
    estado parcial que ninguém vai conferir.

    O rollback do `deploy_vps_safe.sh` restaura imagens — não a árvore nem o
    schema —, então a distinção não é cosmética.
    """
    intacta = "nada foi implantado"

    # Único caso em que produção comprovadamente não foi tocada.
    for outcome in ("skipped", ""):
        texto = _resumo("failure", outcome, tmp_path)
        assert intacta in texto, f"outcome={outcome!r} devia acusar produção intacta"

    # rsync concluiu: produção foi tocada, com certeza.
    texto = _resumo("failure", "success", tmp_path)
    assert "APÓS TOCAR PRODUÇÃO" in texto
    assert intacta not in texto

    # rsync não concluiu: NÃO se sabe. Precisa dizer que não sabe.
    for outcome in ("failure", "cancelled"):
        texto = _resumo("failure", outcome, tmp_path)
        assert intacta not in texto, (
            f"outcome={outcome!r}: o resumo afirma que produção está intacta "
            "sem ter como saber — o rsync pode ter falhado no meio da escrita"
        )
        assert "ESTADO INCERTO" in texto

    # E o caminho feliz continua dizendo o que sempre disse.
    assert "**implantado**" in _resumo("success", "success", tmp_path)


def test_o_passo_do_rsync_mantem_o_id_que_o_resumo_consulta():
    sync = _passos()["Sincronizar checkout aprovado para /opt/ejc"]
    assert re.search(r"^\s*id:\s*sync\s*$", sync, re.M), (
        "o passo do rsync perdeu o `id: sync` — sem ele `steps.sync.outcome` "
        "chega vazio e toda falha vira 'nada foi implantado'"
    )
    assert "steps.sync.outcome" in _passos()[PASSO_RESUMO]


def test_valores_de_dado_nao_viram_texto_de_script_no_resumo():
    """`current_revision` vem de um SELECT no banco de produção.

    Interpolado direto no `run:`, um `version_num` com aspas e `$(...)` viraria
    execução de comando. Por `env:`, é dado.
    """
    corpo = _passos()[PASSO_RESUMO]
    corpo_run = corpo.split("run: |", 1)[1] if "run: |" in corpo else corpo
    interpolacoes = re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", corpo_run)
    assert not interpolacoes, (
        "expressão interpolada dentro do `run:` do resumo — passe por `env:`: "
        f"{interpolacoes}"
    )
