"""Motor puro da Agenda v2 — issue #1342 (AP-16/17/18).

Este módulo não conhece banco, usuário, caso nem autorização. Ele concentra as
regras temporais que o router SQL cru de ``agenda_eventos`` consumirá quando a
migration aditiva correspondente puder ser criada de acordo com o ledger
Alembic. Manter a lógica fora do router reduz risco de regressão e permite testar
intervalos/recorrência sem depender de PostgreSQL.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "America/Sao_Paulo"
MAX_OCORRENCIAS = 366
MAX_LEMBRETE_MINUTOS = 60 * 24 * 90

FrequenciaRecorrencia = Literal["diaria", "semanal", "mensal"]

# Preserva o comportamento operacional já existente para audiência:
# D-3, D-1 e no dia. Outros tipos continuam sem lembrete automático até que o
# usuário configure explicitamente — não ampliamos notificações silenciosamente.
DEFAULT_LEMBRETES_MINUTOS: dict[str, tuple[int, ...]] = {
    "audiencia": (3 * 24 * 60, 24 * 60, 0),
    "reuniao": (),
    "compromisso": (),
    "diligencia": (),
    "outro": (),
}


class AgendaTemporalError(ValueError):
    """Entrada temporal inválida da Agenda v2."""


@dataclass(frozen=True, slots=True)
class IntervaloAgenda:
    inicio: datetime
    fim: datetime
    timezone: str
    dia_inteiro: bool = False

    @property
    def duracao_minutos(self) -> int:
        return int((self.fim - self.inicio).total_seconds() // 60)


@dataclass(frozen=True, slots=True)
class RegraRecorrencia:
    frequencia: FrequenciaRecorrencia
    intervalo: int = 1
    quantidade: int | None = None
    ate: datetime | None = None


def timezone_valido(nome: str) -> ZoneInfo:
    valor = (nome or "").strip()
    if not valor:
        raise AgendaTemporalError("timezone é obrigatório")
    try:
        return ZoneInfo(valor)
    except ZoneInfoNotFoundError as exc:
        raise AgendaTemporalError(f"timezone inválido: {valor}") from exc


def _aware_local(valor: datetime, tz: ZoneInfo) -> datetime:
    """Interpreta datetime naive no timezone informado; aware é convertido."""
    if valor.tzinfo is None:
        return valor.replace(tzinfo=tz)
    return valor.astimezone(tz)


def normalizar_intervalo(
    *,
    inicio_em: datetime,
    fim_em: datetime | None,
    timezone: str = DEFAULT_TIMEZONE,
    dia_inteiro: bool = False,
) -> IntervaloAgenda:
    tz = timezone_valido(timezone)
    inicio = _aware_local(inicio_em, tz)

    if dia_inteiro:
        # Eventos de dia inteiro usam intervalo semiaberto [00:00, 00:00 do dia
        # seguinte). Isso elimina ambiguidade e permite detectar sobreposição.
        inicio = datetime.combine(inicio.date(), time.min, tzinfo=tz)
        if fim_em is None:
            fim = inicio + timedelta(days=1)
        else:
            fim_local = _aware_local(fim_em, tz)
            fim_data = fim_local.date()
            if fim_local.time() != time.min:
                fim_data += timedelta(days=1)
            fim = datetime.combine(fim_data, time.min, tzinfo=tz)
            if fim <= inicio:
                fim = inicio + timedelta(days=1)
    else:
        if fim_em is None:
            raise AgendaTemporalError("fim_em é obrigatório quando dia_inteiro=false")
        fim = _aware_local(fim_em, tz)
        if fim <= inicio:
            raise AgendaTemporalError("fim_em deve ser posterior a inicio_em")

    return IntervaloAgenda(
        inicio=inicio,
        fim=fim,
        timezone=timezone,
        dia_inteiro=dia_inteiro,
    )


def intervalos_sobrepoem(a: IntervaloAgenda, b: IntervaloAgenda) -> bool:
    """Sobreposição real em intervalos semiabertos; bordas encostadas não colidem."""
    inicio_a = a.inicio.astimezone(ZoneInfo("UTC"))
    fim_a = a.fim.astimezone(ZoneInfo("UTC"))
    inicio_b = b.inicio.astimezone(ZoneInfo("UTC"))
    fim_b = b.fim.astimezone(ZoneInfo("UTC"))
    return inicio_a < fim_b and inicio_b < fim_a


def normalizar_lembretes(
    valores: Iterable[int] | None,
    *,
    tipo: str,
) -> tuple[int, ...]:
    """Retorna offsets em minutos, únicos e do maior para o menor.

    ``None`` significa "usar default do tipo"; lista vazia significa "sem
    lembretes". Esse detalhe permite desligar explicitamente os defaults de
    audiência sem confundir ausência de configuração com escolha do usuário.
    """
    if valores is None:
        return DEFAULT_LEMBRETES_MINUTOS.get(tipo, ())

    normalizados: set[int] = set()
    for bruto in valores:
        if isinstance(bruto, bool) or not isinstance(bruto, int):
            raise AgendaTemporalError("lembretes devem ser minutos inteiros")
        if bruto < 0:
            raise AgendaTemporalError("lembrete não pode ser negativo")
        if bruto > MAX_LEMBRETE_MINUTOS:
            raise AgendaTemporalError("lembrete excede o limite de 90 dias")
        normalizados.add(bruto)
    return tuple(sorted(normalizados, reverse=True))


def instantes_lembrete(
    intervalo: IntervaloAgenda,
    offsets_minutos: Iterable[int],
) -> tuple[datetime, ...]:
    return tuple(
        intervalo.inicio - timedelta(minutes=minutos)
        for minutos in normalizar_lembretes(offsets_minutos, tipo="outro")
    )


def validar_regra_recorrencia(regra: RegraRecorrencia) -> None:
    if regra.intervalo < 1:
        raise AgendaTemporalError("intervalo da recorrência deve ser >= 1")
    if regra.quantidade is not None:
        if regra.quantidade < 1:
            raise AgendaTemporalError("quantidade da recorrência deve ser >= 1")
        if regra.quantidade > MAX_OCORRENCIAS:
            raise AgendaTemporalError(
                f"quantidade da recorrência excede {MAX_OCORRENCIAS} ocorrências"
            )
    if regra.quantidade is None and regra.ate is None:
        raise AgendaTemporalError("recorrência exige quantidade ou data limite")


def _adicionar_meses(
    valor: datetime,
    meses: int,
    *,
    dia_ancora: int | None = None,
) -> datetime:
    indice = (valor.month - 1) + meses
    ano = valor.year + indice // 12
    mes = indice % 12 + 1
    alvo = dia_ancora if dia_ancora is not None else valor.day
    dia = min(alvo, calendar.monthrange(ano, mes)[1])
    return valor.replace(year=ano, month=mes, day=dia)


def _inicio_ocorrencia(
    base_inicio: datetime,
    regra: RegraRecorrencia,
    indice_ocorrencia: int,
) -> datetime:
    """Calcula cada ocorrência a partir da âncora original, evitando deriva."""
    saltos = regra.intervalo * indice_ocorrencia
    if regra.frequencia == "diaria":
        return base_inicio + timedelta(days=saltos)
    if regra.frequencia == "semanal":
        return base_inicio + timedelta(weeks=saltos)
    if regra.frequencia == "mensal":
        return _adicionar_meses(
            base_inicio,
            saltos,
            dia_ancora=base_inicio.day,
        )
    raise AgendaTemporalError(f"frequência inválida: {regra.frequencia}")


def expandir_recorrencia(
    base: IntervaloAgenda,
    regra: RegraRecorrencia,
    *,
    excecoes_inicio: Iterable[datetime] = (),
) -> tuple[IntervaloAgenda, ...]:
    """Expande série com limite rígido; exceção remove só a ocorrência indicada.

    Cada ocorrência é derivada da âncora original, não da ocorrência anterior.
    Assim, uma série mensal iniciada em dia 31 usa o último dia de fevereiro mas
    volta ao dia 31 em março, em vez de derivar permanentemente para o dia 28.
    """
    validar_regra_recorrencia(regra)
    tz = timezone_valido(base.timezone)
    base_inicio = base.inicio.astimezone(tz)
    duracao = base.fim.astimezone(tz) - base_inicio
    excecoes = {
        _aware_local(valor, tz).isoformat()
        for valor in excecoes_inicio
    }
    limite = regra.ate
    if limite is not None:
        limite = _aware_local(limite, tz)

    resultados: list[IntervaloAgenda] = []
    geradas = 0
    while geradas < MAX_OCORRENCIAS:
        atual = _inicio_ocorrencia(base_inicio, regra, geradas)
        if limite is not None and atual > limite:
            break
        geradas += 1
        if atual.isoformat() not in excecoes:
            resultados.append(
                IntervaloAgenda(
                    inicio=atual,
                    fim=atual + duracao,
                    timezone=base.timezone,
                    dia_inteiro=base.dia_inteiro,
                )
            )
        if regra.quantidade is not None and geradas >= regra.quantidade:
            break

    if geradas >= MAX_OCORRENCIAS and regra.quantidade is None:
        # Uma data limite muito distante não pode transformar um request em lote
        # ilimitado; o caller deve paginar/materializar por janela.
        raise AgendaTemporalError(
            f"recorrência excede o limite de {MAX_OCORRENCIAS} ocorrências"
        )
    return tuple(resultados)


def legado_para_intervalo(
    *,
    data_evento: date,
    hora: str | None,
    timezone: str = DEFAULT_TIMEZONE,
    duracao_padrao_minutos: int = 60,
) -> IntervaloAgenda | None:
    """Adapter somente para leitura/transição; não inventa horário ausente.

    Evento legado sem ``hora`` retorna ``None`` em vez de receber 00:00 ou uma
    duração fictícia. Quando há hora válida HH:MM, a duração padrão serve apenas
    para detecção conservadora durante a migração e deve ser identificada como
    legado pelo caller — não deve ser persistida como fato histórico.
    """
    if not hora or not hora.strip():
        return None
    try:
        hora_local = time.fromisoformat(hora.strip())
    except ValueError as exc:
        raise AgendaTemporalError("hora legada inválida; esperado HH:MM") from exc
    if duracao_padrao_minutos < 1:
        raise AgendaTemporalError("duração padrão deve ser positiva")
    inicio = datetime.combine(data_evento, hora_local)
    fim = inicio + timedelta(minutes=duracao_padrao_minutos)
    return normalizar_intervalo(
        inicio_em=inicio,
        fim_em=fim,
        timezone=timezone,
        dia_inteiro=False,
    )
