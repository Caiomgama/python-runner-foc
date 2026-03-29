import json

resultado = {
    "projeto": "FOC",
    "status": "ok",
    "mensagem": "python-runner funcionando"
}

print(json.dumps(resultado, ensure_ascii=False))