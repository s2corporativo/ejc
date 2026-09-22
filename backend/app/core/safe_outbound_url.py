"""HTTP outbound seguro para URLs controladas pelo usuário.

Evita SSRF e DNS rebinding validando todos os IPs resolvidos e conectando
diretamente ao IP público aprovado. O hostname original é preservado em
Host/SNI para manter virtual-host e validação TLS corretos.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx


def validar_url_publica(
    url: str, *, exigir_https: bool = False, rotulo: str = "URL"
) -> str:
    """Valida esquema/host e retorna o primeiro IP público resolvido."""
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise ValueError(f"{rotulo} deve usar http(s)")
    if exigir_https and p.scheme != "https":
        raise ValueError(f"{rotulo} deve usar https em produção")
    if p.username is not None or p.password is not None:
        raise ValueError(f"{rotulo} não aceita credenciais na URL")
    host = p.hostname
    if not host:
        raise ValueError(f"{rotulo} sem host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"host de {rotulo} não resolve") from exc

    ips_validos: list[str] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                f"{rotulo} aponta para endereço privado/loopback (bloqueado)"
            )
        ips_validos.append(str(ip))
    if not ips_validos:
        raise ValueError(f"host de {rotulo} não resolve para IP utilizável")
    return ips_validos[0]


def url_com_ip_fixado(url: str, ip: str) -> tuple[str, str]:
    """Retorna URL com IP fixado e hostname original para Host/SNI."""
    p = urlparse(url)
    host = p.hostname or ""
    porta = f":{p.port}" if p.port else ""
    ip_fmt = f"[{ip}]" if ":" in ip else ip
    return p._replace(netloc=f"{ip_fmt}{porta}").geturl(), host


async def buscar_url_publica(
    url: str,
    *,
    timeout: float = 20.0,
    max_redirects: int = 5,
    exigir_https: bool = False,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """GET seguro com IP pinning e revalidação a cada redirect."""
    atual = url
    base_headers = dict(headers or {})
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as cli:
        for salto in range(max_redirects + 1):
            ip = validar_url_publica(atual, exigir_https=exigir_https, rotulo="URL")
            destino, host = url_com_ip_fixado(atual, ip)
            resp = await cli.get(
                destino,
                headers={**base_headers, "Host": host},
                extensions={"sni_hostname": host},
            )
            if not resp.is_redirect:
                return resp
            if salto >= max_redirects:
                raise ValueError("redirecionamentos demais")
            location = resp.headers.get("location", "")
            if not location:
                raise ValueError("redirect sem destino")
            atual = urljoin(atual, location)
    raise ValueError("redirecionamentos demais")
