import json
import os
from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucadashboard",
    "/criare/servlet/wbpnucnovdashboard",
    "/criare/servlet/wbpnucnovodashboard",
]

CONTRATOS_URL_PARTS = [
    "/criare/wbpvencontratos",
    "/criare/servlet/wbpvencontratos",
]


def is_dashboard(page):
    url = page.url or ""
    return any(part in url for part in DASHBOARD_URL_PARTS)


def is_contratos_page(page):
    url = page.url or ""
    return any(part in url for part in CONTRATOS_URL_PARTS)


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


def has_login_form(page):
    frame_user, _ = find_in_any_frame(page, "#vIPN_USU_LOGIN", 2000)
    frame_pass, _ = find_in_any_frame(page, "#vIPN_USU_SENHA", 2000)
    frame_btn, _ = find_in_any_frame(page, "#BTNLOGIN", 2000)
    return frame_user is not None and frame_pass is not None and frame_btn is not None


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


def garantir_login(page):
    page.goto(FOCCO_URL, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    if is_dashboard(page):
        return "ja_logado"

    if has_login_form(page):
        do_login(page)
        page.wait_for_timeout(8000)

        if is_dashboard(page):
            return "login_executado"

        raise Exception(f"Login executado, mas dashboard não foi confirmado. URL final: {page.url}")

    raise Exception(f"Página abriu, mas não estava nem no dashboard nem no formulário de login. URL final: {page.url}")


def abrir_contratos(page):
    seletores = [
        'a[href="wbpvencontratos"]',
        'a[href*="wbpvencontratos"]',
        'a:has-text("Contratos")',
        'text=Contratos',
    ]

    clicou = False

    for seletor in seletores:
        try:
            loc = page.locator(seletor).first
            loc.wait_for(state="attached", timeout=4000)
            loc.click(force=True)
            clicou = True
            break
        except Exception:
            pass

    if not clicou:
        raise Exception("Não foi possível clicar no menu Contratos")

    page.wait_for_timeout(6000)

    if not is_contratos_page(page):
        page.goto("https://web.foccolojas.com.br/criare/wbpvencontratos", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(6000)

    if not is_contratos_page(page):
        raise Exception(f"Página de contratos não foi confirmada. URL final: {page.url}")


def extrair_texto_celula(cells, idx):
    if idx >= len(cells):
        return ""
    try:
        return cells[idx].inner_text().strip()
    except Exception:
        return ""


def listar_contratos_visiveis(page, max_linhas=30):
    contratos = []

    linhas = page.locator("table tr").all()

    for linha in linhas:
        try:
            if not linha.is_visible():
                continue

            cells = linha.locator("td").all()
            if len(cells) < 8:
                continue

            numero = extrair_texto_celula(cells, 1)
            projeto = extrair_texto_celula(cells, 2)
            cliente = extrair_texto_celula(cells, 3)
            consultor = extrair_texto_celula(cells, 4)
            executor = extrair_texto_celula(cells, 5)
            valor_venda = extrair_texto_celula(cells, 6)
            situacao = extrair_texto_celula(cells, 7)
            assinatura = extrair_texto_celula(cells, 8)
            previsao_entrega = extrair_texto_celula(cells, 9)

            if not numero or not numero.strip().isdigit():
                continue

            link_contrato = None
            try:
                link = cells[1].locator("a").first
                href = link.get_attribute("href")
                if href:
                    link_contrato = href
            except Exception:
                pass

            contratos.append({
                "numero_contrato": numero,
                "projeto": projeto,
                "cliente": cliente,
                "consultor": consultor,
                "executor": executor,
                "valor_venda": valor_venda,
                "situacao": situacao,
                "assinatura": assinatura,
                "previsao_entrega": previsao_entrega,
                "link_contrato": link_contrato,
            })

            if len(contratos) >= max_linhas:
                break

        except Exception:
            pass

    return contratos


def main():
    resultado = {
        "success": False,
        "url_inicial": FOCCO_URL,
        "url_final": None,
        "login_status": None,
        "quantidade_contratos_visiveis": 0,
        "contratos": [],
        "mensagem": ""
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
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            page = context.new_page()

            resultado["login_status"] = garantir_login(page)

            abrir_contratos(page)

            contratos = listar_contratos_visiveis(page, max_linhas=30)

            resultado["success"] = True
            resultado["url_final"] = page.url
            resultado["contratos"] = contratos
            resultado["quantidade_contratos_visiveis"] = len(contratos)
            resultado["mensagem"] = "Lista de contratos carregada com sucesso"

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao listar contratos: {str(e)}"

        finally:
            browser.close()

    print(json.dumps(resultado, ensure_ascii=False))


if __name__ == "__main__":
    main()