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


def find_in_any_frame(page, selector: str, timeout_ms: int = 3000):
    for frame in page.frames:
        try:
            loc = frame.locator(selector).first
            loc.wait_for(state="attached", timeout=timeout_ms)
            return frame, loc
        except Exception:
            pass
    return None, None


def set_value(frame, selector, value):
    frame.eval_on_selector(
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
    if not FOCCO_USERNAME or not FOCCO_PASSWORD:
        print(json.dumps({
            "success": False,
            "error": "FOCCO_USERNAME ou FOCCO_PASSWORD não configurados"
        }, ensure_ascii=False))
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 900})
        page = context.new_page()

        resultado = {
            "success": False,
            "url_inicial": FOCCO_URL,
            "url_final": None,
            "frames": [],
            "mensagem": ""
        }

        try:
            page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(5000)

            resultado["frames"] = [f.url for f in page.frames]

            usuario_selector = "#vIPN_USU_LOGIN"
            senha_selector = "#vIPN_USU_SENHA"
            entrar_selector = "#BTNLOGIN"

            frame_user, _ = find_in_any_frame(page, usuario_selector, 5000)
            frame_pass, _ = find_in_any_frame(page, senha_selector, 5000)
            frame_btn, _ = find_in_any_frame(page, entrar_selector, 5000)

            if not frame_user:
                raise Exception("Campo usuário não encontrado em nenhum frame")
            if not frame_pass:
                raise Exception("Campo senha não encontrado em nenhum frame")
            if not frame_btn:
                raise Exception("Botão entrar não encontrado em nenhum frame")

            set_value(frame_user, usuario_selector, FOCCO_USERNAME)
            set_value(frame_pass, senha_selector, FOCCO_PASSWORD)

            frame_btn.locator(entrar_selector).click(force=True)

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