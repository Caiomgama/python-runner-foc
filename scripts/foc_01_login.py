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


def first_visible(page, selectors, timeout_each=3000):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_each)
            return locator, selector
        except Exception:
            pass
    return None, None


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
            "mensagem": "",
            "selector_usuario": None,
            "selector_senha": None
        }

        try:
            page.goto(FOCCO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            usuario_selectors = [
                'input[name="BTNCONHECAAGORA"]',
                'input[id="BTNCONHECAAGORA"]',
                'input[name="vUSUARIO"]',
                'input[id="vUSUARIO"]',
                'input[name="usuario"]',
                'input[id="usuario"]',
                'input[name="login"]',
                'input[id="login"]',
                'input[type="text"]:not([type="hidden"])',
            ]

            senha_selectors = [
                'input[name="BTNCONHECAAG"]',
                'input[id="BTNCONHECAAG"]',
                'input[name="vSENHA"]',
                'input[id="vSENHA"]',
                'input[name="senha"]',
                'input[id="senha"]',
                'input[type="password"]',
            ]

            usuario, sel_usuario = first_visible(page, usuario_selectors)
            senha, sel_senha = first_visible(page, senha_selectors)

            resultado["selector_usuario"] = sel_usuario
            resultado["selector_senha"] = sel_senha

            if not usuario:
                raise Exception("Campo de usuário visível não encontrado")
            if not senha:
                raise Exception("Campo de senha visível não encontrado")

            usuario.fill(FOCCO_USERNAME)
            senha.fill(FOCCO_PASSWORD)

            botoes = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Entrar")',
                'button:has-text("Login")',
                'text=Entrar',
                'text=Login',
            ]

            clicou = False
            for seletor in botoes:
                try:
                    botao = page.locator(seletor).first
                    botao.wait_for(state="visible", timeout=1500)
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
            resultado["url_final"] = page.url
            resultado["mensagem"] = f"Erro no login: {str(e)}"

        finally:
            browser.close()

        print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()