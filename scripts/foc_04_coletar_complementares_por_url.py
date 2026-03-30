import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

FOCCO_URL = os.getenv("FOCCO_URL", "https://web.foccolojas.com.br/")
FOCCO_USERNAME = os.getenv("FOCCO_USERNAME", "")
FOCCO_PASSWORD = os.getenv("FOCCO_PASSWORD", "")

DASHBOARD_URL_PARTS = [
    "/criare/servlet/wbpnucnovodashboard",
]

CONTRATO_DETALHE_URL_PART = "/criare/wbpvencontrato?"


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

        if not has_login_form(page):
            return True

        page.wait_for_timeout(3000)
        return not has_login_form(page)

    return True


def _limpar_texto(valor):
    if valor is None:
        return None
    return " ".join(str(valor).split()).strip()


def normalizar(valor):
    return _limpar_texto(valor) or ""


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
    evidencias = []

    if CONTRATO_DETALHE_URL_PART in url_atual:
        evidencias.append("URL de detalhe do contrato detectada")

    if existe_texto(page, "Contrato >"):
        evidencias.append("Breadcrumb de contrato encontrado")

    if existe_texto(page, "Ambientes"):
        evidencias.append("Seção Ambientes encontrada")

    if numero_contrato and existe_texto(page, str(numero_contrato)):
        evidencias.append(f"Número do contrato {numero_contrato} encontrado na tela")

    ok = len(evidencias) >= 2 or (
        CONTRATO_DETALHE_URL_PART in url_atual and len(evidencias) >= 1
    )

    return {
        "ok": ok,
        "evidencias": evidencias,
    }


def abrir_contrato(page, url_contrato, numero_contrato, resultado):
    page.goto(url_contrato, wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(5000)

    if has_login_form(page):
        resultado["relogin_durante_abertura"] = True
        do_login(page)
        page.wait_for_timeout(8000)
        page.goto(url_contrato, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)

    return confirmar_detalhe_contrato(page, numero_contrato)


def extrair_ambientes(page):
    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const pegarTexto = (root, seletor) => {
            const el = root.querySelector(seletor);
            if (!el || !isVisible(el)) return null;
            return normalizar(el.innerText || el.textContent || '');
        };

        const tabelas = Array.from(document.querySelectorAll('table')).filter(isVisible);

        for (const table of tabelas) {
            const textoTabela = normalizar(table.innerText || table.textContent || '');

            // garante que é a tabela certa
            if (!/Ambiente/i.test(textoTabela)) continue;
            if (!/Valor Líquido/i.test(textoTabela) && !/Valor Liquido/i.test(textoTabela)) continue;
            if (!/Valor Total/i.test(textoTabela)) continue;

            const linhas = [];
            const trs = Array.from(table.querySelectorAll('tr'));

            for (const tr of trs) {
                const rowText = normalizar(tr.innerText || tr.textContent || '');

                // ignora header
                if (!rowText) continue;
                if (/^Ambiente\\s+Nome\\s+Situa/i.test(rowText)) continue;

                const ambiente = pegarTexto(tr, "span[id*='VLJ_AMB_AMBIENTE_'], span[id*='AMB_AMBIENTE_']");
                const nome = pegarTexto(tr, "span[id*='VLJ_AMB_DESCRICAO_AUXILIAR_'], span[id*='AMB_DESCRICAO_AUXILIAR_']");
                const situacao = pegarTexto(tr, "span[id*='SITUACAO'], span[id*='SITUACAOITEM'], span[id*='AMB_SITUACAO_']");
                const valorLiquido = pegarTexto(tr, "span[id*='VALORLIQUIDOITEM_'], span[id*='VALORLIQUIDO_']");
                const valorTotal = pegarTexto(tr, "span[id*='VALORTOTALITEM_'], span[id*='VALORTOTAL_']");

                // fallback por colunas visíveis, caso algum seletor não pegue
                const tds = Array.from(tr.querySelectorAll('td'))
                    .filter(isVisible)
                    .map(td => normalizar(td.innerText || td.textContent || ''));

                let ambienteFinal = ambiente;
                let nomeFinal = nome;
                let situacaoFinal = situacao;
                let valorLiquidoFinal = valorLiquido;
                let valorTotalFinal = valorTotal;

                if (tds.length >= 5) {
                    ambienteFinal = ambienteFinal || tds[1] || tds[0] || null;
                    nomeFinal = nomeFinal || tds[2] || null;
                    situacaoFinal = situacaoFinal || tds[3] || null;

                    const valores = tds.filter(v => /^R?\\$?\\s*[\\d\\.]+,\\d+$/.test(v) || /^[\\d\\.]+,\\d+$/.test(v));
                    if (valores.length >= 1) valorLiquidoFinal = valorLiquidoFinal || valores[0];
                    if (valores.length >= 2) valorTotalFinal = valorTotalFinal || valores[1];
                }

                if (!ambienteFinal && !nomeFinal && !valorLiquidoFinal && !valorTotalFinal) {
                    continue;
                }

                linhas.push({
                    ambiente: ambienteFinal,
                    nome: nomeFinal,
                    situacao: situacaoFinal,
                    valor_liquido: valorLiquidoFinal,
                    valor_total: valorTotalFinal,
                    row_text: rowText
                });
            }

            return linhas;
        }

        return [];
    }
    """

    for frame in page.frames:
        try:
            data = frame.evaluate(script)
            if data:
                return [
                    {
                        "ambiente": _limpar_texto(item.get("ambiente")),
                        "nome": _limpar_texto(item.get("nome")),
                        "situacao": _limpar_texto(item.get("situacao")),
                        "valor_liquido": _limpar_texto(item.get("valor_liquido")),
                        "valor_total": _limpar_texto(item.get("valor_total")),
                    }
                    for item in data
                ]
        except Exception:
            pass

    return []


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
        "evidencias_confirmacao": [],
        "ambientes": [],
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            ok_login = garantir_login(page, resultado)
            if not ok_login:
                resultado["url_final"] = page.url
                resultado["mensagem"] = "Não foi possível concluir o login"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            confirmacao = abrir_contrato(page, url_contrato, numero_contrato, resultado)
            resultado["url_final"] = page.url
            resultado["evidencias_confirmacao"] = confirmacao.get("evidencias", [])

            if not confirmacao.get("ok"):
                resultado["mensagem"] = "Não foi possível confirmar a tela do contrato"
                print(json.dumps(resultado, ensure_ascii=False))
                return

            resultado["contrato_aberto"] = True
            resultado["pagina_confirmada"] = True
            resultado["ambientes"] = extrair_ambientes(page)

            resultado["success"] = True
            resultado["mensagem"] = "Ambientes coletados com sucesso"
            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao coletar ambientes: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()