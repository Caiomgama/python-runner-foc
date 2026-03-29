from flask import Flask, request, jsonify
import subprocess
import os

app = Flask(__name__)

SCRIPTS_DIR = "/app/scripts"

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "online",
        "service": "python-runner-foc"
    })

@app.route("/run", methods=["POST"])
def run_script():
    try:
        data = request.get_json(silent=True) or {}

        script = data.get("script")
        args = data.get("args", [])

        if not script:
            return jsonify({"error": "Campo 'script' não informado"}), 400

        script_path = os.path.join(SCRIPTS_DIR, script)

        if not os.path.isfile(script_path):
            return jsonify({
                "error": f"Script não encontrado: {script}",
                "script_path": script_path
            }), 404

        cmd = ["python", script_path]

        if isinstance(args, list):
            cmd.extend(str(arg) for arg in args)
        else:
            return jsonify({"error": "Campo 'args' deve ser uma lista"}), 400

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        return jsonify({
            "success": result.returncode == 0,
            "script": script,
            "args": args,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)