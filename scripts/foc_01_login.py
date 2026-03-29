import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

SESSION_DIR = Path("/app/scripts/session")
SESSION_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_FILE = SESSION_DIR / "focco_storage.json"

LOGIN_URL_PART = "/criare/servlet/hipnlojas3"
DASHBOARD_URL_PART = "/criare/servlet/wbpnucadashboard"


def is_logged_in(page):
    url = page.url or ""
    if DASHBOARD_URL_PART in url:
        return True

    try:
        if page.locator("#vIPN_USU_LOGIN").count() > 0:
            return False
    except Exception:
        pass

    return DASHBOARD_URL_PART in url


def do_login(page):
    usuario_selector = "#vIPN_USU_LOGIN"
    senha_selector = "#vIPN_USU_SENHA"
    entrar_selector = "#BTNLOGIN"

    page.locator(usuario_selector).wait_for(state="attached", timeout=20000)
    page.locator(senha_selector).wait_for(state="attached", timeout=20000)
    page.locator(entrar_selector).wait_for(state="attached", timeout=20000)

    page.eval_on_selector(
        usuario_selector,
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """,
        FOCCO_USERNAME
    )

    page.eval_on_selector(
        senha_selector,
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """,
        FOCCO_PASSWORD
    )

    page.wait_for_timeout(1000)
    page.locator(entrar_selector).click(force=True)
    page.wait_for_timeout(8000)


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "storage_file": str(STORAGE_FILE),
        "session_file_exists": STORAGE_FILE.exists(),
        "session_reused": False,
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
            # 1) tentar reaproveitar sessão existente
            if STORAGE_FILE.exists():
                context = browser.new_context(
                    storage_state=str(STORAGE_FILE),
                    viewport={"width": 1600, "height": 900}
                )
                page = context.new_page()

                try:
                    page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
                    page.wait_for_timeout(5000)

                    if is_logged_in(page):
                        resultado["success"] = True
                        resultado["session_reused"] = True
                        resultado["login_executed"] = False
                        resultado["url_final"] = page.url
                        resultado["mensagem"] = "Sessão existente reutilizada com sucesso"

                        context.storage_state(path=str(STORAGE_FILE))
                        print(json.dumps(resultado, ensure_ascii=False))
                        return

                except Exception:
                    pass
                finally:
                    context.close()

            # 2) se não der para reutilizar, faz login novo
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            page = context.new_page()

            page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(5000)

            do_login(page)

            resultado["url_final"] = page.url
            resultado["login_executed"] = True

            if is_logged_in(page):
                context.storage_state(path=str(STORAGE_FILE))
                resultado["success"] = True
                resultado["session_reused"] = False
                resultado["mensagem"] = "Login executado e sessão salva"
            else:
                resultado["success"] = False
                resultado["mensagem"] = "Login executado, mas dashboard não foi confirmado"

            context.close()

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro no login/sessão: {str(e)}"

        finally:
            browser.close()

    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()