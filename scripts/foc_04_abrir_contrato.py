import json
import os
import sys
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucnovodashboard",
]

CONTRATOS_LISTA_URL_PART = "/criare/wbpvencontratos"
CONTRATO_DETALHE_URL_PART = "/criare/wbpvencontrato?"


def is_dashboard(page):
    url = page.url or ""
    return any(part in url for part in DASHBOARD_URL_PARTS)


def normalizar(valor):
    if valor is None:
        return ""
    return " ".join(str(valor).split()).strip()


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


def garantir_login(page, resultado):
    page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    if is_dashboard(page):
        resultado["already_logged_in"] = True
        return True

    if has_login_form(page):
        do_login(page)
        page.wait_for_timeout(8000)
        resultado["login_executed"] = True
        return is_dashboard(page)

    return False


def coletar_textos_visiveis(page):
    textos = []

    for frame in page.frames:
        try:
            body = frame.locator("body").inner_text(timeout=2000)
            body = normalizar(body)
            if body:
                textos.append(body)
        except Exception:
            pass

    return textos


def existe_texto(page, alvo: str):
    alvo_norm = normalizar(alvo).lower()
    if not alvo_norm:
        return False

    for texto in coletar_textos_visiveis(page):
        if alvo_norm in texto.lower():
            return True
    return False


def confirmar_detalhe_contrato(page, numero_contrato=None):
    url_atual = (page.url or "").lower()

    if CONTRATOS_LISTA_URL_PART in url_atual:
        return {
            "ok": False,
            "motivo": "abriu_lista_em_vez_de_detalhe",
            "evidencias": ["URL da lista de contratos detectada"],
        }

    if CONTRATO_DETALHE_URL_PART not in url_atual:
        # ainda pode ser uma variante da tela, então tentamos confirmar por evidências visuais
        pass

    evidencias = []

    # evidência 1: URL de detalhe
    if CONTRATO_DETALHE_URL_PART in url_atual:
        evidencias.append("URL de detalhe do contrato detectada")

    # evidência 2: seção Ambientes
    if existe_texto(page, "Ambientes"):
        evidencias.append("Texto 'Ambientes' encontrado")

    # evidência 3: botão / ação de imprimir contrato
    if existe_texto(page, "Imprimir Contrato"):
        evidencias.append("Texto 'Imprimir Contrato' encontrado")

    # evidência 4: número do contrato visível
    if numero_contrato and existe_texto(page, str(numero_contrato)):
        evidencias.append(f"Número do contrato {numero_contrato} encontrado na tela")

    ok = len(evidencias) >= 2 or (
        CONTRATO_DETALHE_URL_PART in url_atual and len(evidencias) >= 1
    )

    return {
        "ok": ok,
        "motivo": "detalhe_confirmado" if ok else "evidencias_insuficientes",
        "evidencias": evidencias,
    }


def abrir_contrato(page, url_contrato, numero_contrato, resultado):
    page.goto(url_contrato, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    # se caiu no login, tenta autenticar e abrir de novo
    if has_login_form(page):
        resultado["relogin_durante_abertura"] = True
        do_login(page)
        page.wait_for_timeout(8000)
        page.goto(url_contrato, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)

    confirmacao = confirmar_detalhe_contrato(page, numero_contrato)
    return confirmacao


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_contrato_recebida": None,
        "numero_contrato_recebido": None,
        "url_final": None,
        "already_logged_in": False,
        "login_executed": False,
        "relogin_durante_abertura": False,
        "contrato_aberto": False,
        "pagina_confirmada": False,
        "pagina_tipo": None,
        "evidencias_confirmacao": [],
        "mensagem": "",
    }

    if not FOCCO_USERNAME or not FOCCO_PASSWORD:
        print(json.dumps({
            "success": False,
            "error": "FOCCO_USERNAME ou FOCCO_PASSWORD não configurados"
        }, ensure_ascii=False))
        raise SystemExit(1)

    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "URL do contrato não informada"
        }, ensure_ascii=False))
        raise SystemExit(1)

    url_contrato = normalizar(sys.argv[1])
    numero_contrato = normalizar(sys.argv[2]) if len(sys.argv) > 2 else ""

    resultado["url_contrato_recebida"] = url_contrato
    resultado["numero_contrato_recebido"] = numero_contrato

    if not url_contrato:
        print(json.dumps({
            "success": False,
            "error": "URL do contrato vazia"
        }, ensure_ascii=False))
        raise SystemExit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            ok_login = garantir_login(page, resultado)

            if not ok_login:
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Não foi possível confirmar o login antes de abrir o contrato"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            confirmacao = abrir_contrato(page, url_contrato, numero_contrato, resultado)

            resultado["url_final"] = page.url
            resultado["evidencias_confirmacao"] = confirmacao.get("evidencias", [])

            if confirmacao.get("ok"):
                resultado["success"] = True
                resultado["contrato_aberto"] = True
                resultado["pagina_confirmada"] = True
                resultado["pagina_tipo"] = "detalhe_contrato"
                resultado["mensagem"] = "Contrato aberto com sucesso"
            else:
                resultado["success"] = False
                resultado["contrato_aberto"] = False
                resultado["pagina_confirmada"] = False
                resultado["pagina_tipo"] = confirmacao.get("motivo")
                resultado["mensagem"] = f"Contrato não foi confirmado: {confirmacao.get('motivo')}"

            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao abrir contrato: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()