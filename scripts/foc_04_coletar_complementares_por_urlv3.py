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


LABELS_BASICO = [
    "Projeto",
    "Orçamento",
    "Condição de Pagamento",
    "Observação",
    "Observação do Pedido de Compra",
    "Loja/Unidade",
    "Tipo de Venda",
    "Descritivo do Contrato",
    "Liberação Comercial",
    "Liberação Financeira",
    "Andamento da Obra",
    "Status da Impressão",
    "Data de Aprovação",
    "Assinatura do Contrato",
    "Situação",
    "Link Meu Projeto",
]

LABELS_ENTREGA = [
    "Endereço de Entrega",
    "Endereço de Cobrança",
    "Entrega Sugerido (dias)",
    "Prazo de Entrega",
    "Previsão de Entrega",
    "Observações de Montagem",
    "Prioridade de Entrega",
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

    if existe_texto(page, "CLIENTE"):
        evidencias.append("Seção cliente encontrada")

    if existe_texto(page, "DADOS ENTREGA/COBRANÇA"):
        evidencias.append("Seção Dados Entrega/Cobrança encontrada")

    if existe_texto(page, "IMPRIMIR CONTRATO"):
        evidencias.append("Texto 'Imprimir Contrato' encontrado")

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


def _extrair_por_labels(page, labels):
    script = """
    (labels) => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const todos = Array.from(document.querySelectorAll('div, span, label, a, td, th, p'))
            .filter(isVisible);

        const rotulosSet = new Set(labels.map(l => normalizar(l)));

        const ehRotulo = (txt) => rotulosSet.has(normalizar(txt));

        const candidatosDeValor = (el) => {
            const arr = [];

            if (el.nextElementSibling) arr.push(el.nextElementSibling);
            if (el.parentElement) {
                arr.push(el.parentElement.nextElementSibling);
                arr.push(el.parentElement);
            }
            const bloco = el.closest('div');
            if (bloco) {
                arr.push(bloco.nextElementSibling);
                arr.push(bloco);
            }

            return arr.filter(Boolean);
        };

        const pegarMelhorValor = (label) => {
            for (const el of todos) {
                const txt = normalizar(el.innerText || el.textContent || '');
                if (txt !== label) continue;

                const candidatos = candidatosDeValor(el);

                for (const c of candidatos) {
                    if (!c || !isVisible(c)) continue;

                    const descendentes = Array.from(
                        c.querySelectorAll ? c.querySelectorAll('div, span, label, a, td, th, p') : []
                    )
                    .filter(isVisible)
                    .map(n => normalizar(n.innerText || n.textContent || ''))
                    .filter(Boolean);

                    const proprio = normalizar(c.innerText || c.textContent || '');
                    const pool = [proprio, ...descendentes];

                    for (const valor of pool) {
                        if (!valor) continue;
                        if (valor === label) continue;
                        if (ehRotulo(valor)) continue;

                        // rejeita valor que seja só concatenação de outros rótulos
                        const partes = valor.split(/\\s{2,}|\\n|\\r|\\t|(?=[A-ZÁÀÂÃÉÈÊÍÌÎÓÒÔÕÚÙÛÇ][a-záàâãéèêíìîóòôõúùûç])/)
                            .map(v => normalizar(v))
                            .filter(Boolean);

                        if (partes.length > 0 && partes.every(p => ehRotulo(p))) {
                            continue;
                        }

                        return valor;
                    }
                }
            }

            return null;
        };

        const saida = {};
        for (const label of labels) {
            saida[label] = pegarMelhorValor(label);
        }

        return saida;
    }
    """

    for frame in page.frames:
        try:
            data = frame.evaluate(script, labels)
            if data:
                return {k: _limpar_texto(v) if isinstance(v, str) else v for k, v in data.items()}
        except Exception:
            pass

    return {label: None for label in labels}


def _mapear_dados_basicos(labels_map, numero_contrato):
    return {
        "numero_contrato_tela": numero_contrato,
        "cliente_nome": None,
        "projeto": labels_map.get("Projeto"),
        "orcamento": labels_map.get("Orçamento"),
        "condicao_pagamento": labels_map.get("Condição de Pagamento"),
        "observacao": labels_map.get("Observação"),
        "observacao_pedido_compra": labels_map.get("Observação do Pedido de Compra"),
        "loja_unidade": labels_map.get("Loja/Unidade"),
        "tipo_venda": labels_map.get("Tipo de Venda"),
        "descritivo_contrato": labels_map.get("Descritivo do Contrato"),
        "liberacao_comercial": labels_map.get("Liberação Comercial"),
        "liberacao_financeira": labels_map.get("Liberação Financeira"),
        "andamento_obra": labels_map.get("Andamento da Obra"),
        "status_impressao": labels_map.get("Status da Impressão"),
        "data_aprovacao": labels_map.get("Data de Aprovação"),
        "assinatura_contrato": labels_map.get("Assinatura do Contrato"),
        "situacao": labels_map.get("Situação"),
        "link_meu_projeto": labels_map.get("Link Meu Projeto"),
        "numero_contrato": numero_contrato,
    }


def _extrair_cliente_nome(page):
    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const todos = Array.from(document.querySelectorAll('div, span, label, a'))
            .filter(isVisible);

        for (const el of todos) {
            const txt = normalizar(el.innerText || el.textContent || '');
            if (txt !== 'Cliente') continue;

            const candidatos = [
                el.nextElementSibling,
                el.parentElement,
                el.parentElement ? el.parentElement.nextElementSibling : null
            ].filter(Boolean);

            for (const c of candidatos) {
                const links = Array.from(c.querySelectorAll ? c.querySelectorAll('a') : [])
                    .filter(isVisible)
                    .map(a => normalizar(a.innerText || a.textContent || ''))
                    .filter(Boolean);

                if (links.length > 0) {
                    return links[0];
                }

                const texto = normalizar(c.innerText || c.textContent || '');
                if (texto && texto !== 'Cliente') {
                    const primeiraLinha = texto.split('\\n').map(t => normalizar(t)).filter(Boolean)[0];
                    if (primeiraLinha && primeiraLinha !== 'Cliente') {
                        return primeiraLinha;
                    }
                }
            }
        }

        return null;
    }
    """

    for frame in page.frames:
        try:
            valor = frame.evaluate(script)
            if valor:
                return _limpar_texto(valor)
        except Exception:
            pass
    return None


def extrair_dados_basicos_contrato(page, numero_contrato):
    labels_map = _extrair_por_labels(page, LABELS_BASICO)
    dados = _mapear_dados_basicos(labels_map, numero_contrato)
    dados["cliente_nome"] = _extrair_cliente_nome(page)
    return dados


def extrair_dados_entrega_cobranca(page):
    labels_map = _extrair_por_labels(page, LABELS_ENTREGA)
    return {
        "endereco_entrega": labels_map.get("Endereço de Entrega"),
        "endereco_cobranca": labels_map.get("Endereço de Cobrança"),
        "entrega_sugerido_dias": labels_map.get("Entrega Sugerido (dias)"),
        "prazo_entrega": labels_map.get("Prazo de Entrega"),
        "previsao_entrega": labels_map.get("Previsão de Entrega"),
        "observacoes_montagem": labels_map.get("Observações de Montagem"),
        "prioridade_entrega": labels_map.get("Prioridade de Entrega"),
    }


def clicar_botao_cifrao(page):
    script = """
    () => {
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const candidatos = Array.from(document.querySelectorAll('a, button, div, span, img'));
        for (const el of candidatos) {
            if (!isVisible(el)) continue;

            const txt = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            const title = (el.getAttribute && (el.getAttribute('title') || '')) || '';
            const src = (el.getAttribute && (el.getAttribute('src') || '')) || '';

            const bate =
                txt === '$' ||
                title.includes('$') ||
                /cifrao|financeir|prec|orcament|comiss/i.test(title) ||
                /cifrao|financeir|prec|orcament|comiss/i.test(src);

            if (!bate) continue;

            try {
                el.click();
                return { clicado: true, texto: txt, title, src };
            } catch (e) {}
        }

        return { clicado: false };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script)
            if res and res.get("clicado"):
                page.wait_for_timeout(3000)
                return res
        except Exception:
            pass

    return {"clicado": False}


def confirmar_formacao_preco(page):
    evidencias = []

    if existe_texto(page, "Formação de Preço"):
        evidencias.append("Texto 'Formação de Preço' encontrado")
    if existe_texto(page, "Valor de Venda"):
        evidencias.append("Coluna 'Valor de Venda' encontrada")
    if existe_texto(page, "Valor de Custo"):
        evidencias.append("Coluna 'Valor de Custo' encontrada")
    if existe_texto(page, "Lucro Bruto"):
        evidencias.append("Coluna 'Lucro Bruto' encontrada")

    return {"ok": len(evidencias) >= 2, "evidencias": evidencias}


def extrair_formacao_preco(page):
    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const tabelas = Array.from(document.querySelectorAll('table')).filter(isVisible);

        for (const table of tabelas) {
            const textoTabela = normalizar(table.innerText || table.textContent || '');
            if (!/Valor de Venda/i.test(textoTabela) || !/Lucro Bruto/i.test(textoTabela)) continue;

            const headers = Array.from(table.querySelectorAll('th'))
                .map(th => normalizar(th.innerText || th.textContent || ''))
                .filter(Boolean);

            const rows = [];
            const trs = Array.from(table.querySelectorAll('tr'));

            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td'))
                    .map(td => normalizar(td.innerText || td.textContent || ''));
                if (cells.some(Boolean)) {
                    rows.push(cells);
                }
            }

            return { headers, rows };
        }

        return { headers: [], rows: [] };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script)
            if res and (res.get("headers") or res.get("rows")):
                return res
        except Exception:
            pass

    return {"headers": [], "rows": []}


def clicar_cifrao_comissoes(page):
    script = """
    () => {
        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const tabelas = Array.from(document.querySelectorAll('table')).filter(isVisible);

        for (const table of tabelas) {
            const textoTabela = (table.innerText || table.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!/Comiss/i.test(textoTabela)) continue;

            const candidatos = Array.from(table.querySelectorAll('a, button, span, div, img')).filter(isVisible);

            for (const el of candidatos) {
                const txt = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                const title = (el.getAttribute && (el.getAttribute('title') || '')) || '';
                const src = (el.getAttribute && (el.getAttribute('src') || '')) || '';

                const bate =
                    txt === '$' ||
                    title.includes('$') ||
                    /comiss/i.test(title) ||
                    /comiss/i.test(src);

                if (!bate) continue;

                try {
                    el.click();
                    return { clicado: true, texto: txt, title, src };
                } catch (e) {}
            }
        }

        return { clicado: false };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script)
            if res and res.get("clicado"):
                page.wait_for_timeout(3000)
                return res
        except Exception:
            pass

    return {"clicado": False}


def confirmar_previsao_comissionados(page):
    evidencias = []

    if existe_texto(page, "Previsão de Comissionados"):
        evidencias.append("Texto 'Previsão de Comissionados' encontrado")
    if existe_texto(page, "Envolvido"):
        evidencias.append("Coluna 'Envolvido' encontrada")
    if existe_texto(page, "Percentual"):
        evidencias.append("Coluna 'Percentual' encontrada")
    if existe_texto(page, "Base da Comissão"):
        evidencias.append("Coluna 'Base da Comissão' encontrada")

    return {"ok": len(evidencias) >= 2, "evidencias": evidencias}


def extrair_previsao_comissionados(page):
    script = """
    () => {
        const normalizar = (txt) => (txt || '').replace(/\\s+/g, ' ').trim();

        const isVisible = (el) => {
            if (!el) return false;
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        };

        const tabelas = Array.from(document.querySelectorAll('table')).filter(isVisible);

        for (const table of tabelas) {
            const textoTabela = normalizar(table.innerText || table.textContent || '');
            if (!/Envolvido/i.test(textoTabela) || !/Percentual/i.test(textoTabela)) continue;

            const headers = Array.from(table.querySelectorAll('th'))
                .map(th => normalizar(th.innerText || th.textContent || ''))
                .filter(Boolean);

            const rows = [];
            const trs = Array.from(table.querySelectorAll('tr'));

            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td'))
                    .map(td => normalizar(td.innerText || td.textContent || ''));
                if (cells.some(Boolean)) {
                    rows.push(cells);
                }
            }

            return { headers, rows };
        }

        return { headers: [], rows: [] };
    }
    """

    for frame in page.frames:
        try:
            res = frame.evaluate(script)
            if res and (res.get("headers") or res.get("rows")):
                return res
        except Exception:
            pass

    return {"headers": [], "rows": []}


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
        "dados_basicos_contrato": {},
        "dados_entrega_cobranca": {},
        "formacao_preco_confirmada": False,
        "formacao_preco_evidencias": [],
        "formacao_preco": {},
        "previsao_comissionados_confirmada": False,
        "previsao_comissionados_evidencias": [],
        "previsao_comissionados": {},
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

            resultado["dados_basicos_contrato"] = extrair_dados_basicos_contrato(page, numero_contrato)
            resultado["dados_entrega_cobranca"] = extrair_dados_entrega_cobranca(page)

            clique_financeiro = clicar_botao_cifrao(page)
            if clique_financeiro.get("clicado"):
                confirmacao_fp = confirmar_formacao_preco(page)
                resultado["formacao_preco_confirmada"] = confirmacao_fp.get("ok", False)
                resultado["formacao_preco_evidencias"] = confirmacao_fp.get("evidencias", [])
                resultado["formacao_preco"] = extrair_formacao_preco(page)

                clique_comissoes = clicar_cifrao_comissoes(page)
                if clique_comissoes.get("clicado"):
                    confirmacao_pc = confirmar_previsao_comissionados(page)
                    resultado["previsao_comissionados_confirmada"] = confirmacao_pc.get("ok", False)
                    resultado["previsao_comissionados_evidencias"] = confirmacao_pc.get("evidencias", [])
                    resultado["previsao_comissionados"] = extrair_previsao_comissionados(page)

            resultado["success"] = True
            resultado["mensagem"] = "Complementares coletados com sucesso"
            print(json.dumps(resultado, ensure_ascii=False))

        except Exception as e:
            resultado["url_final"] = page.url if "page" in locals() and page else None
            resultado["mensagem"] = f"Erro ao coletar complementares: {str(e)}"
            print(json.dumps(resultado, ensure_ascii=False))

        finally:
            browser.close()


if __name__ == "__main__":
    main()