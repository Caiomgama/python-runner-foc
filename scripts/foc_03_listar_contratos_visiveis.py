
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

SELECTOR_LINHAS_POR_PAGINA = "select#vCOMBOLINHASGRID, select[id*='LINHASGRID']"


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
    return frame_user is not None and frame_pass is not None and frame_btn is not None


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


def _limpar_texto(valor):
    if valor is None:
        return None
    return " ".join(str(valor).split()).strip()


def _normalizar(texto):
    return _limpar_texto(texto) or ""


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


def obter_estado_limpar_filtros(page):
    seletores = [
        "[data-gx-cntrl='LIMPARFILTROS']",
        "#DIVLIMPAFILTRO a",
        "#DIVLIMPARFILTRO a",
        "#LIMPARFILTROS a",
        "a:has-text('Limpar Filtros')",
        "a:has-text('LIMPAR FILTROS')",
    ]

    script_estado = """
    (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        const pai = el.parentElement;
        const paiStyle = pai ? window.getComputedStyle(pai) : null;
        return {
            texto: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(),
            id: el.id || null,
            classe: el.className || null,
            display: style.display,
            visibility: style.visibility,
            width: rect.width,
            height: rect.height,
            visible: style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0,
            parent_id: pai ? (pai.id || null) : null,
            parent_class: pai ? (pai.className || null) : null,
            parent_display: paiStyle ? paiStyle.display : null,
            parent_visibility: paiStyle ? paiStyle.visibility : null,
            parent_hidden_by_class: !!(pai && String(pai.className || '').includes('gx-invisible')),
            href: el.getAttribute('href') || null,
            data_gx_evt: el.getAttribute('data-gx-evt') || null,
            data_gx_control: el.getAttribute('data-gx-evt-control') || null,
        };
    }
    """

    for frame in page.frames:
        for selector in seletores:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0:
                    estado = loc.evaluate(script_estado)
                    estado["selector"] = selector
                    estado["frame_url"] = frame.url
                    return {
                        "encontrado": True,
                        "selector": selector,
                        "estado": estado,
                    }
            except Exception:
                pass

    return {
        "encontrado": False,
        "selector": None,
        "estado": None,
    }


def obter_info_paginacao(page):
    info = {
        "linhas_por_pagina": None,
        "intervalo_pagina": None,
        "inicio_intervalo": None,
        "fim_intervalo": None,
        "total_registros": None,
    }

    # tenta primeiro pelo select visível
    for frame in page.frames:
        try:
            loc = frame.locator(SELECTOR_LINHAS_POR_PAGINA).first
            if loc.count() > 0:
                try:
                    if loc.is_visible():
                        valor = loc.input_value(timeout=1000)
                        if valor:
                            info["linhas_por_pagina"] = valor
                            break
                except Exception:
                    pass
        except Exception:
            pass

    for frame in page.frames:
        try:
            texto = frame.locator("body").inner_text(timeout=1000)

            if info["linhas_por_pagina"] is None and "Linhas por página:" in texto:
                partes = texto.split("Linhas por página:")
                if len(partes) > 1:
                    trecho = partes[1].strip().splitlines()[0].strip()
                    if trecho:
                        info["linhas_por_pagina"] = trecho.split()[0]

            m = re.search(r"\b(\d+)\s*-\s*(\d+)\s+de\s+(\d+)\b", texto)
            if m and info["intervalo_pagina"] is None:
                info["intervalo_pagina"] = m.group(0)
                info["inicio_intervalo"] = int(m.group(1))
                info["fim_intervalo"] = int(m.group(2))
                info["total_registros"] = int(m.group(3))
                break
        except Exception:
            pass

    return info


def obter_estado_tela_contratos(page):
    contratos = extrair_contratos_visiveis(page)
    info = obter_info_paginacao(page)
    return {
        "url": page.url,
        "paginacao": info,
        "total_visiveis_na_tela": len(contratos),
        "primeiro_numero": contratos[0]["numero_contrato"] if contratos else None,
        "ultimo_numero": contratos[-1]["numero_contrato"] if contratos else None,
    }


def limpar_filtros_se_existir(page):
    antes_estado = obter_estado_limpar_filtros(page)
    antes_tela = obter_estado_tela_contratos(page)

    if not antes_estado["encontrado"]:
        return {
            "encontrado": False,
            "clicado": False,
            "limpo_confirmado": False,
            "selector": None,
            "estado_antes": None,
            "estado_depois": None,
            "tela_antes": antes_tela,
            "tela_depois": antes_tela,
            "mensagem": "Limpar filtros não encontrado",
        }

    estado = antes_estado["estado"] or {}
    selector = antes_estado["selector"]

    estava_visivel = bool(estado.get("visible"))
    estava_oculto = (
        str(estado.get("display")) == "none"
        or str(estado.get("parent_display")) == "none"
        or bool(estado.get("parent_hidden_by_class"))
    )

    if not estava_visivel and estava_oculto:
        return {
            "encontrado": True,
            "clicado": False,
            "limpo_confirmado": True,
            "selector": selector,
            "estado_antes": estado,
            "estado_depois": estado,
            "tela_antes": antes_tela,
            "tela_depois": antes_tela,
            "mensagem": "Limpar filtros já estava oculto; filtros aparentemente já limpos",
        }

    # tenta clicar
    clicou = False
    erro_clique = None
    for frame in page.frames:
        if frame.url != estado.get("frame_url"):
            continue
        try:
            loc = frame.locator(selector).first
            loc.click(force=True, timeout=5000)
            clicou = True
            break
        except Exception as e:
            erro_clique = str(e)

    if not clicou:
        return {
            "encontrado": True,
            "clicado": False,
            "limpo_confirmado": False,
            "selector": selector,
            "estado_antes": estado,
            "estado_depois": obter_estado_limpar_filtros(page).get("estado"),
            "tela_antes": antes_tela,
            "tela_depois": obter_estado_tela_contratos(page),
            "mensagem": f"Limpar filtros encontrado, mas erro ao clicar: {erro_clique or 'sem detalhe'}",
        }

    # espera evidência de mudança
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    mudou = False
    for _ in range(12):
        page.wait_for_timeout(500)
        depois_estado = obter_estado_limpar_filtros(page)
        depois_tela = obter_estado_tela_contratos(page)
        est2 = depois_estado.get("estado") or {}
        ficou_oculto = (
            str(est2.get("display")) == "none"
            or str(est2.get("parent_display")) == "none"
            or bool(est2.get("parent_hidden_by_class"))
        )
        if ficou_oculto:
            mudou = True
            break
        if (
            antes_tela["paginacao"] != depois_tela["paginacao"]
            or antes_tela["primeiro_numero"] != depois_tela["primeiro_numero"]
            or antes_tela["ultimo_numero"] != depois_tela["ultimo_numero"]
        ):
            mudou = True
            break
    else:
        depois_estado = obter_estado_limpar_filtros(page)
        depois_tela = obter_estado_tela_contratos(page)

    estado_depois = depois_estado.get("estado")
    return {
        "encontrado": True,
        "clicado": True,
        "limpo_confirmado": mudou,
        "selector": selector,
        "estado_antes": estado,
        "estado_depois": estado_depois,
        "tela_antes": antes_tela,
        "tela_depois": depois_tela,
        "mensagem": (
            "Limpar filtros encontrado e clicado com evidência de atualização"
            if mudou
            else "Limpar filtros clicado, mas sem evidência forte de atualização"
        ),
    }


def ajustar_linhas_por_pagina(page, valor="120"):
    valor = str(valor)
    antes = obter_info_paginacao(page)

    # caminho principal: usar o select real
    for frame in page.frames:
        try:
            loc = frame.locator(SELECTOR_LINHAS_POR_PAGINA).first
            if loc.count() == 0:
                continue
            if not loc.is_visible():
                continue

            opcoes = []
            try:
                opcoes = loc.locator("option").evaluate_all(
                    "(opts) => opts.map(o => ({value: o.value, text: (o.innerText || o.textContent || '').trim()}))"
                )
            except Exception:
                pass

            possui = any(
                (str(o.get("value", "")).strip() == valor or str(o.get("text", "")).strip() == valor)
                for o in opcoes
            )

            if possui:
                try:
                    loc.select_option(value=valor, timeout=5000)
                except Exception:
                    loc.select_option(label=valor, timeout=5000)

                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                # espera o texto de paginação mudar
                confirmou = False
                depois = None
                for _ in range(12):
                    page.wait_for_timeout(500)
                    depois = obter_info_paginacao(page)
                    if (
                        str(depois.get("linhas_por_pagina")) == valor
                        or (
                            antes.get("intervalo_pagina") != depois.get("intervalo_pagina")
                            and depois.get("intervalo_pagina") is not None
                        )
                    ):
                        confirmou = True
                        break

                return {
                    "alterado": confirmou,
                    "valor": valor if confirmou else depois.get("linhas_por_pagina") if depois else None,
                    "mensagem": (
                        f"Linhas por página ajustado para {valor}"
                        if confirmou
                        else "Select encontrado, mas não houve confirmação do ajuste"
                    ),
                    "modo": "select_real",
                    "antes": antes,
                    "depois": depois,
                }
        except Exception:
            pass

    # fallback: JavaScript genérico
    script = """
    (valor) => {
        const textoAlvo = String(valor).trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const sel = document.querySelector('select#vCOMBOLINHASGRID, select[id*="LINHASGRID"]');
        if (sel && isVisible(sel)) {
            const options = Array.from(sel.options || []);
            const opt = options.find(o => normalizar(o.value) === textoAlvo || normalizar(o.text) === textoAlvo);
            if (opt) {
                sel.value = opt.value;
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return { alterado: true, modo: 'select_js' };
            }
        }
        return { alterado: false, modo: null };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script, valor)
            if res and res.get("alterado"):
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                depois = obter_info_paginacao(page)
                confirmou = str(depois.get("linhas_por_pagina")) == valor
                return {
                    "alterado": confirmou,
                    "valor": depois.get("linhas_por_pagina"),
                    "mensagem": (
                        f"Linhas por página ajustado para {valor}"
                        if confirmou
                        else "Fallback executado, mas sem confirmação do ajuste"
                    ),
                    "modo": res.get("modo"),
                    "antes": antes,
                    "depois": depois,
                }
        except Exception:
            pass

    return {
        "alterado": False,
        "valor": antes.get("linhas_por_pagina"),
        "mensagem": "Não foi possível ajustar linhas por página",
        "modo": None,
        "antes": antes,
        "depois": antes,
    }


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

        const anchors = Array.from(document.querySelectorAll('a[href]'))
            .filter(a => {
                if (!isVisible(a)) return false;
                const href = (a.getAttribute('href') || '').trim();
                if (!href) return false;

                const hrefLower = href.toLowerCase();
                const isContratoDetalhe =
                    hrefLower.includes('wbpvencontrato?') ||
                    hrefLower.endsWith('/wbpvencontrato') ||
                    hrefLower.includes('/wbpvencontrato?') ||
                    hrefLower.startswith('wbpvencontrato?');

                const isLista = hrefLower.includes('wbpvencontratos');
                return isContratoDetalhe && !isLista;
            });

        const resultado = [];

        for (const a of anchors) {
            const numeroContrato = normalizar(a.innerText || a.textContent || '');
            const href = a.getAttribute('href') || '';

            if (!numeroContrato) continue;
            if (!/^\d+$/.test(numeroContrato)) continue;

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

            contrato = {
                "numero_contrato": numero,
                "url_contrato": urljoin(frame.url, href) if href else None,
                "projeto": _melhor_candidato(grupos_campos[0], "projeto", numero),
                "cliente": _melhor_candidato(grupos_campos[1], "cliente", numero),
                "consultor": _melhor_candidato(grupos_campos[2], "consultor", numero),
                "executor": _melhor_candidato(grupos_campos[3], "executor", numero),
                "valor_venda": _melhor_candidato(grupos_campos[4], "valor_venda", numero),
                "situacao": _melhor_candidato(grupos_campos[5], "situacao", numero),
                "assinatura": _melhor_candidato(grupos_campos[6], "assinatura", numero),
                "previsao_entrega": _melhor_candidato(grupos_campos[7], "previsao_entrega", numero),
                "row_text": _limpar_texto(row.get("row_text")),
                "debug_grupos": grupos_limpos,
                "debug_grupos_campos": grupos_campos,
                "debug_row_tag": row.get("row_tag"),
                "debug_row_id": row.get("row_id"),
            }

            contratos.append(contrato)

    contratos.sort(key=lambda c: int(c["numero_contrato"]) if str(c.get("numero_contrato", "")).isdigit() else 999999999)
    return contratos


def clicar_proxima_pagina(page):
    script = """
    () => {
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const candidatos = Array.from(document.querySelectorAll('img, a, button, span, div'));

        for (const el of candidatos) {
            const src = (el.getAttribute && (el.getAttribute('src') || '')) || '';
            const title = (el.getAttribute && (el.getAttribute('title') || '')) || '';
            const txt = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            const id = (el.id || '');
            const cls = (el.className || '').toString();

            const bate =
                src.includes('ImgGridProximo') ||
                title.toLowerCase().includes('próximo') ||
                title.toLowerCase().includes('proximo') ||
                txt.toLowerCase() === '>' ||
                id.toUpperCase().includes('PROXIMO') ||
                cls.toUpperCase().includes('PROXIMO');

            if (!bate || !isVisible(el)) continue;
            if (src.includes('Disabled')) continue;

            const alvo = el.closest('a, button, span, div') || el;
            try {
                alvo.click();
                return {
                    clicado: true,
                    src,
                    title,
                    text: txt,
                    id,
                    cls
                };
            } catch (e) {}
        }

        return { clicado: false };
    }
    """

    antes = obter_estado_tela_contratos(page)

    for frame in page.frames:
        try:
            res = frame.evaluate(script)
            if res and res.get("clicado"):
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                depois = None
                mudou = False
                for _ in range(12):
                    page.wait_for_timeout(500)
                    depois = obter_estado_tela_contratos(page)
                    if (
                        antes["paginacao"] != depois["paginacao"]
                        or antes["primeiro_numero"] != depois["primeiro_numero"]
                        or antes["ultimo_numero"] != depois["ultimo_numero"]
                    ):
                        mudou = True
                        break

                return {
                    "clicado": True,
                    "mudou": mudou,
                    "antes": antes,
                    "depois": depois,
                    "debug": res,
                }
        except Exception:
            pass

    return {
        "clicado": False,
        "mudou": False,
        "antes": antes,
        "depois": antes,
        "debug": None,
    }


def coletar_contratos_com_paginacao(page, max_paginas=30):
    todos = []
    vistos = set()
    paginas_lidas = []
    paginacao_historico = []
    mensagens = []

    for pagina_idx in range(1, max_paginas + 1):
        info = obter_info_paginacao(page)
        paginacao_historico.append({
            "pagina_loop": pagina_idx,
            "paginacao": info,
        })

        visiveis = extrair_contratos_visiveis(page)
        paginas_lidas.append({
            "pagina_loop": pagina_idx,
            "paginacao": info,
            "quantidade_lida": len(visiveis),
            "primeiro_numero": visiveis[0]["numero_contrato"] if visiveis else None,
            "ultimo_numero": visiveis[-1]["numero_contrato"] if visiveis else None,
        })

        novos_nesta_pagina = 0
        for c in visiveis:
            chave = f"{c.get('numero_contrato')}|{c.get('url_contrato')}"
            if chave in vistos:
                continue
            vistos.add(chave)
            todos.append(c)
            novos_nesta_pagina += 1

        total_registros = info.get("total_registros")
        fim_intervalo = info.get("fim_intervalo")

        if total_registros and len(todos) >= total_registros:
            mensagens.append("Coleta encerrada porque a quantidade acumulada atingiu o total informado na paginação.")
            break

        if total_registros and fim_intervalo and fim_intervalo >= total_registros:
            mensagens.append("Coleta encerrada porque a paginação indica que já estamos na última página.")
            break

        proxima = clicar_proxima_pagina(page)
        if not proxima["clicado"]:
            mensagens.append("Coleta encerrada porque não foi encontrado botão habilitado de próxima página.")
            break
        if not proxima["mudou"]:
            mensagens.append("Coleta encerrada porque o clique na próxima página não alterou a grade.")
            break

        # proteção contra loop infinito
        if novos_nesta_pagina == 0 and pagina_idx > 1:
            mensagens.append("Coleta encerrada por proteção: página sem novos contratos visíveis.")
            break

    todos.sort(key=lambda c: int(c["numero_contrato"]) if str(c.get("numero_contrato", "")).isdigit() else 999999999)
    return {
        "contratos": todos,
        "paginas_lidas": paginas_lidas,
        "paginacao_historico": paginacao_historico,
        "mensagens": mensagens,
    }


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
        "limpar_filtros_mensagem": "",
        "linhas_por_pagina_ajustado": False,
        "linhas_por_pagina_valor": None,
        "linhas_por_pagina_mensagem": "",
        "paginacao": {},
        "paginas_lidas": [],
        "paginacao_historico": [],
        "mensagens_paginacao": [],
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
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
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
            resultado["limpar_filtros_confirmado"] = acao_limpar["limpo_confirmado"]
            resultado["limpar_filtros_mensagem"] = acao_limpar["mensagem"]

            ajuste_pagina = ajustar_linhas_por_pagina(page, "120")
            resultado["linhas_por_pagina_ajustado"] = ajuste_pagina["alterado"]
            resultado["linhas_por_pagina_valor"] = ajuste_pagina["valor"]
            resultado["linhas_por_pagina_mensagem"] = ajuste_pagina["mensagem"]

            coleta = coletar_contratos_com_paginacao(page, max_paginas=30)
            resultado["contratos"] = coleta["contratos"]
            resultado["paginas_lidas"] = coleta["paginas_lidas"]
            resultado["paginacao_historico"] = coleta["paginacao_historico"]
            resultado["mensagens_paginacao"] = coleta["mensagens"]

            resultado["paginacao"] = obter_info_paginacao(page)
            resultado["total_contratos_visiveis"] = len(resultado["contratos"])
            resultado["url_final"] = page.url

            if resultado["tela_contratos_aberta"]:
                resultado["success"] = True
                resultado["mensagem"] = (
                    f"Lista de contratos lida com sucesso. "
                    f"Contratos coletados: {resultado['total_contratos_visiveis']}"
                )
            else:
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
