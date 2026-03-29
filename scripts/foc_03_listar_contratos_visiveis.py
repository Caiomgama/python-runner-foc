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

        const abrirPorTexto = () => {
            const elementos = Array.from(document.querySelectorAll('div, span, a, button'));
            for (const el of elementos) {
                const txt = normalizar(el.innerText || el.textContent || '');
                if (txt === 'Linhas por página:' && isVisible(el)) {
                    const clicaveis = [
                        el.nextElementSibling,
                        el.parentElement,
                        el.closest('div'),
                    ].filter(Boolean);

                    for (const c of clicaveis) {
                        try {
                            c.click();
                        } catch (e) {}
                    }
                    return true;
                }
            }
            return false;
        };

        const clicarOpcao = () => {
            const candidatos = Array.from(document.querySelectorAll('li, div, span, a, option'));
            for (const el of candidatos) {
                const txt = normalizar(el.innerText || el.textContent || '');
                if (txt === textoAlvo && isVisible(el)) {
                    try {
                        el.click();
                        return true;
                    } catch (e) {}
                }
            }
            return false;
        };

        const selects = Array.from(document.querySelectorAll('select')).filter(isVisible);
        for (const sel of selects) {
            const options = Array.from(sel.options || []).map(o => normalizar(o.text));
            if (options.includes(textoAlvo)) {
                sel.value = Array.from(sel.options).find(o => normalizar(o.text) === textoAlvo).value;
                sel.dispatchEvent(new Event('input', { bubbles: true }));
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                return { alterado: true, modo: 'select' };
            }
        }

        abrirPorTexto();
        const clicouOpcao = clicarOpcao();
        if (clicouOpcao) {
            return { alterado: true, modo: 'menu' };
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


def _normalizar_celulas(cells, numero_contrato):
    cells = [c.strip() for c in cells if c and c.strip()]

    if not cells:
        return cells

    if cells and cells[0] != numero_contrato and not cells[0].isdigit():
        if numero_contrato in cells[1:]:
            cells = cells[1:]

    if numero_contrato in cells:
        idx = cells.index(numero_contrato)
        cells = cells[idx:]

    return cells


def _mapear_contrato(row_data, frame_url):
    numero_contrato = (row_data.get("numero_contrato") or "").strip()
    href = row_data.get("href") or ""
    cells = _normalizar_celulas(row_data.get("cells") or [], numero_contrato)

    contrato = {
        "numero_contrato": numero_contrato,
        "url_contrato": urljoin(frame_url, href) if href else None,
        "projeto": None,
        "cliente": None,
        "consultor": None,
        "executor": None,
        "valor_venda": None,
        "situacao": None,
        "assinatura": None,
        "previsao_entrega": None,
        "row_text": row_data.get("row_text"),
    }

    if len(cells) >= 2:
        contrato["projeto"] = cells[1]
    if len(cells) >= 3:
        contrato["cliente"] = cells[2]
    if len(cells) >= 4:
        contrato["consultor"] = cells[3]
    if len(cells) >= 5:
        contrato["executor"] = cells[4]
    if len(cells) >= 6:
        contrato["valor_venda"] = cells[5]
    if len(cells) >= 7:
        contrato["situacao"] = cells[6]
    if len(cells) >= 8:
        contrato["assinatura"] = cells[7]
    if len(cells) >= 9:
        contrato["previsao_entrega"] = cells[8]

    return contrato


def extrair_contratos_visiveis(page):
    contratos = []
    vistos = set()

    script = """
    () => {
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

        const links = Array.from(document.querySelectorAll('a[href*="wbpvencontrato"]'))
            .filter(a => isVisible(a));

        return links.map((a) => {
            const numero = (a.innerText || a.textContent || '').trim();
            const href = a.getAttribute('href') || '';
            const tr = a.closest('tr');

            let cells = [];
            let rowText = '';

            if (tr) {
                cells = Array.from(tr.querySelectorAll('td, th'))
                    .map(el => (el.innerText || el.textContent || '').trim())
                    .filter(Boolean);
                rowText = (tr.innerText || tr.textContent || '').trim();
            } else {
                const parent = a.parentElement;
                rowText = parent ? (parent.innerText || parent.textContent || '').trim() : numero;
            }

            return {
                numero_contrato: numero,
                href,
                cells,
                row_text: rowText
            };
        });
    }
    """

    for frame in page.frames:
        try:
            rows = frame.evaluate(script)
        except Exception:
            continue

        for row in rows:
            numero = (row.get("numero_contrato") or "").strip()
            href = (row.get("href") or "").strip()

            if not numero:
                continue

            chave = f"{numero}|{href}"
            if chave in vistos:
                continue

            vistos.add(chave)
            contratos.append(_mapear_contrato(row, frame.url))

    if not contratos:
        for frame in page.frames:
            try:
                links = frame.locator("a[href*='wbpvencontrato']")
                total = links.count()

                for i in range(total):
                    try:
                        loc = links.nth(i)
                        numero = (loc.inner_text(timeout=1000) or "").strip()
                        href = loc.get_attribute("href") or ""

                        if not numero:
                            continue

                        chave = f"{numero}|{href}"
                        if chave in vistos:
                            continue

                        vistos.add(chave)
                        contratos.append({
                            "numero_contrato": numero,
                            "url_contrato": urljoin(frame.url, href) if href else None,
                            "projeto": None,
                            "cliente": None,
                            "consultor": None,
                            "executor": None,
                            "valor_venda": None,
                            "situacao": None,
                            "assinatura": None,
                            "previsao_entrega": None,
                            "row_text": numero,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

    def ordenar(c):
        n = c.get("numero_contrato") or ""
        return int(n) if n.isdigit() else 999999999

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
                viewport={"width": 1600, "height": 900}
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