import subprocess, os, shlex, time
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = '/tmp'
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
DB_PASSWORD = os.getenv("MONGO_PASSWORD")
if not DB_PASSWORD: exit(1)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def run_command(command, timeout=60):
    try:
        # capture_output=True ensures non-interactive mode to prevent hangs
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, timeout=timeout, cwd=PROJECT_DIR)
        return {"success": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired: return {"success": False, "error": "Command timed out."}
    except subprocess.CalledProcessError as e: return {"success": False, "output": e.stdout, "error": e.stderr}
    except Exception as e: return {"success": False, "error": str(e)}

@app.route('/')
def index(): return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    run_command("docker compose pull", timeout=300)
    return jsonify(run_command("docker compose up -d", timeout=60))

@app.route('/backup', methods=['GET', 'POST'])
def backup():
    if DB_PASSWORD == "CHANGE_ME": return "SECURITY RISK: Change default password first.", 400
    host_path = os.path.join(UPLOAD_FOLDER, f"backup_{int(time.time())}.gz")
    # CRITICAL FIX: Direct stream to host file, forced IPv4 (127.0.0.1)
    cmd = f"docker exec my-mongo-db mongodump --host 127.0.0.1 --username=root --password={shlex.quote(DB_PASSWORD)} --authenticationDatabase=admin --archive --gzip"
    try:
        with open(host_path, 'wb') as f:
            subprocess.run(cmd, shell=True, check=True, stdout=f, stderr=subprocess.PIPE, timeout=120)
        return send_file(host_path, as_attachment=True, download_name="mongo_backup.gz", mimetype="application/gzip")
    except Exception as e: return f"Error: {str(e)}", 500
    finally:
        if os.path.exists(host_path):
             time.sleep(1)
             try: os.remove(host_path)
             except: pass

@app.route('/restore', methods=['POST'])
def restore():
    file = request.files.get('backupFile')
    if not file or file.filename == '': return jsonify({"success": False, "error": "No file."}), 400
    host_path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
    try:
        file.save(host_path)
        if not run_command(f"docker cp {host_path} my-mongo-db:/tmp/restore.gz", timeout=60)["success"]: return jsonify({"success": False, "error": "Copy failed."}), 500
        # CRITICAL FIX: Restore from internal path, forced IPv4
        restore_cmd = f"docker exec my-mongo-db mongorestore --host 127.0.0.1 --username=root --password={shlex.quote(DB_PASSWORD)} --authenticationDatabase=admin --archive=/tmp/restore.gz --gzip --drop"
        return jsonify(run_command(restore_cmd, timeout=300))
    finally:
        if os.path.exists(host_path): os.remove(host_path)
        run_command("docker exec my-mongo-db rm -f /tmp/restore.gz", timeout=10)

@app.route('/logs', methods=['GET'])
def logs(): return jsonify(run_command("docker compose logs --tail=100", timeout=10))

@app.route('/add-rule', methods=['POST'])
def add_rule():
    ip = request.json.get('ip')
    return jsonify(run_command(f"sudo ufw allow from {shlex.quote(ip)} to any port 27017 proto tcp", timeout=10)) if ip else (jsonify({"success": False, "error": "No IP."}), 400)

@app.route('/status', methods=['GET'])
def get_status():
    try:
        res = subprocess.run("docker inspect --format '{{.State.Status}}' my-mongo-db", shell=True, check=True, capture_output=True, text=True, timeout=5)
        return jsonify({"success": True, "status": res.stdout.strip()})
    except: return jsonify({"success": True, "status": "not_deployed"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)