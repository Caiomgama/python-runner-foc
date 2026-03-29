import json
import os
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


def obter_estado_tela_contratos(page):
    estado = {
        "pesquisa_valor": None,
        "qtd_linhas": 0,
        "primeiro_contrato": None,
    }

    for frame in page.frames:
        try:
            try:
                pesquisa = frame.locator("input[placeholder='Pesquisar']").first
                if pesquisa.count() > 0:
                    estado["pesquisa_valor"] = pesquisa.input_value(timeout=1000)
            except Exception:
                pass

            try:
                contratos = frame.locator("a[href*='wbpvencontrato']")
                qtd = contratos.count()

                if qtd > estado["qtd_linhas"]:
                    estado["qtd_linhas"] = qtd

                if qtd > 0 and not estado["primeiro_contrato"]:
                    try:
                        estado["primeiro_contrato"] = contratos.nth(0).inner_text(timeout=1000).strip()
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    return estado


def obter_estado_limpar_filtros(page):
    seletores = [
        "#DIVLIMPAFILTRO",
        "#DIVLIMPARFILTRO",
        "#LIMPARFILTROS",
        "[data-gx-cntrl='LIMPARFILTROS']",
    ]

    estado = {
        "existe": False,
        "visivel": False,
        "gx_invisible": False,
        "display_none": False,
        "selector_usado": None,
    }

    for selector in seletores:
        frame, loc = find_in_any_frame(page, selector, 1000)

        if not loc:
            continue

        estado["existe"] = True
        estado["selector_usado"] = selector

        try:
            estado["visivel"] = loc.is_visible()
        except Exception:
            estado["visivel"] = False

        try:
            classes = (loc.get_attribute("class") or "").lower()
        except Exception:
            classes = ""

        try:
            style = (loc.get_attribute("style") or "").replace(" ", "").lower()
        except Exception:
            style = ""

        estado["gx_invisible"] = "gx-invisible" in classes
        estado["display_none"] = "display:none" in style

        return estado

    return estado


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
                if loc.count() > 0:
                    return frame, loc, selector
            except Exception:
                pass

    return None, None, None


def limpar_filtros_se_existir(page):
    antes_botao = obter_estado_limpar_filtros(page)
    antes_tela = obter_estado_tela_contratos(page)

    frame, loc, selector = encontrar_link_limpar_filtros(page)

    if not loc:
        return {
            "encontrado_antes": antes_botao["existe"],
            "clicado": False,
            "sumiu_depois": False,
            "houve_mudanca_na_tela": False,
            "estado_antes": antes_tela,
            "estado_depois": antes_tela,
            "estado_botao_antes": antes_botao,
            "estado_botao_depois": antes_botao,
            "mensagem": "Link limpar filtros não encontrado para clique"
        }

    try:
        loc.click(force=True)
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            page.wait_for_timeout(5000)
    except Exception as e:
        return {
            "encontrado_antes": antes_botao["existe"],
            "clicado": False,
            "sumiu_depois": False,
            "houve_mudanca_na_tela": False,
            "estado_antes": antes_tela,
            "estado_depois": antes_tela,
            "estado_botao_antes": antes_botao,
            "estado_botao_depois": antes_botao,
            "mensagem": f"Erro ao clicar em limpar filtros: {str(e)}"
        }

    depois_botao = obter_estado_limpar_filtros(page)
    depois_tela = obter_estado_tela_contratos(page)

    sumiu_depois = (
        (not depois_botao["visivel"])
        or depois_botao["gx_invisible"]
        or depois_botao["display_none"]
        or (not depois_botao["existe"])
    )

    houve_mudanca_na_tela = antes_tela != depois_tela

    if sumiu_depois and houve_mudanca_na_tela:
        mensagem = "Limpar filtros funcionou: botão ficou oculto e a tela mudou"
    elif sumiu_depois:
        mensagem = "Limpar filtros provavelmente funcionou: botão ficou oculto"
    elif houve_mudanca_na_tela:
        mensagem = "Limpar filtros provavelmente funcionou: a tela mudou após o clique"
    else:
        mensagem = "Clique executado, mas sem evidência forte de limpeza"

    return {
        "encontrado_antes": antes_botao["existe"],
        "clicado": True,
        "sumiu_depois": sumiu_depois,
        "houve_mudanca_na_tela": houve_mudanca_na_tela,
        "estado_antes": antes_tela,
        "estado_depois": depois_tela,
        "estado_botao_antes": antes_botao,
        "estado_botao_depois": depois_botao,
        "mensagem": mensagem
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
        "limpar_filtros_sumiu_depois": False,
        "houve_mudanca_na_tela": False,
        "estado_antes": {},
        "estado_depois": {},
        "estado_botao_antes": {},
        "estado_botao_depois": {},
        "mensagem": ""
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

            resultado["limpar_filtros_encontrado"] = acao_limpar["encontrado_antes"]
            resultado["limpar_filtros_clicado"] = acao_limpar["clicado"]
            resultado["limpar_filtros_sumiu_depois"] = acao_limpar["sumiu_depois"]
            resultado["houve_mudanca_na_tela"] = acao_limpar["houve_mudanca_na_tela"]
            resultado["estado_antes"] = acao_limpar["estado_antes"]
            resultado["estado_depois"] = acao_limpar["estado_depois"]
            resultado["estado_botao_antes"] = acao_limpar["estado_botao_antes"]
            resultado["estado_botao_depois"] = acao_limpar["estado_botao_depois"]
            resultado["url_final"] = page.url

            if resultado["tela_contratos_aberta"]:
                resultado["success"] = True
                resultado["mensagem"] = acao_limpar["mensagem"]
            else:
                resultado["success"] = False
                resultado["mensagem"] = "Tela de contratos não foi confirmada"

            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro no teste de limpar filtros: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()