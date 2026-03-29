import json
import os
from playwright.sync_api import sync_playwright
from foc_01_login import is_dashboard, has_login_form, do_login, find_in_any_frame

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

CONTRATOS_URL = os.getenv(
    "FOCCO_CONTRATOS_URL",
    "https://web.foccolojas.com.br/criare/wbpvencontratos"
)


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


def limpar_filtros_se_existir(page):
    frame, loc = find_in_any_frame(page, "#LIMPARFILTROS", 2000)

    if not loc:
        return {
            "encontrado": False,
            "clicado": False,
            "mensagem": "Botão limpar filtros não encontrado"
        }

    try:
        visivel = loc.is_visible()
    except Exception:
        visivel = True

    if not visivel:
        return {
            "encontrado": True,
            "clicado": False,
            "mensagem": "Botão limpar filtros encontrado, mas não está visível"
        }

    try:
        loc.click(force=True)
        page.wait_for_timeout(3000)

        return {
            "encontrado": True,
            "clicado": True,
            "mensagem": "Botão limpar filtros encontrado e clicado com sucesso"
        }
    except Exception as e:
        return {
            "encontrado": True,
            "clicado": False,
            "mensagem": f"Botão limpar filtros encontrado, mas erro ao clicar: {str(e)}"
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

            resultado["limpar_filtros_encontrado"] = acao_limpar["encontrado"]
            resultado["limpar_filtros_clicado"] = acao_limpar["clicado"]
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