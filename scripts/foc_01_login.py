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
            page.wait_for_timeout(5000)

            # pega somente inputs visíveis
            visible_inputs = []
            for inp in page.locator("input").all():
                try:
                    if inp.is_visible():
                        input_type = (inp.get_attribute("type") or "").lower()
                        visible_inputs.append((inp, input_type))
                except Exception:
                    pass

            text_like = [inp for inp, t in visible_inputs if t in ("text", "email", "")]
            password_like = [inp for inp, t in visible_inputs if t == "password"]

            if not text_like:
                raise Exception("Nenhum campo visível de usuário/email encontrado")

            if not password_like:
                raise Exception("Nenhum campo visível de senha encontrado")

            usuario = text_like[0]
            senha = password_like[0]

            usuario.fill(FOCCO_USERNAME)
            senha.fill(FOCCO_PASSWORD)

            entrou = False

            # tenta clicar no botão ENTRAR visível
            possible_buttons = [
                page.get_by_role("button", name="ENTRAR"),
                page.get_by_role("button", name="Entrar"),
                page.locator("button:has-text('ENTRAR')").first,
                page.locator("button:has-text('Entrar')").first,
                page.locator("input[type='submit']").first,
                page.locator("text=ENTRAR").first,
                page.locator("text=Entrar").first,
            ]

            for botao in possible_buttons:
                try:
                    if botao.is_visible(timeout=2000):
                        botao.click()
                        entrou = True
                        break
                except Exception:
                    pass

            if not entrou:
                page.keyboard.press("Enter")

            page.wait_for_timeout(7000)
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