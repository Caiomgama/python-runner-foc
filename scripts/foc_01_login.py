import json
import os
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucnovodashboard",
]


def is_dashboard(page):
    url = page.url or ""
    return any(part in url for part in DASHBOARD_URL_PARTS)


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
        value,
    )


def has_login_form(page):
    frame_user, _ = find_in_any_frame(page, "#vIPN_USU_LOGIN", 2000)
    frame_pass, _ = find_in_any_frame(page, "#vIPN_USU_SENHA", 2000)
    frame_btn, _ = find_in_any_frame(page, "#BTNLOGIN", 2000)

    return (
        frame_user is not None
        and frame_pass is not None
        and frame_btn is not None
    )


def do_login(page):
    frame_user, _ = find_in_any_frame(page, "#vIPN_USU_LOGIN", 5000)
    frame_pass, _ = find_in_any_frame(page, "#vIPN_USU_SENHA", 5000)
    frame_btn, _ = find_in_any_frame(page, "#BTNLOGIN", 5000)

    if not frame_user:
        raise Exception("Campo usuário não encontrado em nenhum frame")

    if not frame_pass:
        raise Exception("Campo senha não encontrado em nenhum frame")

    if not frame_btn:
        raise Exception("Botão entrar não encontrado em nenhum frame")

    set_value(frame_user, "#vIPN_USU_LOGIN", FOCCO_USERNAME)
    set_value(frame_pass, "#vIPN_USU_SENHA", FOCCO_PASSWORD)

    frame_btn.locator("#BTNLOGIN").click(force=True)


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "already_logged_in": False,
        "login_executed": False,
        "frames": [],
        "mensagem": "",
    }

    if not FOCCO_USERNAME or not FOCCO_PASSWORD:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": "FOCCO_USERNAME ou FOCCO_PASSWORD não configurados",
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(
                viewport={"width": 1600, "height": 900}
            )
            page = context.new_page()

            page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(5000)

            resultado["frames"] = [f.url for f in page.frames]

            if is_dashboard(page):
                resultado["success"] = True
                resultado["already_logged_in"] = True
                resultado["login_executed"] = False
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Sessão já estava autenticada"

                print(json.dumps(resultado, ensure_ascii=False))
                return

            if has_login_form(page):
                do_login(page)
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

            resultado["url_final"] = page.url
            resultado["mensagem"] = (
                "Página abriu, mas não estava nem no dashboard nem no formulário de login"
            )

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro no login: {str(e)}"

        finally:
            browser.close()

    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()