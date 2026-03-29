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


def set_input_value(page, selector, value):
    page.eval_on_selector(
        selector,
        """
        (el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value
    )


def main():
    if not FOCCO_USERNAME or not FOCCO_PASSWORD:
        print(json.dumps({
            "success": False,
            "error": "FOCCO_USERNAME ou FOCCO_PASSWORD não configurados"
        }, ensure_ascii=False))
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        resultado = {
            "success": False,
            "url_inicial": FOCCO_URL,
            "url_final": None,
            "storage_file": str(STORAGE_FILE),
            "mensagem": ""
        }

        try:
            page.goto(FOCCO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            usuario_selector = "#vIPN_USU_LOGIN"
            senha_selector = "#vIPN_USU_SENHA"
            entrar_selector = "#BTNLOGIN"

            page.locator(usuario_selector).wait_for(state="attached", timeout=20000)
            page.locator(senha_selector).wait_for(state="attached", timeout=20000)
            page.locator(entrar_selector).wait_for(state="attached", timeout=20000)

            set_input_value(page, usuario_selector, FOCCO_USERNAME)
            set_input_value(page, senha_selector, FOCCO_PASSWORD)

            page.wait_for_timeout(1000)
            page.locator(entrar_selector).click(force=True)

            page.wait_for_timeout(8000)
            resultado["url_final"] = page.url

            context.storage_state(path=str(STORAGE_FILE))

            resultado["success"] = True
            resultado["mensagem"] = "Login executado e sessão salva"

        except Exception as e:
            resultado["url_final"] = page.url if page else None
            resultado["mensagem"] = f"Erro no login: {str(e)}"

        finally:
            browser.close()

        print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()