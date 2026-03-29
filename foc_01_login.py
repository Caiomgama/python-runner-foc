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

            # Ajuste inicial genérico: tentar localizar campos de usuário e senha
            usuario = page.locator('input[type="text"], input[name*="user" i], input[id*="user" i], input[name*="login" i], input[id*="login" i]').first
            senha = page.locator('input[type="password"]').first

            usuario.wait_for(timeout=15000)
            senha.wait_for(timeout=15000)

            usuario.fill(FOCCO_USERNAME)
            senha.fill(FOCCO_PASSWORD)

            # tenta botão comum de login
            possiveis_botoes = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
                'text=Entrar',
                'text=Login',
            ]

            clicou = False
            for seletor in possiveis_botoes:
                try:
                    botao = page.locator(seletor).first
                    if botao.is_visible(timeout=2000):
                        botao.click()
                        clicou = True
                        break
                except Exception:
                    pass

            if not clicou:
                page.keyboard.press("Enter")

            page.wait_for_timeout(5000)

            resultado["url_final"] = page.url

            context.storage_state(path=str(STORAGE_FILE))

            resultado["success"] = True
            resultado["mensagem"] = "Login executado e sessão salva"

        except Exception as e:
            resultado["mensagem"] = f"Erro no login: {str(e)}"
            resultado["url_final"] = page.url if page else None

        finally:
            browser.close()

        print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()