
import json
import os
import re
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucnovodashboard",
]

CONTRATOS_URL = os.getenv(
    "FOCCO_CONTRATOS_URL",
    "https://web.foccolojas.com.br/criare/wbpvencontratos"
)

STATUS_VALIDOS = {
    "Pendente",
    "Cancelado",
    "Liberado",
    "Ativo",
    "Finalizado",
    "Em Andamento",
    "Suspenso",
    "Bloqueado",
}

CLEAR_FILTER_CONTAINER_SELECTORS = [
    "#LIMPARFILTROS",
    "[data-gx-cntrl='LIMPARFILTROS']",
    "#DIVLIMPAFILTRO",
    "#DIVLIMPARFILTRO",
]

CLEAR_FILTER_LINK_SELECTORS = [
    "#DIVLIMPAFILTRO a",
    "#DIVLIMPARFILTRO a",
    "#LIMPARFILTROS a",
    "[data-gx-cntrl='LIMPARFILTROS'] a",
    "a[data-gx-evt='5'][data-gx-evt-control='LIMPARFILTROS']",
    "a:has-text('Limpar Filtros')",
    "a:has-text('LIMPAR FILTROS')",
]


def is_dashboard(page):
    url = page.url or ""
    return any(part in url for part in DASHBOARD_URL_PARTS)


def find_in_any_frame(page, selector: str, timeout_ms: int = 3000):
    for frame in page.frames:
        try:
            loc = frame.locator(selector).first
            loc.wait_for(state="attached", timeout=timeout_ms)
            return frame, loc
        except Exception:
            pass
    return None, None


def set_value(frame, selector, value):
    frame.eval_on_selector(
        selector,
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """,
        value,
    )


def has_login_form(page):
    frame_user, _ = find_in_any_frame(page, "#vIPN_USU_LOGIN", 2000)
    frame_pass, _ = find_in_any_frame(page, "#vIPN_USU_SENHA", 2000)
    frame_btn, _ = find_in_any_frame(page, "#BTNLOGIN", 2000)

    return (
        frame_user is not None
        and frame_pass is not None
        and frame_btn is not None
    )


def do_login(page):
    frame_user, _ = find_in_any_frame(page, "#vIPN_USU_LOGIN", 5000)
    frame_pass, _ = find_in_any_frame(page, "#vIPN_USU_SENHA", 5000)
    frame_btn, _ = find_in_any_frame(page, "#BTNLOGIN", 5000)

    if not frame_user:
        raise Exception("Campo usuário não encontrado em nenhum frame")

    if not frame_pass:
        raise Exception("Campo senha não encontrado em nenhum frame")

    if not frame_btn:
        raise Exception("Botão entrar não encontrado em nenhum frame")

    set_value(frame_user, "#vIPN_USU_LOGIN", FOCCO_USERNAME)
    set_value(frame_pass, "#vIPN_USU_SENHA", FOCCO_PASSWORD)
    frame_btn.locator("#BTNLOGIN").click(force=True)


def garantir_login(page, resultado):
    page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    if is_dashboard(page):
        resultado["already_logged_in"] = True
        return True

    if has_login_form(page):
        do_login(page)
        page.wait_for_timeout(8000)
        resultado["login_executed"] = True
        return is_dashboard(page)

    return False


def _safe_eval(locator, script):
    try:
        return locator.evaluate(script)
    except Exception:
        return None


def _estado_elemento(locator):
    return _safe_eval(
        locator,
        """
        (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return {
                tag: (el.tagName || '').toLowerCase(),
                id: el.id || null,
                class_name: el.className || '',
                style_attr: el.getAttribute('style') || '',
                data_gx_cntrl: el.getAttribute('data-gx-cntrl') || '',
                data_gx_evt: el.getAttribute('data-gx-evt') || '',
                data_gx_evt_control: el.getAttribute('data-gx-evt-control') || '',
                text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
                display: style.display || '',
                visibility: style.visibility || '',
                opacity: style.opacity || '',
                width: rect.width || 0,
                height: rect.height || 0,
                hidden_attr: el.hasAttribute('hidden'),
                aria_hidden: el.getAttribute('aria-hidden') || null,
                has_gx_invisible: (el.className || '').includes('gx-invisible'),
                is_visible: (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    rect.width > 0 &&
                    rect.height > 0 &&
                    !el.hasAttribute('hidden')
                ),
            };
        }
        """,
    )


def obter_estado_tela_contratos(page):
    resumo = {
        "url": page.url,
        "contratos_visiveis_qtd": 0,
        "contratos_visiveis_amostra": [],
        "assinatura_visivel": "",
    }

    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const anchors = Array.from(document.querySelectorAll('a[href*="wbpvencontrato"]'))
            .filter(a => isVisible(a))
            .map(a => normalizar(a.innerText || a.textContent || ''))
            .filter(Boolean);

        return {
            contratos_visiveis_qtd: anchors.length,
            contratos_visiveis_amostra: anchors.slice(0, 15),
            assinatura_visivel: anchors.join('|'),
        };
    }
    """

    for frame in page.frames:
        try:
            dados = frame.evaluate(script)
            if dados and (dados.get("contratos_visiveis_qtd") or 0) > 0:
                resumo.update(dados)
                return resumo
        except Exception:
            pass

    return resumo


def obter_estado_limpar_filtros(page):
    estado_padrao = {
        "encontrado": False,
        "selector": None,
        "frame_url": None,
        "container": None,
        "anchor": None,
        "disponivel_para_limpar": False,
        "ja_estava_oculto_ou_limpo": False,
    }

    for frame in page.frames:
        # 1) tenta primeiro no container
        for selector in CLEAR_FILTER_CONTAINER_SELECTORS:
            try:
                loc = frame.locator(selector).first
                if loc.count() == 0:
                    continue

                container = _estado_elemento(loc)
                if not container:
                    continue

                anchor = None
                try:
                    link_loc = loc.locator("a").first
                    if link_loc.count() > 0:
                        anchor = _estado_elemento(link_loc)
                except Exception:
                    pass

                encontrado = True
                anchor_visible = bool(anchor and anchor.get("is_visible"))
                container_visible = bool(container.get("is_visible"))
                has_gx_invisible = bool(container.get("has_gx_invisible")) or bool(anchor and anchor.get("has_gx_invisible"))

                disponivel = (anchor_visible or container_visible) and not has_gx_invisible
                ja_oculto = (
                    has_gx_invisible
                    or container.get("display") == "none"
                    or not (anchor_visible or container_visible)
                )

                return {
                    "encontrado": encontrado,
                    "selector": selector,
                    "frame_url": frame.url,
                    "container": container,
                    "anchor": anchor,
                    "disponivel_para_limpar": disponivel,
                    "ja_estava_oculto_ou_limpo": ja_oculto and not disponivel,
                }
            except Exception:
                pass

        # 2) fallback só pelo link visível
        for selector in CLEAR_FILTER_LINK_SELECTORS:
            try:
                loc = frame.locator(selector).first
                if loc.count() == 0:
                    continue

                anchor = _estado_elemento(loc)
                if not anchor:
                    continue

                return {
                    "encontrado": True,
                    "selector": selector,
                    "frame_url": frame.url,
                    "container": None,
                    "anchor": anchor,
                    "disponivel_para_limpar": bool(anchor.get("is_visible")),
                    "ja_estava_oculto_ou_limpo": not bool(anchor.get("is_visible")),
                }
            except Exception:
                pass

    return estado_padrao


def encontrar_link_limpar_filtros_clicavel(page):
    for frame in page.frames:
        for selector in CLEAR_FILTER_LINK_SELECTORS:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    return frame, loc, selector
            except Exception:
                pass
    return None, None, None


def limpar_filtros_se_existir(page):
    tela_antes = obter_estado_tela_contratos(page)
    estado_antes = obter_estado_limpar_filtros(page)

    retorno = {
        "encontrado": estado_antes["encontrado"],
        "clicado": False,
        "confirmado": False,
        "ja_estava_limpo": False,
        "selector": estado_antes["selector"],
        "mensagem": "",
        "estado_antes": estado_antes,
        "estado_depois": None,
        "tela_antes": tela_antes,
        "tela_depois": None,
    }

    if not estado_antes["encontrado"]:
        retorno["confirmado"] = True
        retorno["ja_estava_limpo"] = True
        retorno["mensagem"] = "Limpar filtros não encontrado; seguindo sem clicar"
        retorno["estado_depois"] = estado_antes
        retorno["tela_depois"] = tela_antes
        return retorno

    if not estado_antes["disponivel_para_limpar"]:
        retorno["confirmado"] = True
        retorno["ja_estava_limpo"] = True
        retorno["mensagem"] = "Limpar filtros encontrado, mas já estava oculto/indisponível"
        retorno["estado_depois"] = estado_antes
        retorno["tela_depois"] = tela_antes
        return retorno

    frame, loc, selector = encontrar_link_limpar_filtros_clicavel(page)
    retorno["selector"] = selector or retorno["selector"]

    if not loc:
        retorno["mensagem"] = "Estado indicava botão visível, mas o link clicável não foi localizado"
        retorno["estado_depois"] = obter_estado_limpar_filtros(page)
        retorno["tela_depois"] = obter_estado_tela_contratos(page)
        return retorno

    try:
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        loc.click(force=True, timeout=5000)
        retorno["clicado"] = True

        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        confirmado = False
        estado_depois = None

        for _ in range(20):
            page.wait_for_timeout(500)
            estado_depois = obter_estado_limpar_filtros(page)

            if (
                not estado_depois["encontrado"]
                or not estado_depois["disponivel_para_limpar"]
                or estado_depois["ja_estava_oculto_ou_limpo"]
            ):
                confirmado = True
                break

        tela_depois = obter_estado_tela_contratos(page)

        retorno["confirmado"] = confirmado
        retorno["estado_depois"] = estado_depois
        retorno["tela_depois"] = tela_depois

        if confirmado:
            retorno["mensagem"] = "Limpar filtros clicado e ocultação do botão confirmada"
        else:
            retorno["mensagem"] = "Limpar filtros clicado, mas não foi possível confirmar a mudança visual"

        return retorno

    except Exception as e:
        retorno["mensagem"] = f"Limpar filtros encontrado, mas erro ao clicar: {str(e)}"
        retorno["estado_depois"] = obter_estado_limpar_filtros(page)
        retorno["tela_depois"] = obter_estado_tela_contratos(page)
        return retorno


def ajustar_linhas_por_pagina(page, valor="120"):
    valor = str(valor)

    script = """
    (valor) => {
        const textoAlvo = String(valor).trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const selects = Array.from(document.querySelectorAll('select')).filter(isVisible);
        for (const sel of selects) {
            const options = Array.from(sel.options || []).map(o => normalizar(o.text));
            if (options.includes(textoAlvo)) {
                const opt = Array.from(sel.options).find(o => normalizar(o.text) === textoAlvo);
                sel.value = opt.value;
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return { alterado: true, modo: 'select' };
            }
        }

        const candidatosAbrir = Array.from(document.querySelectorAll('div, span, a, button'));
        for (const el of candidatosAbrir) {
            const txt = normalizar(el.innerText || el.textContent || '');
            if (txt === 'Linhas por página:' && isVisible(el)) {
                const grupo = [
                    el.nextElementSibling,
                    el.parentElement,
                    el.closest('div')
                ].filter(Boolean);

                for (const alvo of grupo) {
                    try { alvo.click(); } catch (e) {}
                }
                break;
            }
        }

        const candidatosOpcao = Array.from(document.querySelectorAll('li, div, span, a, option'));
        for (const el of candidatosOpcao) {
            const txt = normalizar(el.innerText || el.textContent || '');
            if (txt === textoAlvo && isVisible(el)) {
                try {
                    el.click();
                    return { alterado: true, modo: 'menu' };
                } catch (e) {}
            }
        }

        return { alterado: false, modo: null };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script, valor)
            if res and res.get("alterado"):
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                return {
                    "alterado": True,
                    "valor": valor,
                    "mensagem": f"Linhas por página ajustado para {valor}",
                    "modo": res.get("modo"),
                }
        except Exception:
            pass

    return {
        "alterado": False,
        "valor": None,
        "mensagem": "Não foi possível ajustar linhas por página",
        "modo": None,
    }


def obter_info_paginacao(page):
    info = {
        "linhas_por_pagina": None,
        "intervalo_pagina": None,
    }

    for frame in page.frames:
        try:
            texto = frame.locator("body").inner_text(timeout=1000)

            if "Linhas por página:" in texto and info["linhas_por_pagina"] is None:
                partes = texto.split("Linhas por página:")
                if len(partes) > 1:
                    trecho = partes[1].strip().splitlines()[0].strip()
                    info["linhas_por_pagina"] = trecho.split()[0]

            m = re.search(r"\b\d+\s*-\s*\d+\s+de\s+\d+\b", texto)
            if m and info["intervalo_pagina"] is None:
                info["intervalo_pagina"] = m.group(0)
        except Exception:
            pass

    return info


def _limpar_texto(valor):
    if valor is None:
        return None
    return " ".join(str(valor).split()).strip()


def _unicos(seq):
    vistos = set()
    resultado = []
    for item in seq:
        item = _limpar_texto(item)
        if not item:
            continue
        if item in vistos:
            continue
        vistos.add(item)
        resultado.append(item)
    return resultado


def _parece_data(txt):
    if not txt:
        return False
    if txt == "Não Informado":
        return True
    return bool(re.fullmatch(r"\d{2}/\d{2}/\d{4}", txt))


def _parece_valor(txt):
    if not txt:
        return False
    txt = txt.replace("R$", "").strip()
    return bool(re.fullmatch(r"[\d\.\,]+", txt)) and "," in txt


def _tem_letras(txt):
    if not txt:
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", txt))


def _melhor_candidato(candidatos, tipo, numero_contrato=None):
    candidatos = _unicos(candidatos)

    if numero_contrato:
        candidatos = [c for c in candidatos if c != numero_contrato]

    if not candidatos:
        return None

    if tipo == "projeto":
        preferidos = [
            c for c in candidatos
            if _tem_letras(c) and ("-" in c or re.match(r"^\d+\s*-\s*", c))
        ]
        if preferidos:
            return max(preferidos, key=len)

        preferidos = [c for c in candidatos if _tem_letras(c)]
        if preferidos:
            return max(preferidos, key=len)

        return max(candidatos, key=len)

    if tipo in {"cliente", "consultor", "executor"}:
        preferidos = [c for c in candidatos if _tem_letras(c)]
        if preferidos:
            return max(preferidos, key=len)
        return max(candidatos, key=len)

    if tipo == "valor_venda":
        preferidos = [c for c in candidatos if _parece_valor(c)]
        if preferidos:
            return preferidos[-1]
        return candidatos[-1]

    if tipo == "situacao":
        preferidos = [c for c in candidatos if c in STATUS_VALIDOS]
        if preferidos:
            return preferidos[0]

        preferidos = [c for c in candidatos if _tem_letras(c)]
        if preferidos:
            return preferidos[0]

        return candidatos[0]

    if tipo in {"assinatura", "previsao_entrega"}:
        preferidos = [c for c in candidatos if _parece_data(c)]
        if preferidos:
            return preferidos[0]
        return candidatos[-1]

    return candidatos[-1]


def extrair_contratos_visiveis(page):
    contratos = []
    vistos = set()

    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const anchors = Array.from(document.querySelectorAll('a[href*="wbpvencontrato"]'))
            .filter(a => isVisible(a));

        const resultado = [];

        for (const a of anchors) {
            const numeroContrato = normalizar(a.innerText || a.textContent || '');
            const href = a.getAttribute('href') || '';

            if (!numeroContrato) continue;

            const row =
                a.closest('div[id^="GridContainerRow_"]') ||
                a.closest('tr') ||
                a.parentElement;

            if (!row) continue;

            const visibleTds = Array.from(row.querySelectorAll('td'))
                .filter(td => isVisible(td));

            const grupos = visibleTds.map((td) => {
                const candidatos = [];

                const descendentes = Array.from(
                    td.querySelectorAll('a, span, div, label')
                ).filter(el => isVisible(el));

                for (const el of descendentes) {
                    const txt = normalizar(el.innerText || el.textContent || '');
                    if (txt) candidatos.push(txt);
                }

                const proprioTd = normalizar(td.innerText || td.textContent || '');
                if (proprioTd) candidatos.push(proprioTd);

                return Array.from(new Set(candidatos));
            });

            resultado.push({
                numero_contrato: numeroContrato,
                href,
                grupos,
                row_text: normalizar(row.innerText || row.textContent || ''),
                row_tag: row.tagName,
                row_id: row.id || ''
            });
        }

        return resultado;
    }
    """

    for frame in page.frames:
        try:
            rows = frame.evaluate(script)
        except Exception:
            continue

        for row in rows:
            numero = _limpar_texto(row.get("numero_contrato"))
            href = _limpar_texto(row.get("href"))
            grupos = row.get("grupos") or []

            if not numero:
                continue

            chave = f"{numero}|{href}"
            if chave in vistos:
                continue

            vistos.add(chave)

            grupos_limpos = [_unicos(g) for g in grupos if _unicos(g)]

            idx_contrato = None
            for i, grupo in enumerate(grupos_limpos):
                if numero in grupo:
                    idx_contrato = i
                    break

            if idx_contrato is None:
                continue

            grupos_campos = grupos_limpos[idx_contrato + 1: idx_contrato + 9]

            while len(grupos_campos) < 8:
                grupos_campos.append([])

            projeto = _melhor_candidato(grupos_campos[0], "projeto", numero)
            cliente = _melhor_candidato(grupos_campos[1], "cliente", numero)
            consultor = _melhor_candidato(grupos_campos[2], "consultor", numero)
            executor = _melhor_candidato(grupos_campos[3], "executor", numero)
            valor_venda = _melhor_candidato(grupos_campos[4], "valor_venda", numero)
            situacao = _melhor_candidato(grupos_campos[5], "situacao", numero)
            assinatura = _melhor_candidato(grupos_campos[6], "assinatura", numero)
            previsao_entrega = _melhor_candidato(grupos_campos[7], "previsao_entrega", numero)

            contrato = {
                "numero_contrato": numero,
                "url_contrato": urljoin(frame.url, href) if href else None,
                "projeto": projeto,
                "cliente": cliente,
                "consultor": consultor,
                "executor": executor,
                "valor_venda": valor_venda,
                "situacao": situacao,
                "assinatura": assinatura,
                "previsao_entrega": previsao_entrega,
                "row_text": _limpar_texto(row.get("row_text")),
                "debug_grupos": grupos_limpos,
                "debug_grupos_campos": grupos_campos,
                "debug_row_tag": row.get("row_tag"),
                "debug_row_id": row.get("row_id"),
            }

            contratos.append(contrato)

    def ordenar(c):
        n = c.get("numero_contrato") or ""
        return int(n) if str(n).isdigit() else 999999999

    contratos.sort(key=ordenar)
    return contratos


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "already_logged_in": False,
        "login_executed": False,
        "tela_contratos_aberta": False,
        "limpar_filtros_encontrado": False,
        "limpar_filtros_clicado": False,
        "limpar_filtros_confirmado": False,
        "limpar_filtros_ja_estava_limpo": False,
        "limpar_filtros_mensagem": "",
        "limpar_filtros_estado_antes": {},
        "limpar_filtros_estado_depois": {},
        "linhas_por_pagina_ajustado": False,
        "linhas_por_pagina_mensagem": "",
        "paginacao": {},
        "total_contratos_visiveis": 0,
        "contratos": [],
        "mensagem": "",
    }

    if not FOCCO_USERNAME or not FOCCO_PASSWORD:
        print(json.dumps({
            "success": False,
            "error": "FOCCO_USERNAME ou FOCCO_PASSWORD não configurados"
        }, ensure_ascii=False))
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            ok_login = garantir_login(page, resultado)

            if not ok_login:
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Não foi possível confirmar o login"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            page.goto(CONTRATOS_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(5000)

            resultado["tela_contratos_aberta"] = "/criare/wbpvencontratos" in (page.url or "")

            acao_limpar = limpar_filtros_se_existir(page)
            resultado["limpar_filtros_encontrado"] = acao_limpar["encontrado"]
            resultado["limpar_filtros_clicado"] = acao_limpar["clicado"]
            resultado["limpar_filtros_confirmado"] = acao_limpar["confirmado"]
            resultado["limpar_filtros_ja_estava_limpo"] = acao_limpar["ja_estava_limpo"]
            resultado["limpar_filtros_mensagem"] = acao_limpar["mensagem"]
            resultado["limpar_filtros_estado_antes"] = acao_limpar["estado_antes"]
            resultado["limpar_filtros_estado_depois"] = acao_limpar["estado_depois"]

            ajuste_pagina = ajustar_linhas_por_pagina(page, "120")
            resultado["linhas_por_pagina_ajustado"] = ajuste_pagina["alterado"]
            resultado["linhas_por_pagina_mensagem"] = ajuste_pagina["mensagem"]

            resultado["paginacao"] = obter_info_paginacao(page)
            resultado["contratos"] = extrair_contratos_visiveis(page)
            resultado["total_contratos_visiveis"] = len(resultado["contratos"])
            resultado["url_final"] = page.url

            if resultado["tela_contratos_aberta"]:
                resultado["success"] = True
                resultado["mensagem"] = (
                    f"Lista de contratos lida com sucesso. "
                    f"Contratos visíveis: {resultado['total_contratos_visiveis']}"
                )
            else:
                resultado["success"] = False
                resultado["mensagem"] = "Tela de contratos não foi confirmada"

            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao listar contratos visíveis: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()
