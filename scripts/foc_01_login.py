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
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        resultado = {
            "success": False,
            "url_inicial": FOCCO_URL,
            "url_final": None,
            "inputs_visiveis": [],
            "botoes_visiveis": [],
            "mensagem": ""
        }

        try:
            page.goto(FOCCO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            resultado["url_final"] = page.url

            inputs = page.locator("input").all()
            for inp in inputs:
                try:
                    if inp.is_visible():
                        resultado["inputs_visiveis"].append({
                            "name": inp.get_attribute("name"),
                            "id": inp.get_attribute("id"),
                            "type": inp.get_attribute("type"),
                            "placeholder": inp.get_attribute("placeholder"),
                            "value": inp.get_attribute("value"),
                        })
                except Exception:
                    pass

            botoes = page.locator("button, input[type='submit'], a").all()
            for el in botoes[:30]:
                try:
                    if el.is_visible():
                        texto = el.inner_text().strip() if el.evaluate("e => e.innerText !== undefined") else ""
                        resultado["botoes_visiveis"].append({
                            "tag": el.evaluate("e => e.tagName"),
                            "text": texto[:100],
                            "id": el.get_attribute("id"),
                            "name": el.get_attribute("name"),
                            "type": el.get_attribute("type"),
                        })
                except Exception:
                    pass

            resultado["success"] = True
            resultado["mensagem"] = "Mapeamento da tela realizado"

        except Exception as e:
            resultado["mensagem"] = f"Erro ao mapear tela: {str(e)}"

        finally:
            browser.close()

        print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()