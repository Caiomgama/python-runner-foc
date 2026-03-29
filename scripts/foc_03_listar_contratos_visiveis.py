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


def encontrar_link_limpar_filtros(page):
    seletores = [
        "#DIVLIMPAFILTRO a",
        "#DIVLIMPARFILTRO a",
        "#LIMPARFILTROS a",
        "a:has-text('Limpar Filtros')",
        "a:has-text('LIMPAR FILTROS')",
    ]

    for frame in page.frames:
        for selector in seletores:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0 and loc.is_visible():
                    return frame, loc, selector
            except Exception:
                pass

    return None, None, None


def limpar_filtros_se_existir(page):
    frame, loc, selector = encontrar_link_limpar_filtros(page)

    if not loc:
        return {
            "encontrado": False,
            "clicado": False,
            "selector": None,
            "mensagem": "Limpar filtros não encontrado"
        }

    try:
        loc.click(force=True)
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            page.wait_for_timeout(5000)

        return {
            "encontrado": True,
            "clicado": True,
            "selector": selector,
            "mensagem": "Limpar filtros encontrado e clicado"
        }
    except Exception as e:
        return {
            "encontrado": True,
            "clicado": False,
            "selector": selector,
            "mensagem": f"Limpar filtros encontrado, mas erro ao clicar: {str(e)}"
        }


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


def extrair_contratos_visiveis(page):
    contratos = []
    vistos = set()

    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const anchors = Array.from(document.querySelectorAll('a[href*="wbpvencontrato"]'));

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

            const cells = Array.from(row.querySelectorAll('td'))
                .map(td => normalizar(td.innerText || td.textContent || ''))
                .filter(txt => txt);

            resultado.push({
                numero_contrato: numeroContrato,
                href,
                cells,
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
            cells = row.get("cells") or []

            if not numero:
                continue

            chave = f"{numero}|{href}"
            if chave in vistos:
                continue

            vistos.add(chave)

            contrato = {
                "numero_contrato": numero,
                "url_contrato": urljoin(frame.url, href) if href else None,
                "projeto": _limpar_texto(cells[1]) if len(cells) > 1 else None,
                "cliente": _limpar_texto(cells[2]) if len(cells) > 2 else None,
                "consultor": _limpar_texto(cells[3]) if len(cells) > 3 else None,
                "executor": _limpar_texto(cells[4]) if len(cells) > 4 else None,
                "valor_venda": _limpar_texto(cells[5]) if len(cells) > 5 else None,
                "situacao": _limpar_texto(cells[6]) if len(cells) > 6 else None,
                "assinatura": _limpar_texto(cells[7]) if len(cells) > 7 else None,
                "previsao_entrega": _limpar_texto(cells[8]) if len(cells) > 8 else None,
                "row_text": _limpar_texto(row.get("row_text")),
                "debug_cells": cells,
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