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
            page.wait_for_timeout(4000)

            usuario = page.locator("#vIPN_USU_LOGIN")
            senha = page.locator("#vIPN_USU_SENHA")
            entrar = page.locator("#BTNLOGIN")

            usuario.wait_for(state="visible", timeout=15000)
            senha.wait_for(state="visible", timeout=15000)
            entrar.wait_for(state="visible", timeout=15000)

            usuario.fill(FOCCO_USERNAME)
            senha.fill(FOCCO_PASSWORD)

            entrar.click()

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