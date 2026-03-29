import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")

SESSION_DIR = Path("/app/scripts/session")
SESSION_DIR.mkdir(parents=True, exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        resultado = {
            "success": False,
            "url_inicial": FOCCO_URL,
            "url_final": None,
            "titulo": None,
            "inputs_visiveis": [],
            "textareas_visiveis": [],
            "botoes_visiveis": [],
            "iframes": [],
            "mensagem": ""
        }

        try:
            page.goto(FOCCO_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            resultado["url_final"] = page.url
            resultado["titulo"] = page.title()

            # inputs
            for i, inp in enumerate(page.locator("input").all()):
                try:
                    if inp.is_visible():
                        resultado["inputs_visiveis"].append({
                            "index": i,
                            "name": inp.get_attribute("name"),
                            "id": inp.get_attribute("id"),
                            "type": inp.get_attribute("type"),
                            "placeholder": inp.get_attribute("placeholder"),
                            "value": inp.get_attribute("value"),
                            "outer_html": inp.evaluate("e => e.outerHTML")
                        })
                except Exception:
                    pass

            # textareas
            for i, ta in enumerate(page.locator("textarea").all()):
                try:
                    if ta.is_visible():
                        resultado["textareas_visiveis"].append({
                            "index": i,
                            "name": ta.get_attribute("name"),
                            "id": ta.get_attribute("id"),
                            "placeholder": ta.get_attribute("placeholder"),
                            "outer_html": ta.evaluate("e => e.outerHTML")
                        })
                except Exception:
                    pass

            # botões/links
            for i, el in enumerate(page.locator("button, input[type='submit'], a").all()[:50]):
                try:
                    if el.is_visible():
                        texto = ""
                        try:
                            texto = el.inner_text().strip()
                        except Exception:
                            pass

                        resultado["botoes_visiveis"].append({
                            "index": i,
                            "tag": el.evaluate("e => e.tagName"),
                            "text": texto[:200],
                            "id": el.get_attribute("id"),
                            "name": el.get_attribute("name"),
                            "type": el.get_attribute("type"),
                            "outer_html": el.evaluate("e => e.outerHTML")
                        })
                except Exception:
                    pass

            # iframes
            for i, fr in enumerate(page.locator("iframe").all()):
                try:
                    resultado["iframes"].append({
                        "index": i,
                        "name": fr.get_attribute("name"),
                        "id": fr.get_attribute("id"),
                        "src": fr.get_attribute("src")
                    })
                except Exception:
                    pass

            resultado["success"] = True
            resultado["mensagem"] = "Mapeamento detalhado realizado"

        except Exception as e:
            resultado["mensagem"] = f"Erro ao mapear tela: {str(e)}"

        finally:
            browser.close()

        print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()