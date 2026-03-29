import json
import os
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucnovodashboard",
]

CONTRATOS_URL = os.getenv(
    "FOCCO_CONTRATOS_URL",
    "https://web.foccolojas.com.br/criare/wbpvencontratos"
)


def is_dashboard(page):
    url = page.url or ""
    return any(part in url for part in DASHBOARD_URL_PARTS)


def is_contrato_aberto(page):
    url = page.url or ""
    return "/criare/wbpvencontrato" in url


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


def abrir_tela_contratos(page):
    page.goto(CONTRATOS_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)


def listar_links_para_debug(page, limite=20):
    links = []

    for frame in page.frames:
        try:
            anchors = frame.locator("a")
            total = anchors.count()

            for i in range(min(total, limite)):
                try:
                    a = anchors.nth(i)
                    texto = (a.inner_text(timeout=1000) or "").strip()
                    href = a.get_attribute("href")
                    if texto or href:
                        links.append({
                            "frame_url": frame.url,
                            "text": texto,
                            "href": href,
                        })
                except Exception:
                    pass
        except Exception:
            pass

    return links[:limite]


def encontrar_primeiro_contrato(page):
    seletores = [
        "a[href*='wbpvencontrato?']",
        "a[href*='wbpvencontrato']",
        "a[onclick*='wbpvencontrato']",
    ]

    for selector in seletores:
        for frame in page.frames:
            try:
                loc = frame.locator(selector).first
                if loc.count() > 0:
                    href = loc.get_attribute("href")
                    texto = ""
                    try:
                        texto = (loc.inner_text(timeout=1000) or "").strip()
                    except Exception:
                        pass
                    return frame, loc, {
                        "selector": selector,
                        "href": href,
                        "text": texto,
                        "frame_url": frame.url,
                    }
            except Exception:
                pass

    return None, None, None


def clicar_primeiro_contrato(page):
    frame, loc, info = encontrar_primeiro_contrato(page)

    if not loc:
        return {
            "success": False,
            "mensagem": "Nenhum link de contrato foi encontrado na tela de contratos",
            "contrato_info": None,
        }

    try:
        with page.expect_navigation(wait_until="networkidle", timeout=30000):
            loc.click(force=True)
    except Exception:
        loc.click(force=True)
        page.wait_for_timeout(5000)

    return {
        "success": True,
        "mensagem": "Clique no primeiro contrato executado",
        "contrato_info": info,
    }


def garantir_login(page, resultado):
    page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    resultado["frames_login"] = [f.url for f in page.frames]

    if is_dashboard(page):
        resultado["already_logged_in"] = True
        return True

    if has_login_form(page):
        do_login(page)
        page.wait_for_timeout(8000)
        resultado["login_executed"] = True
        return is_dashboard(page)

    return False


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "already_logged_in": False,
        "login_executed": False,
        "tela_contratos_aberta": False,
        "contrato_aberto": False,
        "contrato_info": None,
        "frames_login": [],
        "frames_contratos": [],
        "debug_links": [],
        "mensagem": "",
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
            context = browser.new_context(
                viewport={"width": 1600, "height": 900}
            )
            page = context.new_page()

            ok_login = garantir_login(page, resultado)

            if not ok_login:
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Não foi possível confirmar o login antes de abrir contratos"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            abrir_tela_contratos(page)
            resultado["frames_contratos"] = [f.url for f in page.frames]
            resultado["debug_links"] = listar_links_para_debug(page, limite=20)
            resultado["tela_contratos_aberta"] = "/criare/wbpvencontratos" in (page.url or "")

            clique = clicar_primeiro_contrato(page)

            if not clique["success"]:
                resultado["url_final"] = page.url
                resultado["mensagem"] = clique["mensagem"]
                resultado["contrato_info"] = clique["contrato_info"]
                print(json.dumps(resultado, ensure_ascii=False))
                return

            page.wait_for_timeout(5000)

            resultado["url_final"] = page.url
            resultado["contrato_info"] = clique["contrato_info"]

            if is_contrato_aberto(page):
                resultado["success"] = True
                resultado["contrato_aberto"] = True
                resultado["mensagem"] = "Contrato aberto com sucesso"
            else:
                resultado["success"] = False
                resultado["contrato_aberto"] = False
                resultado["mensagem"] = "Cliquei no contrato, mas a URL final não confirmou a abertura"

            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao abrir contrato: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()