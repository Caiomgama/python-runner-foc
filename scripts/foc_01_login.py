import json
import os
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

LOGIN_URL_PART = "/criare/servlet/hipnlojas3"
DASHBOARD_URL_PART = "/criare/servlet/wbpnucadashboard"


def is_dashboard(page):
    return DASHBOARD_URL_PART in (page.url or "")


def has_login_form(page):
    try:
        return (
            page.locator("#vIPN_USU_LOGIN").count() > 0 and
            page.locator("#vIPN_USU_SENHA").count() > 0 and
            page.locator("#BTNLOGIN").count() > 0
        )
    except Exception:
        return False


def set_input_value(page, selector, value):
    page.eval_on_selector(
        selector,
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """,
        value
    )


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "already_logged_in": False,
        "login_executed": False,
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
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            page = context.new_page()

            page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(5000)

            # Caso 1: já está logado
            if is_dashboard(page):
                resultado["success"] = True
                resultado["already_logged_in"] = True
                resultado["login_executed"] = False
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Sessão já estava autenticada"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            # Caso 2: está na tela de login
            if has_login_form(page):
                set_input_value(page, "#vIPN_USU_LOGIN", FOCCO_USERNAME)
                set_input_value(page, "#vIPN_USU_SENHA", FOCCO_PASSWORD)

                page.wait_for_timeout(1000)
                page.locator("#BTNLOGIN").click(force=True)
                page.wait_for_timeout(8000)

                resultado["url_final"] = page.url
                resultado["login_executed"] = True

                if is_dashboard(page):
                    resultado["success"] = True
                    resultado["mensagem"] = "Login executado com sucesso"
                else:
                    resultado["success"] = False
                    resultado["mensagem"] = "Login executado, mas dashboard não foi confirmado"

                print(json.dumps(resultado, ensure_ascii=False))
                return

            # Caso 3: estado inesperado
            resultado["url_final"] = page.url
            resultado["mensagem"] = "Página abriu, mas não estava nem no dashboard nem no formulário de login"

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro no login: {str(e)}"

        finally:
            browser.close()

    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()